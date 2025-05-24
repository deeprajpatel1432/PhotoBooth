from datetime import datetime
from flask_login import UserMixin
from app import db, login_manager


@login_manager.user_loader
def load_user(user_id):
    """Load a user for Flask-Login."""
    return User.query.get(int(user_id))


class User(UserMixin, db.Model):
    """User model for authentication and profile information."""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=True)
    profile_picture = db.Column(db.String(255), nullable=True)
    password_hash = db.Column(db.String(256), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, default=datetime.utcnow)
    use_local_storage = db.Column(db.Boolean, default=True)
    
    # Relationships
    folders = db.relationship("PhotoFolder", back_populates="user", cascade="all, delete-orphan")
    photos = db.relationship("Photo", back_populates="user", cascade="all, delete-orphan")
    
    def set_password(self, password):
        """Set the password hash for the user."""
        from werkzeug.security import generate_password_hash
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        """Check if the password matches the hash."""
        from werkzeug.security import check_password_hash
        if self.password_hash:
            return check_password_hash(self.password_hash, password)
        return False


class PhotoFolder(db.Model):
    """Represents a folder for organizing photos."""
    __tablename__ = 'photo_folders'
    
    id = db.Column(db.Integer, primary_key=True)
    folder_name = db.Column(db.String(255), nullable=False)
    folder_key = db.Column(db.String(100), nullable=False, unique=True)  # UUID or other unique identifier
    is_local = db.Column(db.Boolean, default=True)  # Whether photos are stored locally or on catbox.moe
    qr_code_url = db.Column(db.String(512), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    user = db.relationship("User", back_populates="folders")
    photos = db.relationship("Photo", back_populates="folder", cascade="all, delete-orphan")


class Photo(db.Model):
    """Represents a photo uploaded to the application."""
    __tablename__ = 'photos'
    
    id = db.Column(db.Integer, primary_key=True)
    file_name = db.Column(db.String(255), nullable=False)
    original_name = db.Column(db.String(255), nullable=True)
    file_url = db.Column(db.String(512), nullable=False)  # URL on catbox.moe or local path
    file_size = db.Column(db.Integer, nullable=True)  # Size in bytes
    mime_type = db.Column(db.String(100), nullable=True)
    is_local = db.Column(db.Boolean, default=True)  # Whether this is a local file or catbox.moe file
    local_path = db.Column(db.String(512), nullable=True)  # Path to local file if using local storage
    delete_hash = db.Column(db.String(100), nullable=True)  # For catbox.moe deletion (if applicable)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    folder_id = db.Column(db.Integer, db.ForeignKey('photo_folders.id'), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    user = db.relationship("User", back_populates="photos")
    folder = db.relationship("PhotoFolder", back_populates="photos")
