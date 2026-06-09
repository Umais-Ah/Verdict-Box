"""Admin moderation routes for flagged disputes, appeals, and user management."""

from datetime import datetime
from decimal import Decimal
from flask import Blueprint, jsonify, request, render_template, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from core.extensions import db
from core.models import Dispute, Appeal, AdminLog, User, Submission, AIResult, Notification, DisputeReport
from core.badges_engine import refresh_user_badges
from ai.ml_pipeline import run_full_pipeline
import threading


admin_bp = Blueprint("admin", __name__)


def _payload():
    """Returns JSON body when available, otherwise form values."""

    return request.get_json(silent=True) or request.form


def _admin_only():
    """Returns True if current session user is an admin."""

    return current_user.is_authenticated and current_user.role == "admin"


def _mark_reports_reviewed(dispute, decision):
    """Marks dispute reports as reviewed by the current admin."""

    for report in dispute.reports:
        report.reviewed = True
        report.reviewed_at = datetime.utcnow()
        report.reviewed_by_user_id = current_user.id
    # If the admin cleared the dispute, remove the review_state so it no longer
    # appears in moderation queues that filter by non-null review_state.
    if decision == "cleared":
        dispute.review_state = None
    else:
        dispute.review_state = decision


def _log_admin_action(dispute, action_type, reason_text, target_user_id=None):
    """Writes a moderation log with reviewer attribution."""

    db.session.add(
        AdminLog(
            dispute_id=dispute.id if dispute else None,
            admin_user_id=current_user.id,
            action_type=action_type,
            reason=reason_text,
            target_user_id=target_user_id,
        )
    )


def _restore_dispute_status(dispute):
    """Restores dispute status without altering verdict visibility."""

    if dispute.ai_result:
        dispute.status = "resolved"
        return

    submissions_count = Submission.query.filter_by(dispute_id=dispute.id).count()
    if submissions_count == 0:
        dispute.status = "waiting"
    else:
        dispute.status = "active"


@admin_bp.route("/admin", methods=["GET"])
@login_required
def admin_dashboard():
    """Renders admin panel with flagged disputes, appeals, users, and logs."""

    if not _admin_only():
        flash("Admin access required.", "warning")
        return redirect(url_for("auth.home"))

    flagged = Dispute.query.filter_by(status="flagged").order_by(Dispute.created_at.desc()).all()
    appeals = Appeal.query.filter_by(status="pending").order_by(Appeal.submitted_at.desc()).all()
    users = User.query.order_by(User.created_at.desc()).all()
    logs = AdminLog.query.order_by(AdminLog.created_at.desc()).limit(50).all()
    return render_template("admin.html", flagged_disputes=flagged, pending_appeals=appeals, all_users=users, admin_logs=logs)


@admin_bp.route("/admin/dispute/<int:dispute_id>/review", methods=["POST"])
@login_required
def review_dispute(dispute_id):
    """Marks a flagged dispute as reviewed and records admin notes."""

    if not _admin_only():
        return jsonify({"error": "Admin access required"}), 403

    dispute = Dispute.query.get_or_404(dispute_id)
    data = _payload()
    notes = (data.get("notes") or "").strip()

    try:
        _restore_dispute_status(dispute)
        dispute.is_public = True
        _mark_reports_reviewed(dispute, "cleared")
        _log_admin_action(dispute, "dispute_cleared", notes or "Reviewed by admin")
        db.session.commit()
        return jsonify({"message": "Dispute reviewed"}), 200
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": f"Review failed: {exc}"}), 500


@admin_bp.route("/admin/dispute/<int:dispute_id>/moderate", methods=["POST"])
@login_required
def moderate_reported_dispute(dispute_id):
    """Applies admin moderation decisions to a reported or flagged dispute."""

    if not _admin_only():
        return jsonify({"error": "Admin access required"}), 403

    dispute = Dispute.query.get_or_404(dispute_id)
    data = _payload()
    decision = (data.get("decision") or "").strip().lower()
    notes = (data.get("notes") or "").strip()
    target_user_id = data.get("target_user_id")

    valid_decisions = {"clear", "investigate", "hide", "restrict"}
    if decision not in valid_decisions:
        return jsonify({"error": "decision must be clear, investigate, hide, or restrict"}), 400

    try:
        if decision == "clear":
            _restore_dispute_status(dispute)
            dispute.is_public = True
            _mark_reports_reviewed(dispute, "cleared")
            _log_admin_action(dispute, "dispute_cleared", notes or "Dispute cleared by admin")
        elif decision == "investigate":
            dispute.status = "flagged"
            dispute.review_state = "under_review"
            _log_admin_action(dispute, "dispute_under_review", notes or "Dispute kept under review")
        elif decision == "hide":
            dispute.status = "flagged"
            dispute.is_public = False
            dispute.review_state = "hidden"
            _log_admin_action(dispute, "dispute_hidden", notes or "Dispute hidden by admin")
        elif decision == "restrict":
            dispute.status = "flagged"
            dispute.review_state = "restricted"
            target_id = int(target_user_id) if target_user_id else dispute.created_by
            target_user = User.query.get(target_id)
            if target_user and target_user.role != "admin":
                target_user.is_active = False
                _log_admin_action(dispute, "user_restricted", notes or f"User {target_user.username} restricted by admin", target_user_id=target_user.id)
            _log_admin_action(dispute, "dispute_restricted", notes or "Dispute actioned with user restriction", target_user_id=target_id)

        db.session.commit()
        return jsonify({"message": f"Dispute {decision} successfully"}), 200
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": f"Moderation failed: {exc}"}), 500


