"""Badge catalog and achievement evaluation helpers for VerdictBox."""

from datetime import timedelta
from sqlalchemy import func
from core.extensions import db
from core.models import Badge, UserBadge, Dispute, Submission, AIResult, Vote, Appeal


BADGE_DEFINITIONS = [
    {"name": "First Step", "description": "Create your first dispute.", "icon": "bi bi-signpost-fill", "slug": "first-step", "tier": "milestone", "shape": "square", "theme": "first-step"},
    {"name": "First Argument", "description": "Submit your first argument.", "icon": "bi bi-pencil-square", "slug": "first-argument", "tier": "milestone", "shape": "square", "theme": "first-argument"},
    {"name": "First Clash", "description": "Complete a full dispute with both sides submitted.", "icon": "bi bi-shield-fill-exclamation", "slug": "first-clash", "tier": "milestone", "shape": "square", "theme": "first-clash"},
    {"name": "First Victory", "description": "Win your first dispute.", "icon": "bi bi-trophy-fill", "slug": "first-victory", "tier": "milestone", "shape": "square", "theme": "first-victory"},
    {"name": "First Loss", "description": "Lose your first dispute.", "icon": "bi bi-emoji-frown-fill", "slug": "first-loss", "tier": "milestone", "shape": "square", "theme": "first-loss"},
    {"name": "Logic Master", "description": "5 arguments with zero logical fallacies detected.", "icon": "bi bi-lightbulb-fill", "slug": "logic-master", "tier": "personality", "shape": "circle", "theme": "logic-master"},
    {"name": "Sharp Mind", "description": "Win with high reasoning confidence score.", "icon": "bi bi-stars", "slug": "sharp-mind", "tier": "milestone", "shape": "square", "theme": "sharp-mind"},
    {"name": "Clean Thinker", "description": "Low toxicity and neutral sentiment across 10 disputes.", "icon": "bi bi-droplet-half", "slug": "clean-thinker", "tier": "personality", "shape": "circle", "theme": "clean-thinker"},
    {"name": "Evidence Builder", "description": "Consistently strong and structured argument quality.", "icon": "bi bi-collection-fill", "slug": "evidence-builder", "tier": "personality", "shape": "circle", "theme": "evidence-builder"},
    {"name": "AI Challenger", "description": "Win despite high AI verdict confidence pressure.", "icon": "bi bi-robot", "slug": "ai-challenger", "tier": "milestone", "shape": "square", "theme": "ai-challenger"},
    {"name": "Unstoppable", "description": "Win 5 disputes in a row.", "icon": "bi bi-fire", "slug": "unstoppable", "tier": "personality", "shape": "circle", "theme": "unstoppable"},
    {"name": "Consistent Thinker", "description": "Stay active for 7 consecutive days.", "icon": "bi bi-calendar-check-fill", "slug": "consistent-thinker", "tier": "personality", "shape": "circle", "theme": "consistent-thinker"},
    {"name": "Quick Responder", "description": "Submit arguments quickly in multiple disputes.", "icon": "bi bi-lightning-charge-fill", "slug": "quick-responder", "tier": "personality", "shape": "circle", "theme": "quick-responder"},
    {"name": "Debate Addict", "description": "Participate in 20 disputes.", "icon": "bi bi-chat-square-heart-fill", "slug": "debate-addict", "tier": "personality", "shape": "circle", "theme": "debate-addict"},
    {"name": "Voice of the People", "description": "Achieve a high spectator vote ratio.", "icon": "bi bi-megaphone-fill", "slug": "voice-of-the-people", "tier": "personality", "shape": "circle", "theme": "voice-of-the-people"},
    {"name": "Influencer", "description": "Your arguments strongly influence voting outcomes.", "icon": "bi bi-people-fill", "slug": "influencer", "tier": "personality", "shape": "circle", "theme": "influencer"},
    {"name": "Fair Judge", "description": "Vote in line with final AI verdict frequently.", "icon": "bi bi-check2-square", "slug": "fair-judge", "tier": "personality", "shape": "circle", "theme": "fair-judge"},
    {"name": "Clutch Player", "description": "Win a case after submitting an appeal.", "icon": "bi bi-bullseye", "slug": "clutch-player", "tier": "personality", "shape": "circle", "theme": "clutch-player"},
    {"name": "Controversial Case", "description": "Participate in a dispute where AI and crowd strongly disagree.", "icon": "bi bi-flag-fill", "slug": "controversial-case", "tier": "personality", "shape": "circle", "theme": "controversial-case"},
    {"name": "Edge Case Analyzer", "description": "Trigger system fallback or uncertainty verdict handling.", "icon": "bi bi-search-heart-fill", "slug": "edge-case-analyzer", "tier": "milestone", "shape": "square", "theme": "edge-case-analyzer"},
]

