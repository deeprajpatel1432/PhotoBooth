import os
import io
import logging
import qrcode
import uuid
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload
from urllib.parse import urlparse, parse_qs
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key")
CORS(app)

# Configure database
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
db = SQLAlchemy(app)

# Setup Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    from models import User
    return User.query.get(int(user_id))

# Import models and create tables
with app.app_context():
    from models import User, DriveFolder, Upload
    db.create_all()
    
# Add template context processor for current year
@app.context_processor
def inject_now():
    return {'now': datetime.now()}

# Google Drive API scopes
# drive.file allows access only to files created or opened by the app
# userinfo scopes for profile and email information
SCOPES = [
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile',
    'https://www.googleapis.com/auth/drive.file'
]

# Google API credentials - use OAuth credentials 
CLIENT_ID = os.environ.get('GOOGLE_OAUTH_CLIENT_ID', os.environ.get('GOOGLE_CLIENT_ID', ''))
CLIENT_SECRET = os.environ.get('GOOGLE_OAUTH_CLIENT_SECRET', os.environ.get('GOOGLE_CLIENT_SECRET', ''))

# Create a client config dictionary for OAuth
CLIENT_CONFIG = {
    'web': {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
        'token_uri': 'https://oauth2.googleapis.com/token',
        'redirect_uris': []  # Will be set dynamically
    }
}

# Log the client ID (only first few characters for security)
if CLIENT_ID:
    print(f"Using Google OAuth Client ID: {CLIENT_ID[:8]}...")
else:
    print("WARNING: No Google OAuth Client ID found in environment variables")

if not CLIENT_SECRET:
    print("WARNING: No Google OAuth Client Secret found in environment variables")

def credentials_to_dict(credentials):
    return {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }

def extract_folder_id(drive_url):
    """Extract folder ID from a Google Drive URL."""
    parsed_url = urlparse(drive_url)
    
    # Handle different URL formats
    if parsed_url.netloc == 'drive.google.com':
        path = parsed_url.path.split('/')
        if 'folders' in path:
            folder_index = path.index('folders')
            if folder_index + 1 < len(path):
                return path[folder_index + 1]
        
        # For URLs like drive.google.com/drive/folders/FOLDER_ID
        if 'drive' in path and 'folders' in path:
            folder_index = path.index('folders')
            if folder_index + 1 < len(path):
                return path[folder_index + 1]
                
    # For URLs with 'id' parameter
    query_params = parse_qs(parsed_url.query)
    if 'id' in query_params:
        return query_params['id'][0]
    
    return None