@admin_bp.route("/admin/appeal/<int:appeal_id>/decide", methods=["POST"])
@login_required
def decide_appeal(appeal_id):
    """Approves or rejects an appeal and records an admin log."""

    if not _admin_only():
        return jsonify({"error": "Admin access required"}), 403

    appeal = Appeal.query.get_or_404(appeal_id)
    data = _payload()
    decision = (data.get("decision") or "").strip().lower()
    response_text = (data.get("admin_response") or "").strip()

    if decision not in ["approved", "rejected"]:
        return jsonify({"error": "decision must be approved or rejected"}), 400
    try:
        appeal.status = decision
        appeal.admin_response = response_text
        appeal.reviewed_at = datetime.utcnow()
        prior_verdict_context = None
        previous_winner_name = ""
        if decision == "approved" and appeal.dispute:
            dispute = appeal.dispute
            moderator_note = response_text or appeal.reason_text
            dispute.moderator_note = moderator_note
            if dispute.ai_result:
                prior_verdict_context = {
                    "winner_name": dispute.ai_result.winner.username if dispute.ai_result.winner else "Unknown",
                    "fallacies_a": list(dispute.ai_result.fallacies_a or []),
                    "fallacies_b": list(dispute.ai_result.fallacies_b or []),
                    "reasoning": dispute.ai_result.reasoning or "",
                }
                previous_winner_name = str(prior_verdict_context.get("winner_name") or "").strip()
            if dispute.ai_result:
                db.session.delete(dispute.ai_result)
            dispute.status = "active"
            dispute.resolved_at = None
        dispute_title = appeal.dispute.title if appeal.dispute else f"Dispute #{appeal.dispute_id}"
        appellant_name = appeal.appellant.username if appeal.appellant else f"User #{appeal.appellant_user_id}"
        log_reason = (
            f"Appeal {decision} for \"{dispute_title}\" by @{appellant_name}. "
            f"Reason: {appeal.reason_text}. "
            f"Admin response: {response_text or 'No response provided.'}"
        )
        if decision == "approved" and previous_winner_name:
            log_reason += f" Previous winner: {previous_winner_name}."
        db.session.add(AdminLog(dispute_id=appeal.dispute_id, admin_user_id=current_user.id, target_user_id=appeal.appellant_user_id, action_type=f"appeal_{decision}", reason=log_reason))
        db.session.commit()

        if appeal.appellant_user_id:
            notification_title = f"Appeal {decision.title()}"
            notification_body = (
                f"Your appeal for '{dispute_title}' was {decision}. "
                f"Admin response: {response_text or 'No response provided.'}"
            )
            db.session.add(Notification(
                user_id=appeal.appellant_user_id,
                title=notification_title,
                body=notification_body,
                link_url=f"/dispute/{appeal.dispute_id}/verdict",
            ))
            db.session.commit()

        # Run the heavy ML/LLM appeal rerun asynchronously so the admin UI is responsive.
        if decision == "approved" and appeal.dispute:
            def _async_appeal_rerun(a_id):
                with current_app.app_context():
                    try:
                        _appeal = Appeal.query.get(a_id)
                        if not _appeal or _appeal.status != "approved" or not _appeal.dispute:
                            return
                        _dispute = Dispute.query.get(_appeal.dispute_id)
                        submissions = Submission.query.filter_by(dispute_id=_dispute.id).order_by(Submission.submitted_at.asc()).all()
                        if len(submissions) < 2:
                            return
                        user_a = submissions[0].user
                        user_b = submissions[1].user
                        prior_ctx = None
                        if _dispute.ai_result:
                            prior_ctx = {
                                "winner_name": _dispute.ai_result.winner.username if _dispute.ai_result.winner else "Unknown",
                                "fallacies_a": list(_dispute.ai_result.fallacies_a or []),
                                "fallacies_b": list(_dispute.ai_result.fallacies_b or []),
                                "reasoning": _dispute.ai_result.reasoning or "",
                            }
                        # remove any previous AI result before rerun
                        if _dispute.ai_result:
                            try:
                                db.session.delete(_dispute.ai_result)
                                db.session.commit()
                            except Exception:
                                db.session.rollback()
                        pipeline_result = run_full_pipeline(
                            dispute_id=_dispute.id,
                            text_a=submissions[0].argument_text,
                            text_b=submissions[1].argument_text,
                            user_a_name=user_a.username,
                            user_b_name=user_b.username,
                            appeal_context=_dispute.moderator_note,
                            prior_verdict_context=prior_ctx,
                        )
                        if pipeline_result.get("status") == "resolved":
                            verdict = pipeline_result["verdict"]
                            winner_user_id = user_a.id if verdict.get("winner") == "A" else user_b.id
                            ai_result = AIResult(
                                dispute_id=_dispute.id,
                                toxicity_score_a=Decimal(str(pipeline_result["ml_scores"]["toxicity_a"])),
                                toxicity_score_b=Decimal(str(pipeline_result["ml_scores"]["toxicity_b"])),
                                sentiment_a=pipeline_result["ml_scores"]["sentiment_a"],
                                sentiment_b=pipeline_result["ml_scores"]["sentiment_b"],
                                sarcasm_score_a=Decimal(str(pipeline_result["ml_scores"]["sarcasm_a"])),
                                sarcasm_score_b=Decimal(str(pipeline_result["ml_scores"]["sarcasm_b"])),
                                winner_user_id=winner_user_id,
                                reasoning=verdict.get("reasoning", "No reasoning provided"),
                                confidence_score=Decimal(str(verdict.get("confidence", 0.0))),
                                fallacies_a=verdict.get("fallacies_a", []),
                                fallacies_b=verdict.get("fallacies_b", []),
                            )
                            try:
                                db.session.add(ai_result)
                                _dispute.status = "resolved"
                                _dispute.resolved_at = datetime.utcnow()
                                db.session.commit()
                            except Exception:
                                db.session.rollback()
                        elif pipeline_result.get("status") == "flagged":
                            try:
                                _dispute.status = "flagged"
                                db.session.add(AdminLog(dispute_id=_dispute.id, admin_user_id=current_user.id, target_user_id=_appeal.appellant_user_id, action_type="appeal_rerun_flagged", reason=pipeline_result.get("message", "Appeal rerun flagged")))
                                db.session.commit()
                            except Exception:
                                db.session.rollback()
                        else:
                            # log generic failure for operator review
                            try:
                                db.session.add(AdminLog(dispute_id=_dispute.id, admin_user_id=current_user.id, target_user_id=_appeal.appellant_user_id, action_type="appeal_rerun_failed", reason=pipeline_result.get("message", "Appeal rerun failed")))
                                db.session.commit()
                            except Exception:
                                db.session.rollback()
                        try:
                            refresh_user_badges(_appeal.appellant_user_id)
                        except Exception:
                            db.session.rollback()
                    except Exception:
                        # ensure any unexpected errors don't kill the thread silently
                        try:
                            db.session.rollback()
                        except Exception:
                            pass

            # start the rerun in a daemon thread so the HTTP response can return immediately
            t = threading.Thread(target=_async_appeal_rerun, args=(appeal.id,), daemon=True)
            t.start()
        try:
            refresh_user_badges(appeal.appellant_user_id)
        except Exception:
            db.session.rollback()
        return jsonify({"message": f"Appeal {decision}. Rerun queued."}), 200
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": f"Appeal decision failed: {exc}"}), 500