BADGE_META_BY_NAME = {
    badge["name"]: {
        "name": badge["name"],
        "description": badge["description"],
        "icon": badge.get("icon", "bi bi-patch-check-fill"),
        "slug": badge.get("slug", badge["name"].lower().replace(" ", "-")),
        "tier": badge.get("tier", "personality"),
        "shape": badge.get("shape", "circle"),
        "theme": badge.get("theme", badge["name"].lower().replace(" ", "-")),
    }
    for badge in BADGE_DEFINITIONS
}


def ensure_badges_exist():
    """Creates any missing badge definitions from BADGE_DEFINITIONS."""

    names = [badge["name"] for badge in BADGE_DEFINITIONS]
    existing = {name for (name,) in db.session.query(Badge.name).filter(Badge.name.in_(names)).all()}
    missing = [badge for badge in BADGE_DEFINITIONS if badge["name"] not in existing]
    if not missing:
        return

    for badge in missing:
        db.session.add(Badge(name=badge["name"], description=badge["description"]))
    db.session.commit()


def _side_key_for_user(dispute, user_id):
    submissions = sorted(dispute.submissions, key=lambda row: row.id)
    if len(submissions) < 2:
        return None
    if submissions[0].user_id == user_id:
        return "a"
    if submissions[1].user_id == user_id:
        return "b"
    return None


def _get_side_metrics(dispute, user_id):
    ai_result = dispute.ai_result
    if not ai_result:
        return None

    side = _side_key_for_user(dispute, user_id)
    if side == "a":
        return {
            "toxicity": float(ai_result.toxicity_score_a or 0.0),
            "sarcasm": float(ai_result.sarcasm_score_a or 0.0),
            "sentiment": str(ai_result.sentiment_a or ""),
            "fallacies": list(ai_result.fallacies_a or []),
        }
    if side == "b":
        return {
            "toxicity": float(ai_result.toxicity_score_b or 0.0),
            "sarcasm": float(ai_result.sarcasm_score_b or 0.0),
            "sentiment": str(ai_result.sentiment_b or ""),
            "fallacies": list(ai_result.fallacies_b or []),
        }
    return None


def _resolved_user_disputes(user_id):
    # Only consider resolved disputes that are in PUBLIC moderation mode
    return (
        Dispute.query.join(Submission, Submission.dispute_id == Dispute.id)
        .filter(Dispute.status == "resolved", Submission.user_id == user_id, Dispute.moderation_mode == 'public')
        .distinct()
        .order_by(Dispute.resolved_at.asc(), Dispute.id.asc())
        .all()
    )


def _max_win_streak(disputes, user_id):
    best = 0
    current = 0
    for dispute in disputes:
        ai_result = dispute.ai_result
        if ai_result and ai_result.winner_user_id == user_id:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def _longest_day_streak(user_id):
    # Only count submissions on PUBLIC disputes for streak calculations
    rows = (
        db.session.query(func.date(Submission.submitted_at))
        .join(Dispute, Submission.dispute_id == Dispute.id)
        .filter(Submission.user_id == user_id, Dispute.moderation_mode == 'public')
        .group_by(func.date(Submission.submitted_at))
        .order_by(func.date(Submission.submitted_at).asc())
        .all()
    )
    days = [row[0] for row in rows if row[0] is not None]
    if not days:
        return 0

    longest = 1
    current = 1
    for idx in range(1, len(days)):
        if (days[idx] - days[idx - 1]).days == 1:
            current += 1
            longest = max(longest, current)
        elif days[idx] != days[idx - 1]:
            current = 1
    return longest


