"""Root launcher for VerdictBox.

This keeps startup simple (`python app.py`) while preserving existing import paths.
"""

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Ensure project root is importable.
for path in (str(BASE_DIR),):
    if path not in sys.path:
        sys.path.insert(0, path)

from sqlalchemy.exc import SQLAlchemyError

from core.app import create_app
from core.extensions import db


application = create_app()


if __name__ == "__main__":
    with application.app_context():
        try:
            db.create_all()
        except SQLAlchemyError as exc:
            application.logger.error("db.create_all failed: %s", exc)

    debug_mode = os.getenv("FLASK_ENV", "development").lower() == "development"
    application.run(debug=debug_mode)
