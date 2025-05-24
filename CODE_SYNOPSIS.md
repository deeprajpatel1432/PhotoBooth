# Flask Photobooth Application - Code Synopsis

## Core Files & Structure

### Application Foundation
- **app.py**: Flask application setup, database configuration, login manager initialization
- **main.py**: Entry point for running the application
- **models.py**: Database models for User, PhotoFolder, and Photo with relationships
- **routes.py**: All HTTP endpoints and request handling 
- **utils.py**: Helper functions for file operations, QR code generation, and token management

### Frontend
- **templates/**: HTML templates for all pages
- **static/**: CSS, JavaScript, and uploaded images/QR codes

## Key Database Models

### User Model
```python
class User(UserMixin, db.Model):
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
```

### PhotoFolder Model
```python
class PhotoFolder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    folder_name = db.Column(db.String(255), nullable=False)
    folder_key = db.Column(db.String(100), nullable=False, unique=True)
    is_local = db.Column(db.Boolean, default=True)
    qr_code_url = db.Column(db.String(512), nullable=True)
    qr_code_generated_at = db.Column(db.DateTime, nullable=True)
    qr_code_expires_at = db.Column(db.DateTime, nullable=True)
    qr_code_active = db.Column(db.Boolean, default=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Methods
    @classmethod
    def create_folder(cls, name, user_id, is_local=True, expiration_hours=None)
    def is_qr_code_expired(self)
    def deactivate_qr_code(self)
```

### Photo Model
```python
class Photo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    file_name = db.Column(db.String(255), nullable=False)
    original_name = db.Column(db.String(255), nullable=True)
    file_url = db.Column(db.String(512), nullable=False)
    file_size = db.Column(db.Integer, nullable=True)
    mime_type = db.Column(db.String(100), nullable=True)
    is_local = db.Column(db.Boolean, default=True)
    local_path = db.Column(db.String(512), nullable=True)
    delete_hash = db.Column(db.String(100), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    folder_id = db.Column(db.Integer, db.ForeignKey('photo_folders.id'), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
```

## Key Features Implementation

### QR Code Expiration System
The application has a multi-layered QR code expiration system:

1. **Session Expiration**: 60-second timeout in the scan route:
```python
# In routes.py (scan route)
if folder.qr_code_generated_at:
    now = datetime.utcnow()
    expiry_time = folder.qr_code_generated_at
    time_difference = (now - expiry_time).total_seconds()
    qr_expired = time_difference > 60  # 60 seconds expiry time for scan session
    
    if qr_expired:
        # Regenerate QR code
        scan_url = url_for("scan", folder_key=folder.folder_key, _external=True)
        qr_url = generate_qr_url(scan_url)
```

2. **Permanent Expiration**: Configurable in hours via the `create_folder` method:
```python
# In models.py (PhotoFolder)
@classmethod
def create_folder(cls, name, user_id, is_local=True, expiration_hours=None):
    # ...
    if expiration_hours is not None:
        folder.qr_code_expires_at = datetime.utcnow() + timedelta(hours=expiration_hours)
```

3. **Manual Deactivation**: Via the deactivate_folder_qr route:
```python
# In routes.py
@app.route("/folder/deactivate_qr/<int:folder_id>")
@login_required
def deactivate_folder_qr(folder_id):
    # ...
    folder.deactivate_qr_code()
```

### Storage System
The application supports both local and cloud storage (catbox.moe):

```python
# In routes.py (upload route)
if folder.is_local:
    result = save_local_file(file, file.filename)
else:
    result = upload_to_catbox(file)
```

With fallback mechanism in utils.py:
```python
def upload_to_catbox(file):
    # ...
    try:
        # Upload to catbox.moe...
    except Exception:
        # Return local fallback result if catbox.moe fails
        return local_fallback_result
```

### Secure Photo Sharing
Implemented using time-limited tokens:

```python
# In utils.py
def generate_share_token(photo_id):
    # Create a payload with photo ID and timestamp (24-hour validity)
    timestamp = int(time.time()) + (24 * 60 * 60)  # Current time + 24 hours
    payload = f"{photo_id}:{timestamp}"
    
    # Encode the payload using base64
    token = base64.urlsafe_b64encode(payload.encode()).decode()
    
    return token

def decode_share_token(token):
    try:
        # Decode the token
        payload = base64.urlsafe_b64decode(token.encode()).decode()
        
        # Split the payload into photo_id and timestamp
        photo_id_str, timestamp_str = payload.split(":")
        photo_id = int(photo_id_str)
        timestamp = int(timestamp_str)
        
        # Check if the token has expired
        current_time = int(time.time())
        if current_time > timestamp:
            return None
        
        return photo_id
    except Exception:
        return None
```

## Main Routes

### Core Navigation
- `/`: Home page
- `/login`, `/register`: User authentication
- `/profile`: User profile
- `/folders`: List all folders
- `/view_folder/<folder_key>`: View photos in a folder

### QR Code Features
- `/generate`: Generate new QR code for a folder
- `/scan/<folder_key>`: QR code scanning and upload interface

### Photo Management
- `/upload`: Handle photo uploads
- `/photo/download/<photo_id>`: Download a photo
- `/photo/delete/<photo_id>`: Delete a photo
- `/photo/share/<photo_id>`: Share a photo via token
- `/shared/<share_token>`: View a shared photo

### Folder Management
- `/folder/deactivate_qr/<folder_id>`: Deactivate a QR code
- `/folder/delete/<folder_id>`: Delete a folder and all its photos

## Key JavaScript Functionality

### QR Code Scanning
- Camera activation and image capture
- Device camera switching

### File Upload
- Drag and drop support
- Progress tracking
- Multiple file handling

### UI Features
- Copy-to-clipboard for share links
- Toast notifications 
- Photo gallery sorting
- Delete confirmations