def _is_fallback_reasoning(ai_result):
    text = str(ai_result.reasoning or "")
    lowered = text.lower()
    return "system note: openrouter unavailable" in lowered or "fallback analysis used" in lowered


def _award(user_id, badge_name, badge_id_map, unlocked_badges):
    badge_id = badge_id_map.get(badge_name)
    if not badge_id:
        return

    already = UserBadge.query.filter_by(user_id=user_id, badge_id=badge_id).first()
    if not already:
        db.session.add(UserBadge(user_id=user_id, badge_id=badge_id))
        unlocked_badges.append(BADGE_META_BY_NAME.get(badge_name, {"name": badge_name}))


def refresh_user_badges(user_id):
    """Re-evaluates all badge rules for one user and awards newly met badges."""

    ensure_badges_exist()
    unlocked_badges = []
    badge_rows = Badge.query.filter(Badge.name.in_([badge["name"] for badge in BADGE_DEFINITIONS])).all()
    badge_id_map = {badge.name: badge.id for badge in badge_rows}

    # Only count created public disputes for public-facing badges
    created_count = Dispute.query.filter_by(created_by=user_id, moderation_mode='public').count()
    if created_count >= 1:
        _award(user_id, "First Step", badge_id_map, unlocked_badges)

    # Count only submissions in public disputes
    total_arguments = (
        Submission.query.join(Dispute, Submission.dispute_id == Dispute.id)
        .filter(Submission.user_id == user_id, Dispute.moderation_mode == 'public')
        .count()
    )
    if total_arguments >= 1:
        _award(user_id, "First Argument", badge_id_map, unlocked_badges)

    resolved_disputes = _resolved_user_disputes(user_id)
    if resolved_disputes:
        _award(user_id, "First Clash", badge_id_map, unlocked_badges)

    wins = [dispute for dispute in resolved_disputes if dispute.ai_result and dispute.ai_result.winner_user_id == user_id]
    losses = [dispute for dispute in resolved_disputes if dispute.ai_result and dispute.ai_result.winner_user_id != user_id]

    if wins:
        _award(user_id, "First Victory", badge_id_map, unlocked_badges)
    if losses:
        _award(user_id, "First Loss", badge_id_map, unlocked_badges)

    no_fallacy_count = 0
    clean_thinker_count = 0
    evidence_builder_count = 0
    high_conf_wins = 0
    fallback_cases = 0
    fast_response_count = 0
    voice_cases = 0
    influencer_cases = 0
    controversial_cases = 0

    for dispute in resolved_disputes:
        ai_result = dispute.ai_result
        if not ai_result:
            continue

        metrics = _get_side_metrics(dispute, user_id)
        if not metrics:
            continue

        if len(metrics["fallacies"]) == 0:
            no_fallacy_count += 1

        if metrics["toxicity"] <= 0.20 and metrics["sentiment"].lower() == "neutral":
            clean_thinker_count += 1

        if metrics["toxicity"] <= 0.20 and metrics["sarcasm"] <= 0.20 and len(metrics["fallacies"]) == 0:
            evidence_builder_count += 1

        if ai_result.winner_user_id == user_id and float(ai_result.confidence_score or 0.0) >= 0.85:
            high_conf_wins += 1

        if _is_fallback_reasoning(ai_result):
            fallback_cases += 1

        user_submission = next((row for row in dispute.submissions if row.user_id == user_id), None)
        if user_submission and dispute.created_at:
            delta = user_submission.submitted_at - dispute.created_at
            if delta <= timedelta(minutes=30):
                fast_response_count += 1

        vote_rows = list(dispute.votes)
        total_votes = len(vote_rows)
        if total_votes >= 5:
            votes_for_user = sum(1 for vote in vote_rows if vote.voted_for_user_id == user_id)
            ratio = votes_for_user / total_votes
            if ratio >= 0.65:
                voice_cases += 1
            if ratio >= 0.80 and ai_result.winner_user_id == user_id:
                influencer_cases += 1

            vote_counts = {}
            for vote in vote_rows:
                vote_counts[vote.voted_for_user_id] = vote_counts.get(vote.voted_for_user_id, 0) + 1
            leading_user_id = max(vote_counts, key=vote_counts.get)
            leader_share = vote_counts[leading_user_id] / total_votes
            if leader_share >= 0.70 and leading_user_id != ai_result.winner_user_id:
                controversial_cases += 1

    if no_fallacy_count >= 5:
        _award(user_id, "Logic Master", badge_id_map, unlocked_badges)

    if high_conf_wins >= 1:
        _award(user_id, "Sharp Mind", badge_id_map, unlocked_badges)
        _award(user_id, "AI Challenger", badge_id_map, unlocked_badges)

    if clean_thinker_count >= 10:
        _award(user_id, "Clean Thinker", badge_id_map, unlocked_badges)

    if evidence_builder_count >= 5:
        _award(user_id, "Evidence Builder", badge_id_map, unlocked_badges)

    if _max_win_streak(resolved_disputes, user_id) >= 5:
        _award(user_id, "Unstoppable", badge_id_map, unlocked_badges)

    if _longest_day_streak(user_id) >= 7:
        _award(user_id, "Consistent Thinker", badge_id_map, unlocked_badges)

    if fast_response_count >= 5:
        _award(user_id, "Quick Responder", badge_id_map, unlocked_badges)

    if len(resolved_disputes) >= 20:
        _award(user_id, "Debate Addict", badge_id_map, unlocked_badges)

    if voice_cases >= 1:
        _award(user_id, "Voice of the People", badge_id_map, unlocked_badges)

    if influencer_cases >= 1:
        _award(user_id, "Influencer", badge_id_map, unlocked_badges)

    # Only consider votes cast on PUBLIC disputes
    votes_cast = (
        Vote.query.join(Dispute, Vote.dispute_id == Dispute.id)
        .filter(Vote.voter_user_id == user_id, Dispute.moderation_mode == 'public')
        .all()
    )
    if len(votes_cast) >= 10:
        aligned = 0
        considered = 0
        for vote in votes_cast:
            # `votes_cast` already limited to public disputes, so safe to reference ai_result
            dispute = Dispute.query.get(vote.dispute_id)
            if not dispute or not dispute.ai_result:
                continue
            considered += 1
            if vote.voted_for_user_id == dispute.ai_result.winner_user_id:
                aligned += 1
        if considered >= 10 and (aligned / considered) >= 0.75:
            _award(user_id, "Fair Judge", badge_id_map, unlocked_badges)

    # Clutch wins only count for public disputes
    clutch_wins = (
        db.session.query(Appeal.id)
        .join(Dispute, Appeal.dispute_id == Dispute.id)
        .join(AIResult, AIResult.dispute_id == Dispute.id)
        .filter(
            Appeal.appellant_user_id == user_id,
            Appeal.status == "approved",
            AIResult.winner_user_id == user_id,
            Dispute.moderation_mode == 'public',
        )
        .count()
    )
    if clutch_wins >= 1:
        _award(user_id, "Clutch Player", badge_id_map, unlocked_badges)

    if controversial_cases >= 1:
        _award(user_id, "Controversial Case", badge_id_map, unlocked_badges)

    if fallback_cases >= 1:
        _award(user_id, "Edge Case Analyzer", badge_id_map, unlocked_badges)

    db.session.commit()
    return unlocked_badges