@admin_bp.route("/admin/users", methods=["GET"])
@login_required
def list_users():
    """Returns admin view of all users."""

    if not _admin_only():
        return jsonify({"error": "Admin access required"}), 403

    users = User.query.order_by(User.id.asc()).all()
    return jsonify([
        {
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "role": u.role,
            "is_active": u.is_active,
            "reputation_score": u.reputation_score,
        }
        for u in users
    ]), 200


@admin_bp.route("/admin/users/<int:user_id>/toggle", methods=["POST"])
@login_required
def toggle_user(user_id):
    """Toggles user active status for moderation actions."""

    if not _admin_only():
        return jsonify({"error": "Admin access required"}), 403

    user = User.query.get_or_404(user_id)
    try:
        user.is_active = not user.is_active
        action_type = "user_deactivated" if not user.is_active else "user_activated"
        db.session.add(AdminLog(dispute_id=None, admin_user_id=current_user.id, target_user_id=user.id, action_type=action_type, reason=f"User {user.username} active={user.is_active}"))
        db.session.commit()
        return jsonify({"message": "User status updated", "is_active": user.is_active, "action_type": action_type}), 200
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": f"Failed to update user status: {exc}"}), 500


@admin_bp.route("/admin/dispute/<int:dispute_id>/flag-system", methods=["POST"])
@login_required
def create_system_flag(dispute_id):
    """Creates a system-level moderation flag for a dispute (AI-detected toxicity, etc).
    
    This is the primary moderation mechanism for private disputes. System flags bypass
    the participant reporting system and go directly to admin review.
    """

    if not _admin_only():
        return jsonify({"error": "Admin access required"}), 403

    dispute = Dispute.query.get_or_404(dispute_id)
    data = _payload()
    reason = (data.get("reason") or "").strip()
    toxicity_score = data.get("toxicity_score")

    if not reason:
        return jsonify({"error": "reason is required"}), 400

    try:
        # Create a system flag as a DisputeReport with is_system_flag=True
        # Use the admin user as the "reporter"
        system_flag = DisputeReport(
            dispute_id=dispute.id,
            reporter_user_id=current_user.id,
            reason=reason,
            details=f"System flag: {reason}. Toxicity score: {toxicity_score}" if toxicity_score else f"System flag: {reason}",
            is_system_flag=True,
        )
        db.session.add(system_flag)
        
        # Mark the dispute as flagged
        dispute.status = "flagged"
        
        # Log the action
        _log_admin_action(dispute, "system_flag_created", f"System flag: {reason}")
        
        db.session.commit()
        return jsonify({"message": "System flag created successfully"}), 201
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": f"Failed to create system flag: {exc}"}), 500


