import os
import uuid
import logging
from datetime import datetime
from functools import wraps

import requests
from werkzeug.utils import secure_filename
from flask import render_template, request, redirect, url_for, flash, jsonify, send_from_directory, abort, session
from flask_login import login_user, logout_user, login_required, current_user

from app import app, db
from models import User, PhotoFolder, Photo
from utils import allowed_file, upload_to_catbox, generate_qr_url, get_file_info, save_local_file

logger = logging.getLogger(__name__)


def admin_required(f):
    """Decorator for routes that require admin access."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.id != 1:  # Simple admin check
            flash('You do not have permission to access this page.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function


@app.route('/')
def index():
    """Home page."""
    return render_template('index.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login."""
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        remember = 'remember' in request.form
        
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            login_user(user, remember=remember)
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            # Get next page or default to index
            next_page = request.args.get('next')
            if not next_page or not next_page.startswith('/'):
                next_page = url_for('index')
                
            flash('Login successful!', 'success')
            return redirect(next_page)
        else:
            flash('Invalid email or password', 'danger')
    
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    """User registration."""
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Validate input
        if not email or not username or not password:
            flash('All fields are required', 'danger')
            return redirect(url_for('register'))
        
        if password != confirm_password:
            flash('Passwords do not match', 'danger')
            return redirect(url_for('register'))
        
        # Check if user exists
        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'danger')
            return redirect(url_for('register'))
        
        # Create new user
        user = User(email=email, name=username)
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        flash('Registration successful! You can now log in.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')


@app.route('/logout')
@login_required
def logout():
    """User logout."""
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))


@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """User profile page."""
    if request.method == 'POST':
        name = request.form.get('name')
        storage_preference = request.form.get('storage_preference', 'local')
        
        current_user.name = name
        current_user.use_local_storage = (storage_preference == 'local')
        
        db.session.commit()
        
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('profile'))
    
    return render_template('profile.html')


@app.route('/generate', methods=['GET', 'POST'])
@login_required
def generate():
    """Generate QR code for folder."""
    if request.method == 'POST':
        storage_type = request.form.get('storage_type', 'local')
        folder_name = request.form.get('folder_name', '')
        
        # Set session storage type
        session['use_local_storage'] = (storage_type == 'local')
        
        # Generate a unique folder key
        folder_key = str(uuid.uuid4())
        
        # Create folder record
        folder = PhotoFolder(
            folder_name=folder_name,
            folder_key=folder_key,
            is_local=session['use_local_storage'],
            user_id=current_user.id
        )
        
        db.session.add(folder)
        db.session.commit()
        
        # Generate QR code URL for the folder
        qr_data = url_for('scan', folder_key=folder_key, _external=True)
        
        return render_template('generate.html', 
                             qr_data=qr_data, 
                             folder_id=folder_key,
                             folder=folder)
    
    return render_template('generate.html')


@app.route('/scan/<folder_key>')
def scan(folder_key):
    """Upload page for scanning QR code."""
    folder = PhotoFolder.query.filter_by(folder_key=folder_key).first_or_404()
    
    # Create a token for non-authenticated uploads
    token = str(uuid.uuid4())
    session[f'upload_token_{folder_key}'] = token
    
    return render_template('scan.html', 
                         folder_id=folder_key,
                         token=token,
                         use_local_storage=folder.is_local)


@app.route('/admin')
@login_required
@admin_required
def admin():
    """Admin dashboard."""
    users = User.query.all()
    folders = PhotoFolder.query.all()
    photos = Photo.query.all()
    
    return render_template('admin.html', 
                         users=users,
                         folders=folders,
                         photos=photos)


@app.route('/upload', methods=['POST'])
def upload():
    """Handle file uploads."""
    folder_key = request.form.get('folder_id')
    token = request.form.get('token')
    
    # Validate folder and token
    folder = PhotoFolder.query.filter_by(folder_key=folder_key).first()
    
    if not folder:
        return jsonify({'success': False, 'error': 'Invalid folder ID'}), 400
    
    # Check token for non-authenticated users
    stored_token = session.get(f'upload_token_{folder_key}')
    if not current_user.is_authenticated and (not stored_token or stored_token != token):
        return jsonify({'success': False, 'error': 'Invalid upload token'}), 403
    
    # Check if a file was provided
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400
    
    file = request.files['file']
    
    # Validate file
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'success': False, 'error': 'File type not allowed'}), 400
    
    # Process the file
    try:
        original_filename = secure_filename(file.filename)
        file_info = get_file_info(file)
        
        # Generate a unique filename
        unique_filename = f"{uuid.uuid4()}_{original_filename}"
        
        if folder.is_local:
            # Save locally
            file_path = save_local_file(file, unique_filename)
            file_url = url_for('static', filename=f'uploads/{unique_filename}', _external=True)
            
            photo = Photo(
                file_name=unique_filename,
                original_name=original_filename,
                file_url=file_url,
                file_size=file_info['size'],
                mime_type=file_info['mime_type'],
                is_local=True,
                local_path=file_path,
                user_id=folder.user_id,
                folder_id=folder.id
            )
            
        else:
            # Upload to catbox.moe
            result = upload_to_catbox(file)
            
            if not result['success']:
                return jsonify({'success': False, 'error': result['error']}), 500
            
            photo = Photo(
                file_name=unique_filename,
                original_name=original_filename,
                file_url=result['url'],
                file_size=file_info['size'],
                mime_type=file_info['mime_type'],
                is_local=False,
                user_id=folder.user_id,
                folder_id=folder.id
            )
        
        db.session.add(photo)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'file_url': photo.file_url,
            'file_name': photo.original_name,
            'file_size': photo.file_size,
            'uploaded_at': photo.uploaded_at.strftime('%Y-%m-%d %H:%M:%S')
        })
        
    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/check_auth')
def check_auth():
    """Check if the user is authenticated."""
    return jsonify({'authenticated': current_user.is_authenticated})


@app.route('/download/<int:photo_id>')
@login_required
def download_photo(photo_id):
    """Download a photo."""
    photo = Photo.query.get_or_404(photo_id)
    
    # Check if user has permission
    if photo.user_id != current_user.id and not current_user.id == 1:
        abort(403)
    
    if photo.is_local and photo.local_path:
        directory, filename = os.path.split(photo.local_path)
        return send_from_directory(directory, filename, as_attachment=True, download_name=photo.original_name)
    else:
        # For catbox.moe files, redirect to the URL
        return redirect(photo.file_url)
