import os
import logging
from datetime import datetime

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from flask_login import LoginManager


class Base(DeclarativeBase):
    pass


# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Initialize database
db = SQLAlchemy(model_class=Base)

# Create the app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET")

# Configure the database
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

# Configure the application
app.config["UPLOAD_FOLDER"] = "static/uploads"
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB max-limit
app.config["CATBOX_API_URL"] = "https://catbox.moe/user/api.php"
app.config["ALLOWED_EXTENSIONS"] = {"jpg", "jpeg", "png", "gif"}

# Initialize extensions
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Jinja context processors
@app.context_processor
def inject_now():
    return {'now': datetime.utcnow()}

# Create upload folder if not exists
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

with app.app_context():
    # Import models
    from models import User, PhotoFolder, Photo
    
    # Create all tables
    db.create_all()
    
    # Import routes after models to avoid circular imports
    import routes
