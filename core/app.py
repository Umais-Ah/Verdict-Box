"""VerdictBox Flask application factory and global error handlers."""

from pathlib import Path

from flask import Flask, render_template, jsonify
from flask_login import current_user
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError
from config import Config
from core.extensions import db, login_manager
from core.models import Notification
from routes import register_blueprints


def _ensure_dispute_moderator_note_column(app):
    """Adds the moderator_note column when an older database is missing it."""

    inspector = inspect(db.engine)
    columns = {column["name"] for column in inspector.get_columns("disputes")}
    if "moderator_note" in columns:
        return

    app.logger.info("Adding missing disputes.moderator_note column")
    db.session.execute(text("ALTER TABLE disputes ADD COLUMN moderator_note TEXT NULL"))
    db.session.commit()


def _ensure_dispute_review_state_column(app):
    """Adds review_state to disputes if the column is missing."""

    inspector = inspect(db.engine)
    columns = {column["name"] for column in inspector.get_columns("disputes")}
    if "review_state" in columns:
        return

    app.logger.info("Adding missing disputes.review_state column")
    db.session.execute(text("ALTER TABLE disputes ADD COLUMN review_state VARCHAR(32) NULL"))
    db.session.commit()


def _ensure_adminlog_admin_user_column(app):
    """Adds admin_user_id to adminlogs when the column is missing."""

    inspector = inspect(db.engine)
    columns = {column["name"] for column in inspector.get_columns("adminlogs")}
    if "admin_user_id" in columns:
        return

    app.logger.info("Adding missing adminlogs.admin_user_id column")
    db.session.execute(text("ALTER TABLE adminlogs ADD COLUMN admin_user_id INT NULL"))
    db.session.execute(text("ALTER TABLE adminlogs ADD CONSTRAINT fk_adminlogs_admin_user FOREIGN KEY (admin_user_id) REFERENCES users(id) ON DELETE SET NULL"))
    db.session.commit()


def _ensure_adminlog_target_user_column(app):
    """Adds target_user_id to adminlogs when the column is missing."""

    inspector = inspect(db.engine)
    columns = {column["name"] for column in inspector.get_columns("adminlogs")}
    if "target_user_id" in columns:
        return

    app.logger.info("Adding missing adminlogs.target_user_id column")
    db.session.execute(text("ALTER TABLE adminlogs ADD COLUMN target_user_id INT NULL"))
    db.session.execute(text("ALTER TABLE adminlogs ADD CONSTRAINT fk_adminlogs_target_user FOREIGN KEY (target_user_id) REFERENCES users(id) ON DELETE SET NULL"))
    db.session.commit()


def _ensure_notifications_table(app):
    """Adds notifications table for user-facing moderation alerts."""

    inspector = inspect(db.engine)
    tables = set(inspector.get_table_names())
    if "notifications" in tables:
        return

    app.logger.info("Creating notifications table")
    db.session.execute(text(
        """
        CREATE TABLE notifications (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            title VARCHAR(120) NOT NULL,
            body TEXT NOT NULL,
            link_url VARCHAR(255) NULL,
            is_read BOOLEAN NOT NULL DEFAULT FALSE,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_notifications_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    ))
    db.session.commit()


def _ensure_dispute_reporting_schema(app):
    """Adds report storage and reported status support for existing deployments."""

    inspector = inspect(db.engine)
    tables = set(inspector.get_table_names())

    if "disputereports" not in tables:
        db.session.execute(text(
            """
            CREATE TABLE disputereports (
                id INT AUTO_INCREMENT PRIMARY KEY,
                dispute_id INT NOT NULL,
                reporter_user_id INT NOT NULL,
                reason VARCHAR(64) NOT NULL,
                details TEXT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                reviewed BOOLEAN NOT NULL DEFAULT FALSE,
                reviewed_at DATETIME NULL,
                reviewed_by_user_id INT NULL,
                CONSTRAINT uq_dispute_report_once UNIQUE (dispute_id, reporter_user_id),
                CONSTRAINT fk_disputereports_dispute FOREIGN KEY (dispute_id) REFERENCES disputes(id) ON DELETE CASCADE,
                CONSTRAINT fk_disputereports_reporter FOREIGN KEY (reporter_user_id) REFERENCES users(id) ON DELETE CASCADE,
                CONSTRAINT fk_disputereports_reviewed_by FOREIGN KEY (reviewed_by_user_id) REFERENCES users(id) ON DELETE SET NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        ))
        db.session.commit()

    dispute_columns = {column["name"] for column in inspector.get_columns("disputes")}
    if "status" in dispute_columns:
        db.session.execute(text(
            "ALTER TABLE disputes MODIFY status ENUM('waiting','active','resolved','reported','flagged') NOT NULL DEFAULT 'waiting'"
        ))
        db.session.commit()


def create_app():
    """Creates and configures Flask app instance with extensions and blueprints."""

    project_root = Path(__file__).resolve().parent.parent
    app = Flask(
        __name__,
        template_folder=str(project_root / "templates"),
        static_folder=str(project_root / "static"),
    )
    app.config.from_object(Config)

    db.init_app(app)
    login_manager.init_app(app)
    register_blueprints(app)

    with app.app_context():
        try:
            _ensure_dispute_moderator_note_column(app)
            _ensure_dispute_review_state_column(app)
            _ensure_adminlog_admin_user_column(app)
            _ensure_adminlog_target_user_column(app)
            _ensure_dispute_reporting_schema(app)
            _ensure_notifications_table(app)
        except SQLAlchemyError as exc:
            app.logger.error("Schema sync failed: %s", exc)

    @app.context_processor
    def inject_nav_notifications():
        if not current_user.is_authenticated:
            return {"nav_notifications": [], "nav_unread_count": 0}
        try:
            base_query = Notification.query.filter_by(user_id=current_user.id, is_read=False)
            unread_count = base_query.count()
            rows = base_query.order_by(Notification.created_at.desc()).limit(6).all()
            return {"nav_notifications": rows, "nav_unread_count": unread_count}
        except Exception:
            return {"nav_notifications": [], "nav_unread_count": 0}

    @app.errorhandler(404)
    def not_found(_err):
        """Returns custom 404 page."""

        return render_template("index.html", error_message="Page not found"), 404

    @app.errorhandler(500)
    def server_error(_err):
        """Returns JSON-friendly 500 response for easier debugging."""

        return jsonify({"error": "Internal server error"}), 500

    return app


if __name__ == "__main__":
    application = create_app()
    with application.app_context():
        try:
            db.create_all()
        except SQLAlchemyError as exc:
            # Keep the app bootable even when DB storage is exhausted.
            application.logger.error("db.create_all failed: %s", exc)
    application.run(debug=True)
