"""Voting routes allowing spectators to vote once per dispute."""

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from core.extensions import db
from core.models import Dispute, Vote, Submission
from core.badges_engine import refresh_user_badges


voting_bp = Blueprint("voting", __name__)


def _payload():
    """Returns JSON body when available, otherwise form data."""

    return request.get_json(silent=True) or request.form


@voting_bp.route("/dispute/<int:dispute_id>/vote", methods=["POST"])
@login_required
def cast_vote(dispute_id):
    """Creates or updates a spectator vote for a dispute.
    
    Voting is restricted to public disputes only. Private disputes are
    controlled, invite-only environments without public voting.
    """

    if current_user.role != "spectator":
        return jsonify({"error": "Only spectators can vote"}), 403

    dispute = Dispute.query.get_or_404(dispute_id)
    
    # Private disputes do not allow public voting
    if dispute.is_private():
        return jsonify({"error": "Voting is not allowed for private disputes"}), 403
    
    if dispute.status != "resolved":
        return jsonify({"error": "Votes are allowed only for resolved disputes"}), 400

    data = _payload()
    voted_for_user_id = data.get("voted_for_user_id")
    if not voted_for_user_id:
        return jsonify({"error": "voted_for_user_id is required"}), 400

    participants = {s.user_id for s in Submission.query.filter_by(dispute_id=dispute.id).all()}
    if int(voted_for_user_id) not in participants:
        return jsonify({"error": "Invalid target user for this dispute"}), 400

    target_user_id = int(voted_for_user_id)
    existing_vote = Vote.query.filter_by(dispute_id=dispute.id, voter_user_id=current_user.id).first()

    try:
        created = False
        changed = False
        if existing_vote:
            if existing_vote.voted_for_user_id != target_user_id:
                existing_vote.voted_for_user_id = target_user_id
                changed = True
        else:
            vote = Vote(dispute_id=dispute.id, voter_user_id=current_user.id, voted_for_user_id=target_user_id)
            db.session.add(vote)
            created = True
        db.session.commit()
        unlocked_badges = []
        target_user_ids = {current_user.id}
        for participant in Submission.query.filter_by(dispute_id=dispute.id).all():
            target_user_ids.add(participant.user_id)
        for user_id in target_user_ids:
            try:
                new_badges = refresh_user_badges(user_id)
                if user_id == current_user.id:
                    unlocked_badges = list(new_badges or [])
            except Exception:
                db.session.rollback()
        if created:
            message = "Vote submitted"
            status_code = 201
        elif changed:
            message = "Vote updated"
            status_code = 200
        else:
            message = "Vote unchanged"
            status_code = 200
        return jsonify({"message": message, "unlocked_badges": unlocked_badges}), status_code
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": f"Vote failed: {exc}"}), 400


@voting_bp.route("/dispute/<int:dispute_id>/votes", methods=["GET"])
def vote_counts(dispute_id):
    """Returns simple vote counts grouped by voted user id."""

    Dispute.query.get_or_404(dispute_id)
    rows = Vote.query.filter_by(dispute_id=dispute_id).all()
    result = {}
    for row in rows:
        result[str(row.voted_for_user_id)] = result.get(str(row.voted_for_user_id), 0) + 1
    return jsonify(result), 200