@admin_bp.route("/admin/private-disputes", methods=["GET"])
@login_required
def list_private_disputes():
    """Returns admin view of private disputes with system flags and status."""

    if not _admin_only():
        return jsonify({"error": "Admin access required"}), 403

    private_disputes = Dispute.query.filter(
        Dispute.moderation_mode == "private"
    ).order_by(Dispute.created_at.desc()).all()
    
    result = []
    for dispute in private_disputes:
        system_flags = DisputeReport.query.filter_by(
            dispute_id=dispute.id,
            is_system_flag=True
        ).all()
        
        result.append({
            "id": dispute.id,
            "title": dispute.title,
            "created_by": dispute.creator.username if dispute.creator else "Unknown",
            "status": dispute.status,
            "system_flags_count": len(system_flags),
            "created_at": dispute.created_at.isoformat() if dispute.created_at else None,
        })
    
    return jsonify(result), 200


@admin_bp.route("/admin/dispute/<int:dispute_id>/private-moderation", methods=["POST"])
@login_required
def moderate_private_dispute(dispute_id):
    """Applies admin moderation to a private dispute (system flags only).
    
    Private disputes have stricter, more centralized moderation rules:
    - No participant reports (only system flags)
    - Direct admin action without escalation thresholds
    - Appeals allowed but only for participants
    """

    if not _admin_only():
        return jsonify({"error": "Admin access required"}), 403

    dispute = Dispute.query.get_or_404(dispute_id)
    
    if not dispute.is_private():
        return jsonify({"error": "This route is for private disputes only"}), 400

    data = _payload()
    decision = (data.get("decision") or "").strip().lower()
    notes = (data.get("notes") or "").strip()
    target_user_id = data.get("target_user_id")

    valid_decisions = {"clear", "investigate", "restrict", "terminate"}
    if decision not in valid_decisions:
        return jsonify({"error": "decision must be clear, investigate, restrict, or terminate"}), 400

    try:
        if decision == "clear":
            # Clear the system flags and restore status
            _restore_dispute_status(dispute)
            _log_admin_action(dispute, "private_dispute_cleared", notes or "Private dispute cleared by admin")
        
        elif decision == "investigate":
            dispute.status = "flagged"
            dispute.review_state = "under_review"
            _log_admin_action(dispute, "private_dispute_under_review", notes or "Private dispute kept under review")
        
        elif decision == "restrict":
            # Restrict a participant in the private dispute
            dispute.status = "flagged"
            dispute.review_state = "restricted"
            target_id = int(target_user_id) if target_user_id else dispute.created_by
            target_user = User.query.get(target_id)
            if target_user and target_user.role != "admin":
                target_user.is_active = False
                _log_admin_action(dispute, "user_restricted_private_dispute", 
                                 notes or f"User {target_user.username} restricted for private dispute violations",
                                 target_user_id=target_user.id)
        
        elif decision == "terminate":
            # Terminate the private dispute and mark as hidden
            dispute.status = "flagged"
            dispute.is_public = False
            dispute.review_state = "terminated"
            _log_admin_action(dispute, "private_dispute_terminated", 
                             notes or "Private dispute terminated by admin")

        db.session.commit()
        return jsonify({"message": f"Private dispute {decision} successfully"}), 200
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": f"Private dispute moderation failed: {exc}"}), 500
