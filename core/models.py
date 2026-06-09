"""SQLAlchemy models representing VerdictBox database entities and relationships."""

from datetime import datetime
from flask_login import UserMixin
from sqlalchemy import UniqueConstraint
from core.extensions import db, login_manager


class User(UserMixin, db.Model):
    """Application users including disputants, spectators, and admins."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.Enum("disputant", "spectator", "admin", name="role_enum"), nullable=False, default="spectator")
    reputation_score = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    created_disputes = db.relationship("Dispute", foreign_keys="Dispute.created_by", back_populates="creator")
    invited_disputes = db.relationship("Dispute", foreign_keys="Dispute.invited_user", back_populates="invited")
    submissions = db.relationship("Submission", back_populates="user", cascade="all, delete-orphan")
    won_results = db.relationship("AIResult", back_populates="winner", cascade="all, delete")
    votes_cast = db.relationship("Vote", foreign_keys="Vote.voter_user_id", back_populates="voter", cascade="all, delete-orphan")
    votes_received = db.relationship("Vote", foreign_keys="Vote.voted_for_user_id", back_populates="voted_for")
    comments = db.relationship("Comment", back_populates="author", cascade="all, delete-orphan")
    appeals = db.relationship("Appeal", back_populates="appellant", cascade="all, delete-orphan")
    dispute_reports = db.relationship("DisputeReport", foreign_keys="DisputeReport.reporter_user_id", back_populates="reporter", cascade="all, delete-orphan")
    reviewed_reports = db.relationship("DisputeReport", foreign_keys="DisputeReport.reviewed_by_user_id", back_populates="reviewed_by")
    admin_logs = db.relationship("AdminLog", foreign_keys="AdminLog.admin_user_id", back_populates="admin_user", cascade="all, delete-orphan")
    badges = db.relationship("UserBadge", back_populates="user", cascade="all, delete-orphan")


@login_manager.user_loader
def load_user(user_id):
    """Loads a user by id for Flask-Login session restoration."""

    return User.query.get(int(user_id))


class Dispute(db.Model):
    """A debate/dispute containing two participants and their submissions."""

    __tablename__ = "disputes"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    invited_user = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    status = db.Column(db.Enum("waiting", "active", "resolved", "reported", "flagged", name="dispute_status_enum"), nullable=False, default="waiting")
    is_public = db.Column(db.Boolean, nullable=False, default=True)
    moderation_mode = db.Column(db.Enum("public", "private", name="moderation_mode_enum"), nullable=False, default="public")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime)
    moderator_note = db.Column(db.Text)
    review_state = db.Column(db.String(32))

    creator = db.relationship("User", foreign_keys=[created_by], back_populates="created_disputes")
    invited = db.relationship("User", foreign_keys=[invited_user], back_populates="invited_disputes")
    submissions = db.relationship("Submission", back_populates="dispute", cascade="all, delete-orphan")
    ai_result = db.relationship("AIResult", back_populates="dispute", uselist=False, cascade="all, delete-orphan")
    votes = db.relationship("Vote", back_populates="dispute", cascade="all, delete-orphan")
    comments = db.relationship("Comment", back_populates="dispute", cascade="all, delete-orphan")
    appeals = db.relationship("Appeal", back_populates="dispute", cascade="all, delete-orphan")
    reports = db.relationship("DisputeReport", back_populates="dispute", cascade="all, delete-orphan")
    admin_logs = db.relationship("AdminLog", back_populates="dispute", cascade="all, delete-orphan")

    def is_private(self):
        """Check if dispute is in private mode."""
        return self.moderation_mode == "private"

    def is_participant(self, user_id):
        """Check if a user is a participant in this dispute."""
        return Submission.query.filter_by(dispute_id=self.id, user_id=user_id).first() is not None

    def can_report(self, user_id):
        """Determines if a user can file a report for this dispute."""
        # Private disputes cannot be reported by participants
        if self.is_private():
            return False
        # Public disputes can be reported by anyone
        return True

    def can_appeal(self, user_id):
        """Determines if a user can file an appeal for this dispute."""
        # Only participants can appeal, and only after resolution
        if self.status != "resolved":
            return False
        return self.is_participant(user_id)


class Submission(db.Model):
    """Text submitted by a disputant for a specific dispute."""

    __tablename__ = "submissions"
    __table_args__ = (UniqueConstraint("dispute_id", "user_id", name="uq_dispute_user_submission"),)

    id = db.Column(db.Integer, primary_key=True)
    dispute_id = db.Column(db.Integer, db.ForeignKey("disputes.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    argument_text = db.Column(db.Text, nullable=False)
    submitted_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    dispute = db.relationship("Dispute", back_populates="submissions")
    user = db.relationship("User", back_populates="submissions")


class AIResult(db.Model):
    """One-to-one AI analysis result linked to a resolved dispute."""

    __tablename__ = "airesults"

    id = db.Column(db.Integer, primary_key=True)
    dispute_id = db.Column(db.Integer, db.ForeignKey("disputes.id", ondelete="CASCADE"), nullable=False, unique=True)
    toxicity_score_a = db.Column(db.Numeric(5, 4), nullable=False)
    toxicity_score_b = db.Column(db.Numeric(5, 4), nullable=False)
    sentiment_a = db.Column(db.String(20), nullable=False)
    sentiment_b = db.Column(db.String(20), nullable=False)
    sarcasm_score_a = db.Column(db.Numeric(5, 4), nullable=False)
    sarcasm_score_b = db.Column(db.Numeric(5, 4), nullable=False)
    winner_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    reasoning = db.Column(db.Text, nullable=False)
    confidence_score = db.Column(db.Numeric(5, 4), nullable=False)
    fallacies_a = db.Column(db.JSON)
    fallacies_b = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    dispute = db.relationship("Dispute", back_populates="ai_result")
    winner = db.relationship("User", back_populates="won_results")


class Vote(db.Model):
    """Spectator vote for one side of a dispute."""

    __tablename__ = "votes"
    __table_args__ = (UniqueConstraint("dispute_id", "voter_user_id", name="uq_vote_once"),)

    id = db.Column(db.Integer, primary_key=True)
    dispute_id = db.Column(db.Integer, db.ForeignKey("disputes.id", ondelete="CASCADE"), nullable=False)
    voter_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    voted_for_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    voted_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    dispute = db.relationship("Dispute", back_populates="votes")
    voter = db.relationship("User", foreign_keys=[voter_user_id], back_populates="votes_cast")
    voted_for = db.relationship("User", foreign_keys=[voted_for_user_id], back_populates="votes_received")


class Comment(db.Model):
    """Public comment attached to a dispute by an authenticated user."""

    __tablename__ = "comments"

    id = db.Column(db.Integer, primary_key=True)
    dispute_id = db.Column(db.Integer, db.ForeignKey("disputes.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    dispute = db.relationship("Dispute", back_populates="comments")
    author = db.relationship("User", back_populates="comments")


class Appeal(db.Model):
    """Appeal raised by a disputant against an AI verdict."""

    __tablename__ = "appeals"

    id = db.Column(db.Integer, primary_key=True)
    dispute_id = db.Column(db.Integer, db.ForeignKey("disputes.id", ondelete="CASCADE"), nullable=False)
    appellant_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    reason_text = db.Column(db.Text, nullable=False)
    status = db.Column(db.Enum("pending", "approved", "rejected", name="appeal_status_enum"), nullable=False, default="pending")
    admin_response = db.Column(db.Text)
    submitted_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    reviewed_at = db.Column(db.DateTime)

    dispute = db.relationship("Dispute", back_populates="appeals")
    appellant = db.relationship("User", back_populates="appeals")


class DisputeReport(db.Model):
    """User report attached to a dispute for moderation escalation."""

    __tablename__ = "disputereports"
    __table_args__ = (UniqueConstraint("dispute_id", "reporter_user_id", name="uq_dispute_report_once"),)

    id = db.Column(db.Integer, primary_key=True)
    dispute_id = db.Column(db.Integer, db.ForeignKey("disputes.id", ondelete="CASCADE"), nullable=False)
    reporter_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    reason = db.Column(db.String(64), nullable=False)
    details = db.Column(db.Text)
    is_system_flag = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    reviewed = db.Column(db.Boolean, nullable=False, default=False)
    reviewed_at = db.Column(db.DateTime)
    reviewed_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))

    dispute = db.relationship("Dispute", back_populates="reports")
    reporter = db.relationship("User", foreign_keys=[reporter_user_id], back_populates="dispute_reports")
    reviewed_by = db.relationship("User", foreign_keys=[reviewed_by_user_id], back_populates="reviewed_reports")


class Badge(db.Model):
    """Badge definition table used for user achievements."""

    __tablename__ = "badges"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.String(255), nullable=False)

    users = db.relationship("UserBadge", back_populates="badge", cascade="all, delete-orphan")


class UserBadge(db.Model):
    """Many-to-many bridge mapping users to awarded badges."""

    __tablename__ = "userbadges"
    __table_args__ = (UniqueConstraint("user_id", "badge_id", name="uq_user_badge"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    badge_id = db.Column(db.Integer, db.ForeignKey("badges.id", ondelete="CASCADE"), nullable=False)
    awarded_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship("User", back_populates="badges")
    badge = db.relationship("Badge", back_populates="users")


class AdminLog(db.Model):
    """Administrative action log for moderation and review events."""

    __tablename__ = "adminlogs"

    id = db.Column(db.Integer, primary_key=True)
    dispute_id = db.Column(db.Integer, db.ForeignKey("disputes.id", ondelete="SET NULL"))
    admin_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    target_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    action_type = db.Column(db.String(50), nullable=False)
    reason = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    dispute = db.relationship("Dispute", back_populates="admin_logs")
    admin_user = db.relationship("User", foreign_keys=[admin_user_id], back_populates="admin_logs")


class Notification(db.Model):
    """User-facing notifications for moderation and appeal decisions."""

    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = db.Column(db.String(120), nullable=False)
    body = db.Column(db.Text, nullable=False)
    link_url = db.Column(db.String(255))
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship("User", foreign_keys=[user_id])