def generate_qr_code(data):
    """Generate QR code image from data."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    img_io = io.BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    
    return img_io

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/admin')
def admin():
    # Get statistics
    stats = {
        'total_users': User.query.count(),
        'total_folders': DriveFolder.query.count(),
        'total_uploads': Upload.query.count()
    }
    
    # Get recent uploads
    uploads = Upload.query.order_by(Upload.upload_date.desc()).limit(10).all()
    
    # Get active folders
    folders = DriveFolder.query.order_by(DriveFolder.created_at.desc()).limit(10).all()
    
    return render_template('admin.html', stats=stats, uploads=uploads, folders=folders)

@app.route('/generate', methods=['GET', 'POST'])
def generate():
    if request.method == 'POST':
        # Determine storage type
        storage_type = request.form.get('storage_type', 'local')
        use_local_storage = storage_type == 'local'
        
        # Get folder information based on storage type
        folder_id = None
        folder_name = None
        
        if use_local_storage:
            # Local storage option
            folder_name = request.form.get('folder_name')
            
            if not folder_name:
                flash('Please enter a folder name', 'danger')
                return redirect(url_for('generate'))
            
            # Use the folder name as the folder ID for local storage
            folder_id = secure_filename(folder_name)
            
            # Create local folder if user is logged in
            if current_user.is_authenticated:
                uploads_dir = os.path.join("static", "uploads", str(current_user.id), folder_id)
                os.makedirs(uploads_dir, exist_ok=True)
                
                # Check if folder record exists
                drive_folder = DriveFolder.query.filter_by(
                    user_id=current_user.id,
                    folder_id=folder_id,
                    is_local=True
                ).first()
                
                if not drive_folder:
                    # Create new folder record
                    drive_folder = DriveFolder(
                        user_id=current_user.id,
                        folder_id=folder_id,
                        folder_name=folder_name,
                        local_path=uploads_dir,
                        is_local=True
                    )
                    db.session.add(drive_folder)
                    db.session.commit()
        else:
            # Google Drive option
            drive_url = request.form.get('drive_url')
            
            if not drive_url:
                flash('Please enter a Google Drive folder URL', 'danger')
                return redirect(url_for('generate'))
            
            folder_id = extract_folder_id(drive_url)
            
            if not folder_id:
                flash('Invalid Google Drive folder URL', 'danger')
                return redirect(url_for('generate'))
            
            # Store in database if user is logged in
            if current_user.is_authenticated:
                # Check if folder exists for this user
                drive_folder = DriveFolder.query.filter_by(
                    user_id=current_user.id,
                    folder_id=folder_id,
                    is_local=False
                ).first()
                
                if not drive_folder:
                    # Create new folder record
                    drive_folder = DriveFolder(
                        user_id=current_user.id,
                        folder_id=folder_id,
                        folder_url=f"https://drive.google.com/drive/folders/{folder_id}",
                        is_local=False
                    )
                    db.session.add(drive_folder)
                    db.session.commit()
        
        # Store folder ID and storage type in session
        session['folder_id'] = folder_id
        session['use_local_storage'] = use_local_storage
        
        # Generate a unique token for this QR code
        qr_token = str(uuid.uuid4())
        session['qr_token'] = qr_token
        
        # Create QR code data (URL to the scan page with token and storage info)
        storage_param = 'local=true' if use_local_storage else 'local=false'
        qr_data = f"{request.host_url}scan?token={qr_token}&folder={folder_id}&{storage_param}"
        
        # Store QR data in session for display
        session['qr_data'] = qr_data
        
        return render_template('generate.html', qr_data=qr_data, folder_id=folder_id)
    
    return render_template('generate.html')

@app.route('/scan')
def scan():
    token = request.args.get('token')
    folder_id = request.args.get('folder')
    use_local_storage = request.args.get('local') == 'true'
    
    if not token or not folder_id:
        flash('Invalid QR code', 'danger')
        return redirect(url_for('index'))
    
    # Store the storage preference in session
    session['use_local_storage'] = use_local_storage
    
    return render_template('scan.html', token=token, folder_id=folder_id, use_local_storage=use_local_storage)

@app.route('/authorize')
def authorize():
    # Create flow instance to manage OAuth 2.0 Authorization Grant Flow
    # Determine the correct redirect URI based on the request
    redirect_uri = None
    
    # Always use the full request host for the redirect URI
    # This ensures we match exactly what Google sees in the redirect
    protocol = "https" if request.headers.get('X-Forwarded-Proto') == 'https' else "http"
    redirect_uri = f"{protocol}://{request.host}/oauth2callback"
    
    # Log the redirect URI for debugging
    logger.debug(f"Using redirect URI: {redirect_uri}")
    print(f"Using redirect URI: {redirect_uri}")
    with open("redirect_uri.txt", "w") as f:
        f.write(redirect_uri)
    
    # Update CLIENT_CONFIG with the current redirect URI
    CLIENT_CONFIG['web']['redirect_uris'] = [redirect_uri]
    
    # Create flow using from_client_config method
    flow = Flow.from_client_config(
        CLIENT_CONFIG,
        scopes=SCOPES,
        redirect_uri=redirect_uri
    )
    
    # Generate URL for request to Google's OAuth 2.0 server
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'  # Force the consent screen to show every time
    )
    
    # Store the state in the session for later validation
    session['state'] = state
    
    return redirect(authorization_url)

@app.route('/oauth2callback')
def oauth2callback():
    # Specify the state when creating the flow in the callback
    state = session.get('state', None)
    
    # Always use the full request host for the redirect URI
    # This ensures we match exactly what Google sees in the redirect
    protocol = "https" if request.headers.get('X-Forwarded-Proto') == 'https' else "http"
    redirect_uri = f"{protocol}://{request.host}/oauth2callback"
    
    # Log the redirect URI for debugging
    logger.debug(f"Using callback redirect URI: {redirect_uri}")
    print(f"Using callback redirect URI: {redirect_uri}")
    
    # Update CLIENT_CONFIG with the current redirect URI
    CLIENT_CONFIG['web']['redirect_uris'] = [redirect_uri]
    
    # Create flow using from_client_config method
    flow = Flow.from_client_config(
        CLIENT_CONFIG,
        scopes=SCOPES,
        state=state,
        redirect_uri=redirect_uri
    )
    
    # Use the authorization server's response to fetch the OAuth 2.0 tokens
    authorization_response = request.url
    logger.debug(f"OAuth callback URL: {authorization_response}")
    
    # Make sure the URL is absolute and has https if needed
    if not authorization_response.startswith('http'):
        if request.headers.get('X-Forwarded-Proto') == 'https':
            base_url = f"https://{request.host}"
        else:
            base_url = f"http://{request.host}"
        authorization_response = f"{base_url}{request.full_path}"
        logger.debug(f"Updated OAuth callback URL: {authorization_response}")
    
    try:
        flow.fetch_token(authorization_response=authorization_response)
    except Exception as oauth_error:
        logger.error(f"Error during OAuth token fetch: {oauth_error}")
        flash("Authentication failed. Please try again.", "danger")
        return redirect(url_for('index'))
    
    # Store credentials in the session
    credentials = flow.credentials
    session['credentials'] = credentials_to_dict(credentials)
    
    # Get user info from Google
    try:
        # Build the service
        service = build('oauth2', 'v2', credentials=credentials)
        # Get user info
        user_info = service.userinfo().get().execute()
        
        # Extract user data
        google_id = user_info.get('id')
        email = user_info.get('email')
        name = user_info.get('name')
        profile_picture = user_info.get('picture')
        
        # Store in database
        user = User.query.filter_by(google_id=google_id).first()
        
        if not user:
            # Create new user
            user = User(
                google_id=google_id,
                email=email,
                name=name,
                profile_picture=profile_picture
            )
            db.session.add(user)
        else:
            # Update existing user
            user.email = email
            user.name = name
            user.profile_picture = profile_picture
            user.last_login = datetime.utcnow()
        
        db.session.commit()
        
        # Store user ID in session
        session['user_id'] = user.id
    except Exception as e:
        logger.error(f"Error getting user info: {e}")
    
    # Redirect back to the upload page
    folder_id = session.get('folder_id')
    qr_token = session.get('qr_token')
    
    if folder_id and qr_token:
        # Store folder in database if not already there
        if 'user_id' in session:
            user_id = session['user_id']
            
            # Check if folder exists for this user
            drive_folder = DriveFolder.query.filter_by(
                user_id=user_id,
                folder_id=folder_id
            ).first()
            
            if not drive_folder:
                # Create new folder record
                drive_folder = DriveFolder(
                    user_id=user_id,
                    folder_id=folder_id,
                    folder_url=f"https://drive.google.com/drive/folders/{folder_id}"
                )
                db.session.add(drive_folder)
                db.session.commit()
        
        return redirect(url_for('scan', token=qr_token, folder=folder_id, auth='true'))
    else:
        return redirect(url_for('index'))

@app.route('/check_auth', methods=['GET'])
def check_auth():
    """Check if the user is authenticated with Google Drive or with local login"""
    # Check if user is authenticated via Flask-Login
    if current_user.is_authenticated:
        return jsonify({
            'authenticated': True,
            'user_id': current_user.id
        })
    # Check if user is authenticated via Google OAuth
    is_authenticated = 'credentials' in session
    logger.debug(f"Auth check: authenticated={is_authenticated}")
    return jsonify({
        'authenticated': is_authenticated,
        'user_id': session.get('user_id') if is_authenticated else None
    })

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            login_user(user)
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            # Store user ID in session for compatibility with other parts of the app
            session['user_id'] = user.id
            
            next_page = request.args.get('next')
            if not next_page or not next_page.startswith('/'):
                next_page = url_for('index')
            
            return redirect(next_page)
        else:
            flash('Invalid email or password', 'danger')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        email = request.form.get('email')
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Validate inputs
        error = None
        if not email or not username or not password:
            error = 'All fields are required'
        elif password != confirm_password:
            error = 'Passwords do not match'
        elif User.query.filter_by(email=email).first():
            error = 'Email already registered'
        
        if error:
            flash(error, 'danger')
        else:
            # Create new user
            user = User(
                email=email,
                name=username,
                use_local_storage=True
            )
            user.set_password(password)
            
            db.session.add(user)
            db.session.commit()
            
            flash('Registration successful! You can now log in.', 'success')
            return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """User profile settings page"""
    if request.method == 'POST':
        # Update user profile
        name = request.form.get('name')
        storage_preference = request.form.get('storage_preference')
        
        # Update user object
        if name:
            current_user.name = name
        
        # Update storage preference
        if storage_preference:
            current_user.use_local_storage = (storage_preference == 'local')
        
        # Save changes
        db.session.commit()
        
        flash('Profile settings updated successfully', 'success')
        return redirect(url_for('profile'))
    
    return render_template('profile.html')

@app.route('/logout')
def logout():
    # Clear Flask-Login
    logout_user()
    
    # Clear session variables for Google OAuth
    if 'credentials' in session:
        del session['credentials']
    if 'user_id' in session:
        del session['user_id']
    
    return redirect(url_for('index'))

@app.route('/download/<int:upload_id>')
@login_required
def download_file(upload_id):
    upload = Upload.query.get_or_404(upload_id)
    
    # Check if user has access to this upload
    if upload.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
        
    if upload.is_local:
        # For local files
        return send_file(upload.local_path, 
                        download_name=upload.file_name,
                        as_attachment=True)
    else:
        # For Google Drive files, redirect to the file URL
        return redirect(upload.file_url)

@app.route('/upload', methods=['POST'])
def upload_to_drive():
    try:
        # Get the file from request
        if 'file' not in request.files:
            return jsonify({'status': 'error', 'message': 'No file part'}), 400
        
        file = request.files['file']
        folder_id = request.form.get('folder_id')
        
        if not file or not folder_id:
            return jsonify({'status': 'error', 'message': 'Missing file or folder ID'}), 400
        
        # Calculate file size
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)  # Reset file pointer
        
        # Check if user is authenticated with Google Drive or with local login
        # First check if we have the storage type in the session (from QR code scan)
        use_local_storage = session.get('use_local_storage', True)
        user_id = None
        
        if current_user.is_authenticated:
            user_id = current_user.id
            # If session has a storage preference, use that; otherwise use user's preference
            if 'use_local_storage' not in session:
                use_local_storage = current_user.use_local_storage
        elif 'user_id' in session:
            user_id = session.get('user_id')
            # Look up user to determine storage preference if not in session
            if 'use_local_storage' not in session:
                user = User.query.get(user_id)
                if user:
                    use_local_storage = user.use_local_storage
        
        if not user_id:
            return jsonify({'status': 'error', 'message': 'Not authorized'}), 401
        
        # Find drive folder record
        drive_folder = DriveFolder.query.filter_by(
            user_id=user_id,
            folder_id=folder_id
        ).first()
        
        if not drive_folder:
            # Create a new folder record if it doesn't exist
            folder_name = f"uploads_{folder_id}"
            drive_folder = DriveFolder(
                user_id=user_id,
                folder_id=folder_id,
                folder_name=folder_name,
                is_local=use_local_storage
            )
            
            if use_local_storage:
                # Create a local folder for the user's uploads
                uploads_dir = os.path.join("static", "uploads", str(user_id), folder_id)
                os.makedirs(uploads_dir, exist_ok=True)
                drive_folder.local_path = uploads_dir
            else:
                drive_folder.folder_url = f"https://drive.google.com/drive/folders/{folder_id}"
                
            db.session.add(drive_folder)
            db.session.commit()
        
        # Handle the upload based on the storage type
        if use_local_storage or not 'credentials' in session:
            # Local file upload
            filename = secure_filename(file.filename)
            local_path = os.path.join("static", "uploads", str(user_id), folder_id, filename)
            
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            
            # Save the file
            file.save(local_path)
            
            # Create unique file ID
            file_id = str(uuid.uuid4())
            
            # Create a URL to access the file
            file_url = f"/static/uploads/{user_id}/{folder_id}/{filename}"
            
            # Record upload in database
            upload = Upload(
                file_name=filename,
                file_id=file_id,
                file_url=file_url,
                file_size=file_size,
                mime_type=file.content_type,
                is_local=True,
                local_path=local_path,
                user_id=user_id,
                folder_id=drive_folder.id
            )
            db.session.add(upload)
            db.session.commit()
            
            logger.debug(f"Recorded local upload to database: {upload.file_name}")
            
            return jsonify({
                'status': 'success',
                'message': 'File uploaded successfully (local storage)',
                'file_id': file_id,
                'file_name': filename,
                'file_link': file_url
            }), 200
            
        else:
            # Google Drive upload
            try:
                # Create credentials object
                credentials = Credentials(**session['credentials'])
                
                # Build the Drive API client
                drive_service = build('drive', 'v3', credentials=credentials)
                
                # Prepare file metadata
                file_metadata = {
                    'name': file.filename,
                    'parents': [folder_id]
                }
                
                logger.debug(f"Uploading file to Drive: {file.filename}, type: {file.content_type}, to folder: {folder_id}")
                media = MediaIoBaseUpload(
                    file,
                    mimetype=file.content_type,
                    resumable=True
                )
                
                # Verify folder permissions
                try:
                    # Check if we can access the folder first
                    folder_check = drive_service.files().get(
                        fileId=folder_id,
                        fields='id,name,mimeType'
                    ).execute()
                    
                    logger.debug(f"Folder check result: {folder_check}")
                    
                    if folder_check.get('mimeType') != 'application/vnd.google-apps.folder':
                        logger.error(f"ID {folder_id} is not a folder: {folder_check.get('mimeType')}")
                        return jsonify({'status': 'error', 'message': 'The provided ID is not a folder'}), 400
                    
                except Exception as folder_error:
                    logger.error(f"Error checking folder: {folder_error}")
                    return jsonify({
                        'status': 'error', 
                        'message': f'Cannot access the target folder. Check permissions or folder ID. Detail: {str(folder_error)}'
                    }), 403
                
                uploaded_file = drive_service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id,name,webViewLink,mimeType'
                ).execute()
                
                logger.debug(f"File uploaded successfully to Drive: {uploaded_file}")
                
                # Create upload record
                upload = Upload(
                    file_name=uploaded_file.get('name'),
                    file_id=uploaded_file.get('id'),
                    file_url=uploaded_file.get('webViewLink'),
                    file_size=file_size,
                    mime_type=uploaded_file.get('mimeType'),
                    is_local=False,
                    user_id=user_id,
                    folder_id=drive_folder.id
                )
                db.session.add(upload)
                db.session.commit()
                logger.debug(f"Recorded Drive upload to database: {upload.file_name}")
                
                return jsonify({
                    'status': 'success',
                    'message': 'File uploaded successfully to Google Drive',
                    'file_id': uploaded_file.get('id'),
                    'file_name': uploaded_file.get('name'),
                    'file_link': uploaded_file.get('webViewLink')
                }), 200
                
            except Exception as upload_error:
                logger.error(f"Error during Drive file upload: {upload_error}")
                return jsonify({'status': 'error', 'message': f'Error uploading file to Google Drive: {str(upload_error)}'}), 500
        
        # This should never be reached
        return jsonify({'status': 'error', 'message': 'Unknown upload path'}), 500
        
    except HttpError as error:
        logger.error(f"An error occurred: {error}")
        return jsonify({'status': 'error', 'message': str(error)}), 500
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        return jsonify({'status': 'error', 'message': 'An unexpected error occurred'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
