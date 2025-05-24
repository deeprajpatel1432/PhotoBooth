from datetime import datetime, timedelta
import uuid

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

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
    is_admin = db.Column(db.Boolean, default=False)
    use_local_storage = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    folders = db.relationship("PhotoFolder", back_populates="user", cascade="all, delete-orphan")
    photos = db.relationship("Photo", back_populates="user", cascade="all, delete-orphan")
    
    def set_password(self, password):
        """Set the password hash for the user."""
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        """Check if the password matches the hash."""
        return check_password_hash(self.password_hash, password)


class PhotoFolder(db.Model):
    """Represents a folder for organizing photos."""
    __tablename__ = 'photo_folders'
    
    id = db.Column(db.Integer, primary_key=True)
    folder_name = db.Column(db.String(255), nullable=False)
    folder_key = db.Column(db.String(100), nullable=False, unique=True)  # UUID or other unique identifier
    is_local = db.Column(db.Boolean, default=True)  # Whether photos are stored locally or on catbox.moe
    qr_code_url = db.Column(db.String(512), nullable=True)
    qr_code_generated_at = db.Column(db.DateTime, nullable=True)  # Timestamp when QR code was generated
    qr_code_expires_at = db.Column(db.DateTime, nullable=True)  # Timestamp when QR code expires
    qr_code_active = db.Column(db.Boolean, default=True)  # Whether the QR code is active
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    user = db.relationship("User", back_populates="folders")
    photos = db.relationship("Photo", back_populates="folder", cascade="all, delete-orphan")
    
    @classmethod
    def create_folder(cls, name, user_id, is_local=True, expiration_hours=None):
        """Create a new folder with a unique key.
        
        Args:
            name: The name of the folder
            user_id: The user ID who owns the folder
            is_local: Whether to use local storage (True) or cloud storage (False)
            expiration_hours: Number of hours the QR code will be valid (None means no expiration)
        """
        folder = cls(
            folder_name=name,
            folder_key=str(uuid.uuid4()),
            is_local=is_local,
            user_id=user_id,
            qr_code_active=True
        )
        
        # Set expiration time if provided
        if expiration_hours is not None:
            # QR code will be generated later, but we can set the expiration time
            # relative to the current time
            folder.qr_code_expires_at = datetime.utcnow() + timedelta(hours=expiration_hours)
            
        db.session.add(folder)
        db.session.commit()
        return folder
        
    def is_qr_code_expired(self):
        """Check if the QR code for this folder has expired.
        
        Returns:
            bool: True if expired, False otherwise
        """
        # If QR code is explicitly deactivated
        if not self.qr_code_active:
            return True
            
        # If no expiration time set, it doesn't expire
        if self.qr_code_expires_at is None:
            return False
            
        # Check if current time is past expiration time
        return datetime.utcnow() > self.qr_code_expires_at
        
    def deactivate_qr_code(self):
        """Deactivate the QR code for this folder.
        
        This makes the QR code invalid for uploads, but the folder remains accessible.
        """
        self.qr_code_active = False
        db.session.commit()


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