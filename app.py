import os
import logging
from datetime import datetime

from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from flask_login import LoginManager, current_user
from flask_cors import CORS

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# Create base class for SQLAlchemy models
class Base(DeclarativeBase):
    pass

# Initialize extensions
db = SQLAlchemy(model_class=Base)
login_manager = LoginManager()

# Create the app
app = Flask(__name__)
CORS(app)

# Set application config
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
app.config["UPLOAD_FOLDER"] = os.path.join(os.getcwd(), "static", "uploads")
app.config["QR_CODE_FOLDER"] = os.path.join(os.getcwd(), "static", "qr_codes")
app.config["ALLOWED_EXTENSIONS"] = {"png", "jpg", "jpeg", "gif"}
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB max upload size
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key")

# Ensure upload and QR code directories exist
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
os.makedirs(app.config["QR_CODE_FOLDER"], exist_ok=True)

# Initialize extensions with app
db.init_app(app)
login_manager.init_app(app)
login_manager.login_view = "login"

# Context processor for template variables
@app.context_processor
def inject_now():
    return {"now": datetime.utcnow()}

# Import models and routes
with app.app_context():
    from models import User, PhotoFolder, Photo  # noqa: F401
    import routes  # noqa: F401
    
    # Create database tables
    db.create_all()
    
    # Register routes blueprint
    # Note: We're using direct imports, so we don't need to register a blueprint

# Set up custom error pages
@app.errorhandler(404)
def page_not_found(e):
    return render_template("error.html", error_code=404, error_message="Page not found"), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template("error.html", error_code=500, error_message="Internal server error"), 500