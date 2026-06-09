"""Authentication and user profile routes for VerdictBox."""

from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.exc import IntegrityError
from collections import Counter
from core.extensions import db
from core.models import User, Dispute, UserBadge, AIResult, Badge, Notification
from core.badges_engine import BADGE_DEFINITIONS, refresh_user_badges


auth_bp = Blueprint("auth", __name__)


def _payload():
    """Returns JSON body when present, otherwise form data."""

    return request.get_json(silent=True) or request.form


@auth_bp.route("/")
def home():
    """Renders landing page with quick stats."""

    stats = {
        "total_users": User.query.count(),
        "total_disputes": Dispute.query.count(),
        "total_verdicts": Dispute.query.filter_by(status="resolved").count(),
    }
    recent_disputes = (
        Dispute.query.filter_by(is_public=True)
        .order_by(Dispute.created_at.desc())
        .limit(8)
        .all()
    )
    recent_verdicts = (
        AIResult.query.join(Dispute, AIResult.dispute_id == Dispute.id)
        .filter(Dispute.is_public.is_(True))
        .order_by(AIResult.created_at.desc())
        .limit(6)
        .all()
    )
    return render_template(
        "index.html",
        stats=stats,
        recent_disputes=recent_disputes,
        recent_verdicts=recent_verdicts,
    )


@auth_bp.route("/register", methods=["GET"])
def register_page():
    """Renders registration page."""

    return render_template("register.html")


@auth_bp.route("/register", methods=["POST"])
def register():
    """Creates a new user with hashed password and uniqueness checks."""

    data = _payload()
    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    requested_role = (data.get("role") or "spectator").strip().lower()

    if not username or not email or not password:
        return jsonify({"error": "username, email, and password are required"}), 400

    if requested_role not in {"disputant", "spectator"}:
        return jsonify({"error": "role must be disputant or spectator"}), 400

    user = User(username=username, email=email, password_hash=generate_password_hash(password), role=requested_role)

    try:
        db.session.add(user)
        db.session.commit()
        return jsonify({"message": "User registered successfully"}), 201
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Username or email already exists"}), 400
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": f"Registration failed: {exc}"}), 500


@auth_bp.route("/login", methods=["GET"])
def login_page():
    """Renders login page."""

    return render_template("login.html")


@auth_bp.route("/login", methods=["POST"])
def login():
    """Logs in an active user after password hash verification."""

    data = _payload()
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if not username or not password:
        return jsonify({"error": "username and password are required"}), 400

    user = User.query.filter_by(username=username).first()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"error": "Invalid credentials"}), 403
    if not user.is_active:
        return jsonify({"error": "Account is inactive"}), 403

    login_user(user)
    if user.role == "admin":
        redirect_url = url_for("admin.admin_dashboard")
    elif user.role == "spectator":
        redirect_url = url_for("disputes.list_disputes")
    else:
        redirect_url = url_for("auth.dashboard")
    return jsonify({"message": "Login successful", "role": user.role, "redirect_url": redirect_url}), 200


@auth_bp.route("/logout", methods=["GET"])
@login_required
def logout():
    """Logs out the current user."""

    logout_user()
    flash("Logged out successfully.", "info")
    return redirect(url_for("auth.login_page"))


@auth_bp.route("/account/switch-role", methods=["POST"])
@login_required
def switch_role():
    """Allows users to switch between disputant and spectator roles."""

    if current_user.role == "admin":
        return jsonify({"error": "Admin role cannot be changed from account settings"}), 403

    data = _payload()
    requested_role = (data.get("role") or "").strip().lower()
    allowed_roles = {"disputant", "spectator"}

    if requested_role and requested_role not in allowed_roles:
        return jsonify({"error": "role must be disputant or spectator"}), 400

    target_role = requested_role or ("spectator" if current_user.role == "disputant" else "disputant")
    if target_role == current_user.role:
        return jsonify({"message": "Role unchanged", "role": current_user.role}), 200

    try:
        current_user.role = target_role
        db.session.commit()
        return jsonify({"message": f"Role switched to {target_role}", "role": target_role}), 200
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": f"Failed to switch role: {exc}"}), 500


