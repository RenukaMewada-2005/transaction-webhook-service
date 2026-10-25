
import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from flask import Flask

from app.extensions import db

load_dotenv()


def create_app():
    app = Flask(__name__)

    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is missing from the .env file"
        )

    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
    }

    db.init_app(app)

    # Import models so SQLAlchemy registers their tables.
    from app import models  # noqa: F401

    # Register API routes.
    from app.routes import webhook_bp
    app.register_blueprint(webhook_bp)

    @app.get("/")
    @app.get("/")
    def health_check():
      return {
        "status": "HEALTHY",
        "current_time": datetime.now(timezone.utc).isoformat(),
       }, 200

    return app
