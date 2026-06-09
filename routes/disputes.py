"""Dispute lifecycle routes from creation to AI verdict storage."""

from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal
import json
import re
from pathlib import Path
from types import SimpleNamespace
from flask import Blueprint, request, jsonify, render_template, redirect, url_for
from flask_login import login_required, current_user
from sqlalchemy import func, inspect
from sqlalchemy.exc import SQLAlchemyError
from core.extensions import db
from core.models import Dispute, User, Submission, AIResult, Appeal, AdminLog, Comment, DisputeReport
from ai.ml_pipeline import run_full_pipeline
from core.badges_engine import refresh_user_badges


disputes_bp = Blueprint("disputes", __name__)

COMMENTS_FALLBACK_FILE = Path(__file__).resolve().parents[1] / "comments_fallback.json"
REACTIONS_FALLBACK_FILE = Path(__file__).resolve().parents[1] / "dispute_reactions_fallback.json"


FALLACY_EXPLANATIONS = {
    "Ad Hominem": "Attacked the person, not the argument",
    "Strawman": "Twisted the opponent's words unfairly",
    "False Dichotomy": "Gave only two options when more exist",
    "Appeal to Emotion": "Used feelings instead of facts",
    "Hasty Generalization": "Drew a big conclusion from little evidence",
}

REPORT_REASON_LABELS = {
    "spam": "Spam",
    "abuse": "Abuse / Toxic language",
    "misinformation": "Misinformation",
    "off_topic": "Off-topic content",
    "other": "Other",
}

REPORT_ESCALATION_THRESHOLD = 3


def _merge_unlocked_badges(existing, new_items):
    """Merges badge payloads by name while preserving first-seen order."""

    merged = list(existing or [])
    seen = {row.get("name") for row in merged if isinstance(row, dict)}
    for row in (new_items or []):
        if not isinstance(row, dict):
            continue
        name = row.get("name")
        if not name or name in seen:
            continue
        seen.add(name)
        merged.append(row)
    return merged


def _map_fallacies_for_display(fallacies):
    """Maps technical fallacy labels to plain-English frontend text."""

    if not isinstance(fallacies, list):
        return []
    return [FALLACY_EXPLANATIONS.get(name, name) for name in fallacies]


def _payload():
    """Returns JSON body when available, otherwise HTML form values."""

    return request.get_json(silent=True) or request.form


def _dispute_report_summary(dispute_id):
    """Returns report count and rows for one dispute."""

    rows = DisputeReport.query.filter_by(dispute_id=dispute_id).order_by(DisputeReport.created_at.desc()).all()
    return {
        "count": len(rows),
        "reasons": [row.reason for row in rows],
        "rows": rows,
    }