@auth_bp.route("/dashboard", methods=["GET"])
@login_required
def dashboard():
    """Renders user dashboard with active and resolved disputes plus badges."""

    if current_user.role == "admin":
        return redirect(url_for("admin.admin_dashboard"))

    if current_user.role == "spectator":
        flash("Spectator mode does not include a dashboard.", "info")
        return redirect(url_for("disputes.list_disputes"))

    try:
        refresh_user_badges(current_user.id)
    except Exception:
        db.session.rollback()

    active = Dispute.query.filter(
        ((Dispute.created_by == current_user.id) | (Dispute.invited_user == current_user.id)),
        Dispute.status.in_(["waiting", "active"]),
    ).order_by(Dispute.created_at.desc()).all()

    resolved = Dispute.query.filter(
        ((Dispute.created_by == current_user.id) | (Dispute.invited_user == current_user.id)),
        Dispute.status == "resolved",
    ).order_by(Dispute.resolved_at.desc()).all()

    won = sum(1 for dispute in resolved if dispute.ai_result and dispute.ai_result.winner_user_id == current_user.id)
    lost = max(0, len(resolved) - won)
    total_played = won + lost
    win_rate = round((won / total_played) * 100, 1) if total_played else 0.0

    week_cutoff = datetime.utcnow() - timedelta(days=7)
    weekly_wins = AIResult.query.filter(
        AIResult.winner_user_id == current_user.id,
        AIResult.created_at >= week_cutoff,
    ).count()
    weekly_rep_gain = weekly_wins * 10

    level_size = 50
    reputation = int(current_user.reputation_score or 0)
    current_level = (reputation // level_size) + 1
    next_level_points = current_level * level_size
    points_to_next = max(0, next_level_points - reputation)
    level_progress_points = reputation % level_size
    level_progress_pct = round((level_progress_points / level_size) * 100, 1) if level_size else 0.0

    catalog_names = [badge["name"] for badge in BADGE_DEFINITIONS]
    user_badges = (
        UserBadge.query.join(Badge, UserBadge.badge_id == Badge.id)
        .filter(UserBadge.user_id == current_user.id, Badge.name.in_(catalog_names))
        .order_by(UserBadge.awarded_at.desc())
        .all()
    )

    earned_names = {row.badge.name for row in user_badges}
    badge_goals = [
        {
            "name": badge["name"],
            "icon": badge.get("icon", "bi bi-patch-check-fill"),
            "rule": badge["description"],
            "slug": badge.get("slug", badge["name"].lower().replace(" ", "-")),
            "shape": badge.get("shape", "circle"),
            "tier": badge.get("tier", "personality"),
            "theme": badge.get("theme", badge["name"].lower().replace(" ", "-")),
            "earned": badge["name"] in earned_names,
        }
        for badge in BADGE_DEFINITIONS
    ]

    return render_template(
        "dashboard.html",
        active_disputes=active,
        resolved_disputes=resolved,
        user_badges=user_badges,
        badge_goals=badge_goals,
        badge_total=len(BADGE_DEFINITIONS),
        badge_earned=len(earned_names),
        won_count=won,
        lost_count=lost,
        win_rate=win_rate,
        weekly_rep_gain=weekly_rep_gain,
        current_level=current_level,
        points_to_next=points_to_next,
        level_progress_pct=level_progress_pct,
    )


@auth_bp.route("/notifications/read", methods=["POST"])
@login_required
def mark_notifications_read():
    """Marks current user's notifications as read."""

    try:
        Notification.query.filter_by(user_id=current_user.id, is_read=False).update({"is_read": True})
        db.session.commit()
        return jsonify({"message": "Notifications cleared"}), 200
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": f"Failed to clear notifications: {exc}"}), 500


@auth_bp.route("/profile/<username>", methods=["GET"])
def profile(username):
    """Displays public profile summary for one user."""

    user = User.query.filter_by(username=username).first_or_404()
    disputes = Dispute.query.filter((Dispute.created_by == user.id) | (Dispute.invited_user == user.id)).order_by(Dispute.created_at.desc()).all()
    resolved_disputes = [row for row in disputes if row.status == "resolved"]
    wins = sum(1 for row in resolved_disputes if row.ai_result and row.ai_result.winner_user_id == user.id)
    losses = max(0, len(resolved_disputes) - wins)
    total_played = wins + losses
    win_rate = round((wins / total_played) * 100, 1) if total_played else 0.0
    badges = (
        UserBadge.query.filter_by(user_id=user.id)
        .order_by(UserBadge.awarded_at.desc())
        .all()
    )

    level_size = 50
    reputation = int(user.reputation_score or 0)
    current_level = (reputation // level_size) + 1
    next_level_points = current_level * level_size
    points_to_next = max(0, next_level_points - reputation)
    level_progress_points = reputation % level_size
    level_progress_pct = round((level_progress_points / level_size) * 100, 1) if level_size else 0.0

    badge_cards = [
        {
            "name": badge.badge.name,
            "description": badge.badge.description,
            "slug": badge.badge.name.lower().replace(" ", "-").replace("(", "").replace(")", ""),
            "theme": badge.badge.name.lower().replace(" ", "-").replace("(", "").replace(")", ""),
            "shape": "circle" if badge.badge.name not in {"First Step", "First Argument", "First Clash", "First Victory", "First Loss", "Sharp Mind", "AI Challenger", "Edge Case Analyzer"} else "square",
            "awarded_at": badge.awarded_at,
        }
        for badge in badges
    ]

    dispute_cards = []
    for dispute in disputes:
        vote_counts = Counter(vote.voted_for_user_id for vote in dispute.votes)
        total_votes = sum(vote_counts.values())
        winner_user_id = dispute.ai_result.winner_user_id if dispute.ai_result else None
        user_won = bool(dispute.ai_result and winner_user_id == user.id)
        result_label = "WIN" if user_won else "LOSS" if dispute.status == "resolved" else dispute.status.upper()
        result_class = "result-pill-win" if user_won else "result-pill-loss" if dispute.status == "resolved" else "result-pill-neutral"
        if dispute.status == "resolved":
            vote_copy = f"Won by {vote_counts.get(winner_user_id, 0)} votes" if user_won else f"Lost by {vote_counts.get(winner_user_id, 0)} votes"
        else:
            vote_copy = f"{total_votes} spectator votes"
        # Keep public profile focused: only show vote details on high-engagement disputes.
        show_vote_copy = total_votes >= 5
        dispute_cards.append(
            {
                "id": dispute.id,
                "title": dispute.title,
                "status": dispute.status,
                "result_label": result_label,
                "result_class": result_class,
                "vote_copy": vote_copy,
                "vote_count": total_votes,
                "show_vote_copy": show_vote_copy,
                "opponent_name": next(
                    (
                        participant.username
                        for participant in (dispute.creator, dispute.invited)
                        if participant and participant.id != user.id
                    ),
                    "Unknown",
                ),
            }
        )

    return render_template(
        "profile.html",
        profile_user=user,
        profile_disputes=disputes,
        profile_badges=badges,
        profile_badge_cards=badge_cards,
        profile_wins=wins,
        profile_losses=losses,
        profile_win_rate=win_rate,
        profile_level=current_level,
        profile_points_to_next=points_to_next,
        profile_level_progress_pct=level_progress_pct,
        profile_reputation=reputation,
        profile_dispute_cards=dispute_cards,
    )
