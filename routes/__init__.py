"""Blueprint registration helpers for VerdictBox routes."""

from routes.auth import auth_bp
from routes.disputes import disputes_bp
from routes.voting import voting_bp
from routes.admin import admin_bp


def register_blueprints(app):
    """Registers all application blueprints on the Flask app."""

    app.register_blueprint(auth_bp)
    app.register_blueprint(disputes_bp)
    app.register_blueprint(voting_bp)
    app.register_blueprint(admin_bp)