def _argument_summary(text):
    """Builds a short, readable one-line summary from argument text."""

    if not text:
        return "No summary available."
    cleaned = re.sub(r"^\s*in\s*short\s*:\s*", "", str(text), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return "No summary available."
    words = cleaned.split(" ")
    if len(words) <= 18:
        return cleaned
    return " ".join(words[:18]).rstrip(".,;:") + "..."


def _could_have_won_tip(loser_name, loser_fallacies, loser_toxicity, loser_sarcasm):
    """Creates a simple coaching tip for the losing side."""

    tips = []
    if loser_fallacies:
        tips.append(f"avoid {loser_fallacies[0].lower()} and stay on the main claim")
    if loser_toxicity >= 0.35:
        tips.append("use calmer wording and remove personal attacks")
    if loser_sarcasm >= 0.35:
        tips.append("reduce sarcasm and add direct evidence")
    if not tips:
        tips.append("add one concrete fact and a clear cause-effect explanation")

    return f"If {loser_name} had focused on {tips[0]}, the argument could have been much stronger."


def _serialize_comment(comment):
    """Normalizes comment payload for JSON responses."""

    if isinstance(comment, dict):
        return {
            "id": comment.get("id"),
            "dispute_id": comment.get("dispute_id"),
            "user_id": comment.get("user_id"),
            "username": comment.get("username", "Unknown"),
            "body": comment.get("body", ""),
            "created_at": comment.get("created_at"),
        }

    return {
        "id": comment.id,
        "dispute_id": comment.dispute_id,
        "user_id": comment.user_id,
        "username": comment.author.username if comment.author else "Unknown",
        "body": comment.body,
        "created_at": comment.created_at.isoformat() if comment.created_at else None,
    }


def _comments_available():
    """Checks whether comments table exists and is queryable."""

    try:
        return inspect(db.engine).has_table("comments")
    except Exception:
        return False


def _load_fallback_comments():
    """Reads fallback comment rows from local JSON file."""

    if not COMMENTS_FALLBACK_FILE.exists():
        return []
    try:
        data = json.loads(COMMENTS_FALLBACK_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_fallback_comments(rows):
    """Persists fallback comments to local JSON file."""

    COMMENTS_FALLBACK_FILE.write_text(json.dumps(rows, ensure_ascii=True, indent=2), encoding="utf-8")


def _fallback_template_comments(dispute_id):
    """Converts fallback rows to object shape expected by Jinja templates."""

    rows = [row for row in _load_fallback_comments() if int(row.get("dispute_id", -1)) == int(dispute_id)]
    rows.sort(key=lambda row: row.get("created_at") or "", reverse=True)
    out = []
    for row in rows[:100]:
        created_raw = row.get("created_at")
        try:
            created_dt = datetime.fromisoformat(created_raw) if created_raw else None
        except ValueError:
            created_dt = None
        out.append(
            SimpleNamespace(
                id=row.get("id"),
                dispute_id=row.get("dispute_id"),
                user_id=row.get("user_id"),
                body=row.get("body", ""),
                created_at=created_dt,
                author=SimpleNamespace(username=row.get("username", "Unknown")),
            )
        )
    return out


def _fallback_api_comments(dispute_id):
    """Returns fallback comments in API-safe dictionary shape."""

    rows = [row for row in _load_fallback_comments() if int(row.get("dispute_id", -1)) == int(dispute_id)]
    rows.sort(key=lambda row: row.get("created_at") or "", reverse=True)
    return rows[:100]


def _create_fallback_comment(dispute_id, user_id, username, body):
    """Creates a new fallback comment row and persists it."""

    rows = _load_fallback_comments()
    next_id = max([int(row.get("id", 0)) for row in rows] + [0]) + 1
    created_at = datetime.utcnow().isoformat()
    row = {
        "id": next_id,
        "dispute_id": int(dispute_id),
        "user_id": int(user_id),
        "username": username,
        "body": body,
        "created_at": created_at,
    }
    rows.append(row)
    _save_fallback_comments(rows)
    return row


def _load_fallback_reactions():
    """Reads fallback dispute reaction rows from local JSON file."""

    if not REACTIONS_FALLBACK_FILE.exists():
        return []
    try:
        data = json.loads(REACTIONS_FALLBACK_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_fallback_reactions(rows):
    """Persists fallback dispute reactions to local JSON file."""

    REACTIONS_FALLBACK_FILE.write_text(json.dumps(rows, ensure_ascii=True, indent=2), encoding="utf-8")


def _reaction_counts_for_disputes(dispute_ids):
    """Builds upvote/downvote counters for given disputes from fallback storage."""

    tracked_ids = {int(row_id) for row_id in dispute_ids}
    upvotes = Counter()
    downvotes = Counter()
    for row in _load_fallback_reactions():
        dispute_id = int(row.get("dispute_id", -1))
        if dispute_id not in tracked_ids:
            continue
        value = int(row.get("value", 0))
        if value > 0:
            upvotes[dispute_id] += 1
        elif value < 0:
            downvotes[dispute_id] += 1
    return upvotes, downvotes


def _user_reaction_lookup(user_id, dispute_ids):
    """Returns current user's existing reaction per dispute id from fallback storage."""

    tracked_ids = {int(row_id) for row_id in dispute_ids}
    lookup = {}
    for row in _load_fallback_reactions():
        if int(row.get("user_id", -1)) != int(user_id):
            continue
        dispute_id = int(row.get("dispute_id", -1))
        if dispute_id not in tracked_ids:
            continue
        lookup[dispute_id] = int(row.get("value", 0))
    return lookup


def _upsert_fallback_reaction(dispute_id, user_id, value):
    """Creates or updates one user's engagement vote for a dispute and returns fresh totals."""

    rows = _load_fallback_reactions()
    updated = False
    now_iso = datetime.utcnow().isoformat()

    for row in rows:
        if int(row.get("dispute_id", -1)) == int(dispute_id) and int(row.get("user_id", -1)) == int(user_id):
            row["value"] = int(value)
            row["updated_at"] = now_iso
            updated = True
            break

    if not updated:
        next_id = max([int(row.get("id", 0)) for row in rows] + [0]) + 1
        rows.append(
            {
                "id": next_id,
                "dispute_id": int(dispute_id),
                "user_id": int(user_id),
                "value": int(value),
                "created_at": now_iso,
                "updated_at": now_iso,
            }
        )

    _save_fallback_reactions(rows)

    upvotes = 0
    downvotes = 0
    for row in rows:
        if int(row.get("dispute_id", -1)) != int(dispute_id):
            continue
        row_value = int(row.get("value", 0))
        if row_value > 0:
            upvotes += 1
        elif row_value < 0:
            downvotes += 1
    return upvotes, downvotes


def _comment_counts_for_disputes(dispute_ids):
    """Builds comment counters per dispute from DB comments or fallback comments."""

    tracked_ids = [int(row_id) for row_id in dispute_ids]
    counts = Counter()
    if not tracked_ids:
        return counts

    if _comments_available():
        try:
            rows = (
                db.session.query(Comment.dispute_id, func.count(Comment.id))
                .filter(Comment.dispute_id.in_(tracked_ids))
                .group_by(Comment.dispute_id)
                .all()
            )
            for dispute_id, total in rows:
                counts[int(dispute_id)] = int(total or 0)
            return counts
        except SQLAlchemyError:
            pass

    tracked_set = set(tracked_ids)
    for row in _load_fallback_comments():
        dispute_id = int(row.get("dispute_id", -1))
        if dispute_id in tracked_set:
            counts[dispute_id] += 1
    return counts


@disputes_bp.route("/disputes", methods=["GET"])
def list_disputes():
    """Lists public disputes for the home/disputes page with optional search."""

    sort_by = (request.args.get("sort") or "recent").strip().lower()
    if sort_by not in {"recent", "popular", "discussed"}:
        sort_by = "recent"

    search_term = (request.args.get("search") or "").strip()

    query = Dispute.query.filter_by(is_public=True)
    if search_term:
        search_pattern = f"%{search_term}%"
        query = query.filter(
            (Dispute.title.ilike(search_pattern)) |
            (Dispute.description.ilike(search_pattern))
        )
    disputes = query.order_by(Dispute.created_at.desc()).all()
    dispute_ids = [row.id for row in disputes]
    upvote_counts, downvote_counts = _reaction_counts_for_disputes(dispute_ids)
    comment_counts = _comment_counts_for_disputes(dispute_ids)

    user_reactions = {}
    if current_user.is_authenticated:
        user_reactions = _user_reaction_lookup(current_user.id, dispute_ids)

    feed_cards = []
    for dispute in disputes:
        upvotes = int(upvote_counts.get(dispute.id, 0))
        downvotes = int(downvote_counts.get(dispute.id, 0))
        comments_count = int(comment_counts.get(dispute.id, 0))
        feed_cards.append(
            {
                "dispute": dispute,
                "upvotes": upvotes,
                "downvotes": downvotes,
                "comments_count": comments_count,
                "score": upvotes - downvotes,
                "user_vote": int(user_reactions.get(dispute.id, 0)),
            }
        )

    if sort_by == "popular":
        feed_cards.sort(
            key=lambda row: (
                row["score"],
                row["comments_count"],
                row["dispute"].created_at or datetime.min,
            ),
            reverse=True,
        )
    elif sort_by == "discussed":
        feed_cards.sort(
            key=lambda row: (
                row["comments_count"],
                row["score"],
                row["dispute"].created_at or datetime.min,
            ),
            reverse=True,
        )

    return render_template("dispute_view.html", disputes=disputes, feed_cards=feed_cards, sort_by=sort_by, search_term=search_term)


@disputes_bp.route("/dispute/<int:dispute_id>/engagement-vote", methods=["POST"])
@login_required
def cast_dispute_engagement_vote(dispute_id):
    """Stores one spectator engagement vote (+1/-1) for a dispute card."""

    if current_user.role != "spectator":
        return jsonify({"error": "Only spectators can vote on dispute engagement"}), 403

    dispute = Dispute.query.get_or_404(dispute_id)
    if not dispute.is_public:
        return jsonify({"error": "Engagement voting is allowed only on public disputes"}), 403

    data = _payload()
    try:
        value = int(data.get("value"))
    except (TypeError, ValueError):
        return jsonify({"error": "value must be 1 or -1"}), 400

    if value not in {-1, 1}:
        return jsonify({"error": "value must be 1 or -1"}), 400

    upvotes, downvotes = _upsert_fallback_reaction(dispute.id, current_user.id, value)
    return jsonify(
        {
            "message": "Engagement vote saved",
            "upvotes": upvotes,
            "downvotes": downvotes,
            "score": upvotes - downvotes,
            "user_vote": value,
        }
    ), 200


@disputes_bp.route("/dispute/<int:dispute_id>/report", methods=["POST"])
@login_required
def report_dispute(dispute_id):
    """Stores a report, marks the dispute as reported, and escalates on threshold.
    
    Private disputes cannot be reported by participants (reports restricted to maintain
    integrity of private interactions). Only public disputes accept community reports.
    """

    if current_user.role != "spectator":
        return jsonify({"error": "Only spectators can report disputes"}), 403

    dispute = Dispute.query.get_or_404(dispute_id)
    
    # Check if dispute is private - reports are not allowed for private disputes
    if dispute.is_private():
        return jsonify({"error": "Reports are not allowed for private disputes. Contact admin for moderation concerns."}), 403
    
    if current_user.id in [dispute.created_by, dispute.invited_user]:
        return jsonify({"error": "Participants cannot report their own disputes"}), 403

    data = _payload()
    reason = (data.get("reason") or "").strip().lower()
    details = (data.get("details") or "").strip()

    if reason not in REPORT_REASON_LABELS:
        return jsonify({"error": "A valid report reason is required"}), 400

    existing = DisputeReport.query.filter_by(dispute_id=dispute.id, reporter_user_id=current_user.id).first()
    if existing:
        return jsonify({"error": "You have already reported this dispute"}), 400

    try:
        report = DisputeReport(
            dispute_id=dispute.id,
            reporter_user_id=current_user.id,
            reason=reason,
            details=details,
            is_system_flag=False,
        )
        db.session.add(report)
        db.session.flush()

        report_count = DisputeReport.query.filter_by(dispute_id=dispute.id, is_system_flag=False).count()
        is_escalated = report_count >= REPORT_ESCALATION_THRESHOLD
        dispute.status = "flagged" if is_escalated else "reported"
        dispute.review_state = "under_review" if is_escalated else "under_observation"
        db.session.add(
            AdminLog(
                dispute_id=dispute.id,
                admin_user_id=None,
                action_type="dispute_reported",
                reason=f"@{current_user.username} reported dispute as {REPORT_REASON_LABELS[reason]}. Total reports: {report_count}.",
            )
        )
        db.session.commit()

        summary = _dispute_report_summary(dispute.id)
        return jsonify(
            {
                "message": "Report submitted",
                "dispute_status": dispute.status,
                "report_count": summary["count"],
                "threshold": REPORT_ESCALATION_THRESHOLD,
                "reports": [
                    {
                        "reason": row.reason,
                        "reason_label": REPORT_REASON_LABELS.get(row.reason, row.reason),
                        "details": row.details,
                        "reporter": row.reporter.username if row.reporter else "Unknown",
                        "created_at": row.created_at.isoformat() if row.created_at else None,
                    }
                    for row in summary["rows"]
                ],
            }
        ), 201
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": f"Report failed: {exc}"}), 500


@disputes_bp.route("/dispute/create", methods=["GET"])
@login_required
def create_dispute_page():
    """Renders create dispute page."""

    if current_user.role != "disputant":
        return redirect(url_for("disputes.list_disputes"))

    return render_template("create_dispute.html")


@disputes_bp.route("/dispute/create", methods=["POST"])
@login_required
def create_dispute():
    """Creates a dispute and invites an opponent by username."""

    if current_user.role != "disputant":
        return jsonify({"error": "Only disputants can create disputes"}), 403

    data = _payload()
    title = (data.get("title") or "").strip()
    description = (data.get("description") or "").strip()
    opponent_username = (data.get("opponent_username") or "").strip()
    moderation_mode = (data.get("moderation_mode") or "public").strip().lower()

    if not title or not opponent_username:
        return jsonify({"error": "title and opponent_username are required"}), 400

    if moderation_mode not in ["public", "private"]:
        return jsonify({"error": "moderation_mode must be 'public' or 'private'"}), 400

    opponent = User.query.filter_by(username=opponent_username).first()
    if not opponent:
        return jsonify({"error": "Invited user not found"}), 404

    if opponent.id == current_user.id:
        return jsonify({"error": "You cannot invite yourself"}), 400

    dispute = Dispute(
        title=title,
        description=description,
        created_by=current_user.id,
        invited_user=opponent.id,
        status="waiting",
        is_public=True,
        moderation_mode=moderation_mode,
        created_at=datetime.now(),
    )

    try:
        db.session.add(dispute)
        db.session.commit()
        unlocked_badges = []
        try:
            unlocked_badges = refresh_user_badges(current_user.id)
        except Exception:
            db.session.rollback()
        return jsonify({"message": "Dispute created", "dispute_id": dispute.id, "unlocked_badges": unlocked_badges}), 201
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": f"Failed to create dispute: {exc}"}), 500


@disputes_bp.route("/dispute/<int:dispute_id>", methods=["GET"])
@login_required
def get_dispute(dispute_id):
    """Shows a dispute page where disputants can submit arguments."""

    dispute = Dispute.query.get_or_404(dispute_id)
    submissions = Submission.query.filter_by(dispute_id=dispute.id).order_by(Submission.submitted_at.asc()).all()
    appeal_rows = Appeal.query.filter_by(dispute_id=dispute.id).order_by(Appeal.submitted_at.asc()).all()
    comments = []
    if _comments_available():
        try:
            comments = Comment.query.filter_by(dispute_id=dispute.id).order_by(Comment.created_at.desc()).limit(100).all()
        except SQLAlchemyError:
            comments = _fallback_template_comments(dispute.id)
    else:
        comments = _fallback_template_comments(dispute.id)

    if AIResult.query.filter_by(dispute_id=dispute.id).first():
        return redirect(url_for("disputes.get_verdict", dispute_id=dispute.id))

    latest_appeal = appeal_rows[-1] if appeal_rows else None
    report_summary = _dispute_report_summary(dispute.id)

    # Recovery path: if a moderator-approved appeal reopened the case but verdict
    # rerun did not complete (deploy/restart timing), rerun it on next page load.
    if dispute.status == "active" and latest_appeal and latest_appeal.status == "approved" and len(submissions) >= 2:
        existing_ai = AIResult.query.filter_by(dispute_id=dispute.id).first()
        if existing_ai:
            dispute.status = "resolved"
            if not dispute.resolved_at:
                dispute.resolved_at = datetime.utcnow()
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
            return redirect(url_for("disputes.get_verdict", dispute_id=dispute.id))

        user_a = submissions[0].user
        user_b = submissions[1].user
        appeal_context = (dispute.moderator_note or latest_appeal.admin_response or latest_appeal.reason_text or "").strip()
        prior_verdict_context = None
        pipeline_result = run_full_pipeline(
            dispute_id=dispute.id,
            text_a=submissions[0].argument_text,
            text_b=submissions[1].argument_text,
            user_a_name=user_a.username,
            user_b_name=user_b.username,
            appeal_context=appeal_context,
            prior_verdict_context=prior_verdict_context,
        )

        if pipeline_result.get("status") == "resolved":
            verdict = pipeline_result["verdict"]
            winner_user_id = user_a.id if verdict.get("winner") == "A" else user_b.id
            ai_result = AIResult(
                dispute_id=dispute.id,
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
                dispute.status = "resolved"
                dispute.resolved_at = datetime.utcnow()
                db.session.commit()
                return redirect(url_for("disputes.get_verdict", dispute_id=dispute.id))
            except Exception:
                db.session.rollback()

        if pipeline_result.get("status") == "flagged":
            dispute.status = "flagged"
            try:
                db.session.add(AdminLog(dispute_id=dispute.id, action_type="appeal_rerun_flagged", reason=pipeline_result.get("message", "Appeal rerun flagged")))
                db.session.commit()
            except Exception:
                db.session.rollback()

    return render_template(
        "dispute_view.html",
        dispute=dispute,
        submissions=submissions,
        comments=comments,
        latest_appeal=latest_appeal,
        appeal_rows=appeal_rows,
        report_summary=report_summary,
        report_reason_labels=REPORT_REASON_LABELS,
        report_threshold=REPORT_ESCALATION_THRESHOLD,
    )


@disputes_bp.route("/dispute/<int:dispute_id>/state", methods=["GET"])
@login_required
def dispute_state(dispute_id):
    """Returns lightweight live state for polling UI updates on dispute page."""

    dispute = Dispute.query.get_or_404(dispute_id)
    submissions = Submission.query.filter_by(dispute_id=dispute.id).order_by(Submission.submitted_at.asc()).all()
    return jsonify(
        {
            "dispute_id": dispute.id,
            "status": dispute.status,
            "submissions_count": len(submissions),
            "has_verdict": dispute.status == "resolved",
            "verdict_url": url_for("disputes.get_verdict", dispute_id=dispute.id),
        }
    ), 200


@disputes_bp.route("/dispute/<int:dispute_id>/submit", methods=["POST"])
@login_required
def submit_argument(dispute_id):
    """Stores one user submission, then auto-runs AI when both sides have submitted."""

    dispute = Dispute.query.get_or_404(dispute_id)
    if current_user.role != "disputant":
        return jsonify({"error": "Only disputants can submit arguments"}), 403

    if current_user.id not in [dispute.created_by, dispute.invited_user]:
        return jsonify({"error": "Only disputants can submit arguments"}), 403

    data = _payload()
    argument_text = (data.get("argument_text") or "").strip()
    if not argument_text:
        return jsonify({"error": "argument_text is required"}), 400

    existing = Submission.query.filter_by(dispute_id=dispute.id, user_id=current_user.id).first()
    if existing:
        return jsonify({"error": "You have already submitted for this dispute"}), 400

    submission = Submission(dispute_id=dispute.id, user_id=current_user.id, argument_text=argument_text)

    try:
        db.session.add(submission)
        db.session.commit()
        unlocked_badges = []
        try:
            unlocked_badges = refresh_user_badges(current_user.id)
        except Exception:
            db.session.rollback()
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": f"Submission failed: {exc}"}), 500

    submissions = Submission.query.filter_by(dispute_id=dispute.id).order_by(Submission.id.asc()).all()
    if len(submissions) < 2:
        try:
            dispute.status = "active"
            db.session.commit()
        except Exception:
            db.session.rollback()
        return jsonify({"message": "Submission saved. Waiting for opponent.", "unlocked_badges": unlocked_badges}), 201

    user_a = submissions[0].user
    user_b = submissions[1].user

    pipeline_result = run_full_pipeline(
        dispute_id=dispute.id,
        text_a=submissions[0].argument_text,
        text_b=submissions[1].argument_text,
        user_a_name=user_a.username,
        user_b_name=user_b.username,
    )

    if pipeline_result["status"] == "error":
        return jsonify(pipeline_result), 500

    if pipeline_result["status"] == "flagged":
        try:
            dispute.status = "flagged"
            db.session.add(AdminLog(dispute_id=dispute.id, action_type="flagged", reason=pipeline_result["message"]))
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            return jsonify({"error": f"Failed to flag dispute: {exc}"}), 500
        response = dict(pipeline_result)
        response["unlocked_badges"] = unlocked_badges
        return jsonify(response), 200

    verdict = pipeline_result["verdict"]
    winner_user_id = user_a.id if verdict.get("winner") == "A" else user_b.id

    ai_result = AIResult(
        dispute_id=dispute.id,
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
        dispute.status = "resolved"
        dispute.resolved_at = datetime.utcnow()
        db.session.commit()
        participant_ids = {submissions[0].user_id, submissions[1].user_id}
        for participant_id in participant_ids:
            try:
                new_badges = refresh_user_badges(participant_id)
                if participant_id == current_user.id:
                    unlocked_badges = _merge_unlocked_badges(unlocked_badges, new_badges)
            except Exception:
                db.session.rollback()
        return jsonify({"message": "Submission saved and dispute resolved", "verdict": verdict, "unlocked_badges": unlocked_badges}), 201
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": f"Failed to persist AI result: {exc}"}), 500


@disputes_bp.route("/dispute/<int:dispute_id>/verdict", methods=["GET"])
@login_required
def get_verdict(dispute_id):
    """Displays a verdict page for resolved disputes."""

    dispute = Dispute.query.get_or_404(dispute_id)
    ai_result = AIResult.query.filter_by(dispute_id=dispute.id).first()
    if not ai_result:
        return jsonify({"error": "Verdict not available yet"}), 404

    submissions = Submission.query.filter_by(dispute_id=dispute.id).order_by(Submission.id.asc()).all()
    comments = []
    if _comments_available():
        try:
            comments = Comment.query.filter_by(dispute_id=dispute.id).order_by(Comment.created_at.desc()).limit(100).all()
        except SQLAlchemyError:
            comments = _fallback_template_comments(dispute.id)
    else:
        comments = _fallback_template_comments(dispute.id)
    votes = {s.user_id: 0 for s in submissions}
    for vote in dispute.votes:
        votes[vote.voted_for_user_id] = votes.get(vote.voted_for_user_id, 0) + 1

    fallacies_a_display = _map_fallacies_for_display(ai_result.fallacies_a)
    fallacies_b_display = _map_fallacies_for_display(ai_result.fallacies_b)

    summaries_by_user = {}
    for submission in submissions:
        summaries_by_user[submission.user_id] = _argument_summary(submission.argument_text)

    timeline_events = [
        {
            "kind": "created",
            "label": f"Dispute created by {dispute.creator.username if dispute.creator else 'Unknown'}",
            "when": dispute.created_at,
        }
    ]
    for submission in submissions:
        timeline_events.append(
            {
                "kind": "submitted",
                "label": f"Argument submitted by {submission.user.username}",
                "when": submission.submitted_at,
            }
        )
    if dispute.resolved_at:
        winner_name = ai_result.winner.username if ai_result.winner else "Unknown"
        timeline_events.append(
            {
                "kind": "verdict",
                "label": f"AI verdict: {winner_name} wins",
                "when": dispute.resolved_at,
            }
        )
    appeal_rows = Appeal.query.filter_by(dispute_id=dispute.id).order_by(Appeal.submitted_at.asc()).all()
    latest_appeal = appeal_rows[-1] if appeal_rows else None
    approved_appeal = next((appeal for appeal in reversed(appeal_rows) if appeal.status == "approved"), None)
    report_summary = _dispute_report_summary(dispute.id)
    previous_winner_name = ""
    winner_changed_via_appeal = False
    latest_approved_log = (
        AdminLog.query.filter_by(dispute_id=dispute.id, action_type="appeal_approved")
        .order_by(AdminLog.created_at.desc())
        .first()
    )
    if latest_approved_log and latest_approved_log.reason:
        match = re.search(r"Previous winner:\s*@?([A-Za-z0-9_.-]+)", latest_approved_log.reason)
        if match:
            previous_winner_name = match.group(1).strip()
    if previous_winner_name and ai_result.winner:
        winner_changed_via_appeal = previous_winner_name.lower() != ai_result.winner.username.lower()
    for appeal in appeal_rows:
        timeline_events.append(
            {
                "kind": "appeal",
                "label": (
                    f"Appeal {appeal.status} by {appeal.appellant.username if appeal.appellant else 'User'}"
                    if appeal.status != "pending"
                    else f"Appeal filed by {appeal.appellant.username if appeal.appellant else 'User'}"
                ),
                "when": appeal.submitted_at,
            }
        )
        if appeal.status == "approved" and appeal.reviewed_at:
            timeline_events.append(
                {
                    "kind": "appeal",
                    "label": "Result changed via Moderator Appeal",
                    "when": appeal.reviewed_at,
                }
            )
    timeline_events.sort(key=lambda item: item["when"] or datetime.utcnow())

    submissions_by_index = submissions[:2]
    could_have_won_tip = ""
    if len(submissions_by_index) == 2 and ai_result.winner_user_id:
        loser_submission = submissions_by_index[0] if submissions_by_index[0].user_id != ai_result.winner_user_id else submissions_by_index[1]
        if loser_submission.user_id == submissions_by_index[0].user_id:
            loser_fallacies = fallacies_a_display
            loser_toxicity = float(ai_result.toxicity_score_a)
            loser_sarcasm = float(ai_result.sarcasm_score_a)
        else:
            loser_fallacies = fallacies_b_display
            loser_toxicity = float(ai_result.toxicity_score_b)
            loser_sarcasm = float(ai_result.sarcasm_score_b)
        could_have_won_tip = _could_have_won_tip(
            loser_submission.user.username,
            loser_fallacies,
            loser_toxicity,
            loser_sarcasm,
        )

    participant_ids = {dispute.created_by, dispute.invited_user}
    can_appeal = (
        current_user.is_authenticated
        and current_user.role == "disputant"
        and current_user.id in participant_ids
        and ai_result.winner_user_id != current_user.id
    )
    can_report = (
        current_user.is_authenticated
        and current_user.role == "spectator"
        and current_user.id not in participant_ids
    )

    return render_template(
        "verdict.html",
        dispute=dispute,
        ai_result=ai_result,
        submissions=submissions,
        comments=comments,
        vote_counts=votes,
        fallacies_a_display=fallacies_a_display,
        fallacies_b_display=fallacies_b_display,
        summaries_by_user=summaries_by_user,
        timeline_events=timeline_events,
        could_have_won_tip=could_have_won_tip,
        appeal_rows=appeal_rows,
        latest_appeal=latest_appeal,
        approved_appeal=approved_appeal,
        previous_winner_name=previous_winner_name,
        winner_changed_via_appeal=winner_changed_via_appeal,
        report_summary=report_summary,
        report_reason_labels=REPORT_REASON_LABELS,
        report_threshold=REPORT_ESCALATION_THRESHOLD,
        can_appeal=can_appeal,
        can_report=can_report,
    )


@disputes_bp.route("/dispute/<int:dispute_id>/comments", methods=["GET"])
@login_required
def get_comments(dispute_id):
    """Returns the most recent public comments for a dispute."""

    dispute = Dispute.query.get_or_404(dispute_id)
    if not dispute.is_public:
        if current_user.id not in [dispute.created_by, dispute.invited_user] and current_user.role != "admin":
            return jsonify({"error": "Comments are unavailable for this dispute"}), 403

    if not _comments_available():
        return jsonify({"comments": [_serialize_comment(row) for row in _fallback_api_comments(dispute.id)], "storage": "fallback"}), 200

    try:
        comments = Comment.query.filter_by(dispute_id=dispute.id).order_by(Comment.created_at.desc()).limit(100).all()
        return jsonify({"comments": [_serialize_comment(row) for row in comments]}), 200
    except SQLAlchemyError:
        return jsonify({"comments": [_serialize_comment(row) for row in _fallback_api_comments(dispute.id)], "storage": "fallback"}), 200


@disputes_bp.route("/dispute/<int:dispute_id>/comments", methods=["POST"])
@login_required
def create_comment(dispute_id):
    """Creates a public comment for a dispute."""

    dispute = Dispute.query.get_or_404(dispute_id)
    if not dispute.is_public:
        if current_user.id not in [dispute.created_by, dispute.invited_user] and current_user.role != "admin":
            return jsonify({"error": "You cannot comment on this dispute"}), 403

    data = _payload()
    body = (data.get("body") or "").strip()
    if not body:
        return jsonify({"error": "Comment text is required"}), 400
    if len(body) > 1000:
        return jsonify({"error": "Comment must be 1000 characters or less"}), 400

    if not _comments_available():
        row = _create_fallback_comment(dispute.id, current_user.id, current_user.username, body)
        return jsonify({"message": "Comment posted", "comment": _serialize_comment(row), "storage": "fallback"}), 201

    comment = Comment(dispute_id=dispute.id, user_id=current_user.id, body=body)
    try:
        db.session.add(comment)
        db.session.commit()
        return jsonify({"message": "Comment posted", "comment": _serialize_comment(comment)}), 201
    except SQLAlchemyError:
        db.session.rollback()
        row = _create_fallback_comment(dispute.id, current_user.id, current_user.username, body)
        return jsonify({"message": "Comment posted", "comment": _serialize_comment(row), "storage": "fallback"}), 201
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": f"Failed to post comment: {exc}"}), 500


@disputes_bp.route("/dispute/<int:dispute_id>/appeal", methods=["POST"])
@login_required
def create_appeal(dispute_id):
    """Allows a disputant to file an appeal on a resolved dispute.
    
    Appeals are restricted to participants only, and only after a final decision is made.
    This applies to both public and private disputes to ensure fairness.
    """

    dispute = Dispute.query.get_or_404(dispute_id)
    ai_result = AIResult.query.filter_by(dispute_id=dispute.id).first()
    if not ai_result:
        return jsonify({"error": "Appeals are only available after a verdict"}), 400

    if current_user.role != "disputant":
        return jsonify({"error": "Only disputants can appeal"}), 403

    # Verify the user is a participant in this dispute
    if not dispute.is_participant(current_user.id):
        return jsonify({"error": "Only participants in this dispute can appeal"}), 403

    if ai_result.winner_user_id == current_user.id:
        return jsonify({"error": "Only the losing side can appeal"}), 403

    data = _payload()
    reason_text = (data.get("reason_text") or "").strip()
    if not reason_text:
        return jsonify({"error": "reason_text is required"}), 400

    try:
        appeal = Appeal(dispute_id=dispute.id, appellant_user_id=current_user.id, reason_text=reason_text)
        db.session.add(appeal)
        db.session.commit()
        unlocked_badges = []
        try:
            unlocked_badges = refresh_user_badges(current_user.id)
        except Exception:
            db.session.rollback()
        return jsonify({"message": "Appeal submitted", "unlocked_badges": unlocked_badges}), 201
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": f"Failed to submit appeal: {exc}"}), 500


@disputes_bp.route("/leaderboard", methods=["GET"])
def leaderboard_page():
    """Shows ranked users by AI wins with chart-ready data."""

    period = (request.args.get("period") or "all").strip().lower()
    if period not in {"all", "month", "week"}:
        period = "all"

    now = datetime.utcnow()
    cutoff = None
    if period == "month":
        cutoff = now - timedelta(days=30)
    elif period == "week":
        cutoff = now - timedelta(days=7)

    dispute_filters = [Dispute.status == "resolved"]
    if cutoff is not None:
        dispute_filters.append(Dispute.resolved_at.isnot(None))
        dispute_filters.append(Dispute.resolved_at >= cutoff)

    wins_query = db.session.query(
        AIResult.winner_user_id.label("user_id"),
        func.count(AIResult.id).label("wins"),
    ).join(Dispute, AIResult.dispute_id == Dispute.id)
    if dispute_filters:
        wins_query = wins_query.filter(*dispute_filters)
    wins_sq = wins_query.group_by(AIResult.winner_user_id).subquery()

    created_sq = db.session.query(Dispute.created_by.label("user_id")).filter(*dispute_filters)
    invited_sq = db.session.query(Dispute.invited_user.label("user_id")).filter(
        *dispute_filters,
        Dispute.invited_user.isnot(None),
    )
    participants_sq = created_sq.union_all(invited_sq).subquery()
    totals_sq = (
        db.session.query(
            participants_sq.c.user_id.label("user_id"),
            func.count().label("total"),
        )
        .group_by(participants_sq.c.user_id)
        .subquery()
    )

    base_query = (
        db.session.query(
            User.id,
            User.username,
            User.reputation_score,
            func.coalesce(wins_sq.c.wins, 0).label("wins"),
            func.coalesce(totals_sq.c.total, 0).label("total"),
        )
        .outerjoin(wins_sq, wins_sq.c.user_id == User.id)
        .outerjoin(totals_sq, totals_sq.c.user_id == User.id)
        .order_by(func.coalesce(wins_sq.c.wins, 0).desc(), User.reputation_score.desc(), User.username.asc())
    )

    rows = (
        base_query
        .limit(10)
        .all()
    )

    leaderboard = []
    for idx, row in enumerate(rows, start=1):
        wins = int(row.wins or 0)
        total = int(row.total or 0)
        win_rate = round((wins / total) * 100) if total else 0
        leaderboard.append(
            {
                "rank": idx,
                "user_id": row.id,
                "username": row.username,
                "wins": wins,
                "total": total,
                "win_rate": win_rate,
                "reputation_score": int(row.reputation_score or 0),
            }
        )

    your_position = None
    if current_user.is_authenticated:
        all_rows = base_query.all()
        for idx, row in enumerate(all_rows, start=1):
            if row.id != current_user.id:
                continue
            wins = int(row.wins or 0)
            total = int(row.total or 0)
            your_position = {
                "rank": idx,
                "user_id": row.id,
                "username": row.username,
                "wins": wins,
                "total": total,
                "win_rate": round((wins / total) * 100) if total else 0,
                "reputation_score": int(row.reputation_score or 0),
            }
            break

    return render_template(
        "leaderboard.html",
        leaderboard=leaderboard,
        period=period,
        your_position=your_position,
    )


@disputes_bp.route("/statistics", methods=["GET"])
def statistics_page():
    """Shows aggregate dispute and AI statistics with chart datasets."""

    period = (request.args.get("period") or "30d").strip().lower()
    if period not in {"7d", "30d", "all"}:
        period = "30d"

    today = datetime.utcnow().date()
    cutoff_dt = None
    days_for_chart = 30
    if period == "7d":
        cutoff_dt = datetime.utcnow() - timedelta(days=7)
        days_for_chart = 7
    elif period == "30d":
        cutoff_dt = datetime.utcnow() - timedelta(days=30)
        days_for_chart = 30
    else:
        days_for_chart = 30

    dispute_query = Dispute.query
    resolved_dispute_query = Dispute.query.filter(Dispute.status == "resolved")
    ai_result_query = AIResult.query
    if cutoff_dt is not None:
        dispute_query = dispute_query.filter(Dispute.created_at >= cutoff_dt)
        resolved_dispute_query = resolved_dispute_query.filter(
            Dispute.resolved_at.isnot(None),
            Dispute.resolved_at >= cutoff_dt,
        )
        ai_result_query = ai_result_query.filter(AIResult.created_at >= cutoff_dt)

    total_disputes = dispute_query.count()
    total_verdicts = resolved_dispute_query.count()
    avg_conf = ai_result_query.with_entities(func.avg(AIResult.confidence_score)).scalar() or 0
    avg_confidence_pct = round(float(avg_conf) * 100, 1)

    ai_results = ai_result_query.all()
    fallacy_counter = Counter()
    fallacy_examples = {}

    def _fallacy_category(raw_label):
        text = str(raw_label or "").strip()
        lower = text.lower()

        if "ad hominem" in lower or "person" in lower and "argument" in lower:
            return "Ad Hominem"
        if "strawman" in lower or "twisted" in lower or "misrepresent" in lower:
            return "Strawman"
        if "false dichotomy" in lower or "only two options" in lower or "two options" in lower:
            return "False Dichotomy"
        if "appeal to emotion" in lower or "emotion" in lower or "feelings" in lower:
            return "Appeal to Emotion"
        if "hasty generalization" in lower or "broad conclusion" in lower or "limited evidence" in lower:
            return "Hasty Generalization"

        if "(" in text:
            text = text.split("(", 1)[0].strip()
        return text or "Other"
    toxicity_values = []
    for row in ai_results:
        toxicity_values.append(float(row.toxicity_score_a))
        toxicity_values.append(float(row.toxicity_score_b))
        for item in (row.fallacies_a or []):
            category = _fallacy_category(item)
            fallacy_counter[category] += 1
            fallacy_examples.setdefault(category, str(item))
        for item in (row.fallacies_b or []):
            category = _fallacy_category(item)
            fallacy_counter[category] += 1
            fallacy_examples.setdefault(category, str(item))

    avg_toxicity_pct = round((sum(toxicity_values) / len(toxicity_values)) * 100, 1) if toxicity_values else 0.0

    day_labels = []
    day_counts = []
    for offset in range(days_for_chart - 1, -1, -1):
        day = today - timedelta(days=offset)
        day_labels.append(day.strftime("%b %d"))
        count = dispute_query.filter(func.date(Dispute.created_at) == day).count()
        day_counts.append(count)

    top_fallacies = fallacy_counter.most_common(5)
    fallacy_label_map = {
        "Ad Hominem": "Ad Hominem",
        "Strawman": "Strawman",
        "False Dichotomy": "Dichotomy",
        "Appeal to Emotion": "Emotion",
        "Hasty Generalization": "Generalization",
    }
    fallacy_labels = [fallacy_label_map.get(name, name) for name, _ in top_fallacies]
    fallacy_full_labels = [fallacy_examples.get(name, name) for name, _ in top_fallacies]
    fallacy_counts = [count for _, count in top_fallacies]

    agreement_total = 0
    agreement_match = 0
    resolved_disputes = resolved_dispute_query.all()
    for dispute in resolved_disputes:
        if not dispute.ai_result:
            continue
        vote_counter = Counter(v.voted_for_user_id for v in dispute.votes)
        if not vote_counter:
            continue
        top_count = max(vote_counter.values())
        top_users = [uid for uid, count in vote_counter.items() if count == top_count]
        if len(top_users) != 1:
            continue
        agreement_total += 1
        if top_users[0] == dispute.ai_result.winner_user_id:
            agreement_match += 1

    agreement_pct = round((agreement_match / agreement_total) * 100, 1) if agreement_total else 0.0
    disagreement_pct = round(100 - agreement_pct, 1) if agreement_total else 0.0
    agreement_has_votes = agreement_total > 0

    return render_template(
        "statistics.html",
        period=period,
        total_disputes=total_disputes,
        total_verdicts=total_verdicts,
        avg_confidence_pct=avg_confidence_pct,
        avg_toxicity_pct=avg_toxicity_pct,
        activity_labels=day_labels,
        activity_counts=day_counts,
        fallacy_labels=fallacy_labels,
        fallacy_full_labels=fallacy_full_labels,
        fallacy_counts=fallacy_counts,
        agreement_pct=agreement_pct,
        disagreement_pct=disagreement_pct,
        agreement_total=agreement_total,
        agreement_has_votes=agreement_has_votes,
    )
