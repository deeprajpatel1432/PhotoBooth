import os
import uuid
import json
import logging
from functools import wraps
from datetime import datetime

from werkzeug.utils import secure_filename
from flask import render_template, redirect, url_for, flash, request, jsonify, send_file, abort
from flask_login import login_user, logout_user, current_user, login_required

from app import app, db
from models import User, PhotoFolder, Photo
from utils import allowed_file, save_local_file, upload_to_catbox, generate_qr_url, generate_share_token, decode_share_token

# Set up logging
logger = logging.getLogger(__name__)

# Admin decorator
def admin_required(f):
    """Decorator for routes that require admin access."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash("You don't have permission to access this page.", "danger")
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return decorated_function

# Routes
@app.route("/")
def index():
    """Home page."""
    # If user is logged in, get their recent folders
    folders = []
    if current_user.is_authenticated:
        folders = PhotoFolder.query.filter_by(user_id=current_user.id).order_by(PhotoFolder.created_at.desc()).limit(3).all()
    return render_template("index.html", folders=folders)

@app.route("/login", methods=["GET", "POST"])
def login():
    """User login."""
    if current_user.is_authenticated:
        return redirect(url_for("index"))
        
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        remember = "remember" in request.form
        
        # Find the user by email
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            login_user(user, remember=remember)
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            next_page = request.args.get("next")
            return redirect(next_page or url_for("index"))
        else:
            flash("Invalid email or password. Please try again.", "danger")
    
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    """User registration."""
    if current_user.is_authenticated:
        return redirect(url_for("index"))
        
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")
        password_confirm = request.form.get("password_confirm")
        storage_preference = request.form.get("storage_preference", "local")
        
        # Validate inputs
        if not all([name, email, password, password_confirm]):
            flash("All fields are required.", "danger")
            return render_template("register.html")
            
        if password != password_confirm:
            flash("Passwords don't match.", "danger")
            return render_template("register.html")
            
        if len(password) < 8:
            flash("Password must be at least 8 characters long.", "danger")
            return render_template("register.html")
            
        # Check if user already exists
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash("An account with this email already exists.", "danger")
            return render_template("register.html")
            
        # Create a new user
        user = User(
            name=name,
            email=email,
            use_local_storage=(storage_preference == "local")
        )
        user.set_password(password)
        
        # Set the first user as admin
        if User.query.count() == 0:
            user.is_admin = True
            
        db.session.add(user)
        db.session.commit()
        
        flash("Account created successfully! You can now log in.", "success")
        return redirect(url_for("login"))
    
    return render_template("register.html")

@app.route("/logout")
@login_required
def logout():
    """User logout."""
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    """User profile page."""
    # Get user's folders
    folders = PhotoFolder.query.filter_by(user_id=current_user.id).order_by(PhotoFolder.created_at.desc()).all()
    
    if request.method == "POST":
        name = request.form.get("name")
        storage_preference = request.form.get("storage_preference", "local")
        
        # Update user profile
        current_user.name = name
        current_user.use_local_storage = (storage_preference == "local")
        db.session.commit()
        
        flash("Profile updated successfully.", "success")
        return redirect(url_for("profile"))
    
    return render_template("profile.html", folders=folders)

@app.route("/folders")
@login_required
def folders():
    """Display all user folders."""
    folders = PhotoFolder.query.filter_by(user_id=current_user.id).order_by(PhotoFolder.created_at.desc()).all()
    return render_template("folders.html", folders=folders)

@app.route("/folder/view/<folder_key>")
@login_required
def view_folder(folder_key):
    """View photos in a specific folder."""
    folder = PhotoFolder.query.filter_by(folder_key=folder_key).first_or_404()
    
    # Check if the current user has permission to view this folder
    if folder.user_id != current_user.id and not current_user.is_admin:
        flash("You don't have permission to view this folder.", "danger")
        return redirect(url_for("folders"))
    
    # Get sort parameter
    sort = request.args.get("sort", "newest")
    
    # Query photos with sorting
    photos_query = Photo.query.filter_by(folder_id=folder.id)
    
    if sort == "newest":
        photos_query = photos_query.order_by(Photo.uploaded_at.desc())
    elif sort == "oldest":
        photos_query = photos_query.order_by(Photo.uploaded_at.asc())
    elif sort == "name":
        photos_query = photos_query.order_by(Photo.original_name.asc())
    elif sort == "size":
        photos_query = photos_query.order_by(Photo.file_size.desc())
    
    photos = photos_query.all()
    
    return render_template("view_folder.html", folder=folder, photos=photos, sort=sort)

@app.route("/generate", methods=["GET", "POST"])
@login_required
def generate():
    """Generate QR code for folder."""
    try:
        if request.method == "POST":
            folder_name = request.form.get("folder_name")
            storage_type = request.form.get("storage_type", "local")
            expiration_time = request.form.get("expiration_time")  # In hours
            
            if not folder_name:
                flash("Folder name is required.", "danger")
                return redirect(url_for("generate"))
            
            # Convert expiration_time to integer if provided
            expiration_hours = None
            if expiration_time and expiration_time.strip():
                try:
                    expiration_hours = int(expiration_time)
                    if expiration_hours <= 0:
                        flash("Expiration time must be a positive number.", "warning")
                        expiration_hours = None
                except ValueError:
                    flash("Invalid expiration time provided. Using no expiration.", "warning")
            
            logger.info(f"Creating new folder: {folder_name}, storage type: {storage_type}, expiration: {expiration_hours} hours")
            
            is_local = (storage_type == "local")
            
            # Create a new folder
            folder = PhotoFolder.create_folder(
                name=folder_name,
                user_id=current_user.id,
                is_local=is_local,
                expiration_hours=expiration_hours
            )
            
            logger.info(f"Folder created with ID: {folder.id}, key: {folder.folder_key}")
            
            # Generate QR code for the folder
            scan_url = url_for("scan", folder_key=folder.folder_key, _external=True)
            logger.info(f"Generating QR code for URL: {scan_url}")
            
            qr_url = generate_qr_url(scan_url)
            
            if qr_url:
                logger.info(f"QR code generated successfully: {qr_url}")
                # Save the QR code URL to the folder and timestamp
                folder.qr_code_url = qr_url
                folder.qr_code_generated_at = datetime.utcnow()
                db.session.commit()
                
                # Copy QR code to make it accessible by folder key for stability
                try:
                    qr_source_path = os.path.join(app.root_path, 'static', qr_url.lstrip('/static/'))
                    qr_dest_name = f"{folder.folder_key}.png"
                    qr_dest_path = os.path.join(app.config['QR_CODE_FOLDER'], qr_dest_name)
                    
                    import shutil
                    shutil.copy2(qr_source_path, qr_dest_path)
                    logger.info(f"QR code copied to: {qr_dest_path}")
                except Exception as e:
                    logger.error(f"Error copying QR code for folder stability: {str(e)}")
                
                return render_template("generate.html", folder=folder, qr_data=scan_url)
            else:
                # QR code generation failed
                logger.error("QR code generation failed")
                flash("There was a problem generating the QR code. Please try again.", "danger")
                return redirect(url_for("generate"))
        
        return render_template("generate.html")
    except Exception as e:
        logger.error(f"Error in generate route: {str(e)}")
        flash("There was a problem creating your folder. Please try again.", "danger")
        return redirect(url_for("folders"))

@app.route("/scan/<folder_key>")
def scan(folder_key):
    """Upload page for scanning QR code."""
    try:
        folder = PhotoFolder.query.filter_by(folder_key=folder_key).first_or_404()
        
        # Check if QR code is active or expired
        if not folder.qr_code_active:
            logger.info(f"QR code manually deactivated for folder: {folder.folder_name}")
            reason = "The QR code has been manually deactivated by the owner."
            return render_template(
                "qr_expired.html",
                folder=folder,
                reason=reason,
                user_owns_folder=current_user.is_authenticated and current_user.id == folder.user_id,
                is_authenticated=current_user.is_authenticated
            )
        
        # Check if the QR code has permanently expired (time-limited expiry)
        if folder.is_qr_code_expired():
            logger.info(f"QR code permanently expired for folder: {folder.folder_name}")
            reason = "The QR code has expired."
            if folder.qr_code_expires_at:
                reason += f" It expired on {folder.qr_code_expires_at.strftime('%Y-%m-%d %H:%M UTC')}."
            
            return render_template(
                "qr_expired.html",
                folder=folder,
                reason=reason,
                user_owns_folder=current_user.is_authenticated and current_user.id == folder.user_id,
                is_authenticated=current_user.is_authenticated
            )
        
        # Generate a token for the upload
        token = str(uuid.uuid4())
        
        # Check for temporary QR code expiry (60 seconds for scan session)
        qr_expired = False
        if folder.qr_code_generated_at:
            now = datetime.utcnow()
            expiry_time = folder.qr_code_generated_at
            time_difference = (now - expiry_time).total_seconds()
            qr_expired = time_difference > 60  # 60 seconds expiry time for scan session
            
            if qr_expired:
                logger.info(f"QR code scan session expired for folder: {folder.folder_name}. Regenerating...")
                # Regenerate QR code
                scan_url = url_for("scan", folder_key=folder.folder_key, _external=True)
                qr_url = generate_qr_url(scan_url)
                
                if qr_url:
                    folder.qr_code_url = qr_url
                    folder.qr_code_generated_at = datetime.utcnow()
                    # Don't reset the qr_code_expires_at field here - that's a separate time limit
                    db.session.commit()
                    
                    # Copy QR code for stability
                    try:
                        qr_source_path = os.path.join(app.root_path, 'static', qr_url.lstrip('/static/'))
                        qr_dest_name = f"{folder.folder_key}.png"
                        qr_dest_path = os.path.join(app.config['QR_CODE_FOLDER'], qr_dest_name)
                        
                        import shutil
                        shutil.copy2(qr_source_path, qr_dest_path)
                        logger.info(f"Regenerated QR code copied to: {qr_dest_path}")
                    except Exception as e:
                        logger.error(f"Error copying regenerated QR code: {str(e)}")
        
        logger.info(f"Rendering scan page for folder: {folder.folder_name} (key: {folder_key})")
        
        # If expiration time is set, add it to the template context
        expires_at = None
        if folder.qr_code_expires_at:
            expires_at = folder.qr_code_expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')
        
        return render_template(
            "scan.html", 
            folder_id=folder.folder_key, 
            folder_name=folder.folder_name,
            use_local_storage=folder.is_local,
            token=token,
            qr_refreshed=qr_expired,  # Pass to template if QR was just refreshed
            expires_at=expires_at  # Pass expiration time to template
        )
    except Exception as e:
        logger.error(f"Error in scan route: {str(e)}")
        flash("Error displaying the upload page. Please try again.", "danger")
        return redirect(url_for("index"))

@app.route("/admin")
@login_required
@admin_required
def admin():
    """Admin dashboard."""
    users = User.query.order_by(User.created_at.desc()).all()
    folders = PhotoFolder.query.order_by(PhotoFolder.created_at.desc()).all()
    photos = Photo.query.order_by(Photo.uploaded_at.desc()).limit(50).all()
    
    return render_template(
        "admin.html", 
        users=users, 
        folders=folders, 
        photos=photos
    )

@app.route("/upload", methods=["POST"])
def upload():
    """Handle file uploads."""
    try:
        logger.info("Upload request received")
        
        if "file" not in request.files:
            logger.warning("No file part in request")
            return jsonify({"success": False, "error": "No file part"}), 400
            
        file = request.files["file"]
        folder_id = request.form.get("folder_id")
        
        logger.info(f"Upload request for folder: {folder_id}, file: {file.filename if file else 'None'}")
        
        if not file or file.filename == "":
            logger.warning("No file selected")
            return jsonify({"success": False, "error": "No file selected"}), 400
            
        if not allowed_file(file.filename):
            logger.warning(f"File type not allowed: {file.filename}")
            return jsonify({"success": False, "error": "File type not allowed"}), 400
            
        if not folder_id:
            logger.warning("No folder specified")
            return jsonify({"success": False, "error": "No folder specified"}), 400
        
        # Get the folder
        folder = PhotoFolder.query.filter_by(folder_key=folder_id).first()
        if not folder:
            logger.warning(f"Folder not found: {folder_id}")
            return jsonify({"success": False, "error": "Folder not found"}), 404
            
        # Check if QR code is active
        if not folder.qr_code_active:
            logger.warning(f"Attempt to upload to folder with deactivated QR code: {folder_id}")
            return jsonify({"success": False, "error": "This QR code has been deactivated and can no longer be used for uploads"}), 403
            
        # Check if the QR code has exceeded its time limit
        if folder.is_qr_code_expired():
            logger.warning(f"Attempt to upload to folder with expired QR code: {folder_id}")
            return jsonify({"success": False, "error": "This QR code has expired and can no longer be used for uploads"}), 403
        
        logger.info(f"Processing upload for folder {folder.folder_name} (ID: {folder.id}), is_local: {folder.is_local}")
        
        # Process the upload - respect the folder's storage setting
        if folder.is_local:
            logger.info("Using local storage for this upload")
            result = save_local_file(file, file.filename)
        else:
            logger.info("Using catbox.moe cloud storage for this upload")
            result = upload_to_catbox(file)
        
        if not result["success"]:
            logger.error(f"Upload failed: {result.get('error', 'Unknown error')}")
            return jsonify({"success": False, "error": result.get("error", "Upload failed")}), 500
        
        logger.info(f"File saved successfully: {result['file_url']}")
        
        # Determine if this is actually stored in the cloud or locally
        is_cloud = not folder.is_local and result.get('is_cloud', False)
        is_local = folder.is_local or result.get('is_fallback', False)
        
        logger.info(f"Storage status - Cloud: {is_cloud}, Local: {is_local}")
        
        # Get file size
        file_size = 0
        if hasattr(file, 'content_length') and file.content_length:
            file_size = file.content_length
        elif 'local_path' in result and os.path.exists(result['local_path']):
            file_size = os.path.getsize(result['local_path'])
        
        # Create a photo record
        photo = Photo(
            file_name=result["file_name"],
            original_name=result["original_name"],
            file_url=result["file_url"],
            file_size=file_size,
            mime_type=file.content_type,
            is_local=is_local,  # Set based on actual storage location
            user_id=folder.user_id,
            folder_id=folder.id
        )
        
        if "local_path" in result:
            photo.local_path = result["local_path"]
        
        if "delete_hash" in result:
            photo.delete_hash = result["delete_hash"]
        
        db.session.add(photo)
        db.session.commit()
        
        logger.info(f"Photo record created with ID: {photo.id}")
        
        return jsonify({
            "success": True,
            "message": "File uploaded successfully",
            "file_url": result["file_url"],
            "photo_id": photo.id
        })
    except Exception as e:
        logger.error(f"Unexpected error in upload: {str(e)}")
        return jsonify({"success": False, "error": f"Server error: {str(e)}"}), 500

@app.route("/check_auth")
def check_auth():
    """Check if the user is authenticated."""
    if current_user.is_authenticated:
        return jsonify({
            "authenticated": True,
            "user": {
                "id": current_user.id,
                "name": current_user.name,
                "email": current_user.email
            }
        })
    else:
        return jsonify({"authenticated": False})

@app.route("/photo/download/<int:photo_id>")
@login_required
def download_photo(photo_id):
    """Download a photo."""
    photo = Photo.query.get_or_404(photo_id)
    
    # Check permissions
    if photo.user_id != current_user.id and not current_user.is_admin:
        flash("You don't have permission to download this photo.", "danger")
        return redirect(url_for("index"))
    
    if photo.is_local and photo.local_path:
        # Serve local file
        return send_file(
            photo.local_path,
            as_attachment=True,
            download_name=photo.original_name
        )
    else:
        # Redirect to the external URL
        return redirect(photo.file_url)

@app.route("/photo/delete/<int:photo_id>")
@login_required
def delete_photo(photo_id):
    """Delete a photo."""
    photo = Photo.query.get_or_404(photo_id)
    
    # Check permissions
    if photo.user_id != current_user.id and not current_user.is_admin:
        if request.headers.get('Accept') == 'application/json':
            return jsonify({"success": False, "message": "You don't have permission to delete this photo."}), 403
        flash("You don't have permission to delete this photo.", "danger")
        return redirect(url_for("index"))
    
    # Get folder for redirecting after deletion
    folder = photo.folder
    
    # Delete local file if needed
    if photo.is_local and photo.local_path and os.path.exists(photo.local_path):
        try:
            os.remove(photo.local_path)
        except Exception as e:
            logger.error(f"Error deleting file: {str(e)}")
    
    # Delete from database
    db.session.delete(photo)
    db.session.commit()
    
    # Return JSON if requested
    if request.headers.get('Accept') == 'application/json':
        return jsonify({
            "success": True,
            "message": "Photo deleted successfully."
        })
    
    flash("Photo deleted successfully.", "success")
    return redirect(url_for("view_folder", folder_key=folder.folder_key))

@app.route("/photo/share/<int:photo_id>")
@login_required
def share_photo(photo_id):
    """Generate a shareable link for a photo."""
    photo = Photo.query.get_or_404(photo_id)
    
    # Check permissions
    if photo.user_id != current_user.id and not current_user.is_admin:
        if request.headers.get('Accept') == 'application/json':
            return jsonify({"success": False, "message": "You don't have permission to share this photo."}), 403
        flash("You don't have permission to share this photo.", "danger")
        return redirect(url_for("index"))
    
    # Generate share token (simple token with photo ID and timestamp)
    share_token = generate_share_token(photo_id)
    
    # Create the shareable URL
    share_url = url_for('view_shared_photo', share_token=share_token, _external=True)
    
    # Return JSON if requested
    if request.headers.get('Accept') == 'application/json':
        return jsonify({
            "success": True,
            "share_url": share_url
        })
    
    # Otherwise return the share page with the URL
    return render_template("share_photo.html", photo=photo, share_url=share_url)

@app.route("/shared/<share_token>")
def view_shared_photo(share_token):
    """View a shared photo using a share token."""
    try:
        # Decode the share token
        photo_id = decode_share_token(share_token)
        if not photo_id:
            flash("Invalid or expired share link.", "danger")
            return redirect(url_for("index"))
        
        # Get the photo
        photo = Photo.query.get_or_404(photo_id)
        
        # Render the shared photo view
        return render_template("shared_photo.html", photo=photo)
    except Exception as e:
        logger.error(f"Error viewing shared photo: {str(e)}")
        flash("The shared link is invalid or has expired.", "danger")
        return redirect(url_for("index"))

@app.route("/folder/deactivate_qr/<int:folder_id>")
@login_required
def deactivate_folder_qr(folder_id):
    """Deactivate the QR code for a folder."""
    folder = PhotoFolder.query.get_or_404(folder_id)
    
    # Check permissions
    if folder.user_id != current_user.id and not current_user.is_admin:
        if request.headers.get('Accept') == 'application/json':
            return jsonify({"success": False, "message": "You don't have permission to deactivate this QR code."}), 403
        flash("You don't have permission to deactivate this QR code.", "danger")
        return redirect(url_for("folders"))
    
    # Deactivate the QR code
    folder.deactivate_qr_code()
    
    # Return JSON if requested
    if request.headers.get('Accept') == 'application/json':
        return jsonify({
            "success": True,
            "message": "QR code deactivated successfully."
        })
    
    flash("QR code deactivated successfully. The folder is still accessible, but the QR code can no longer be used for uploads.", "success")
    return redirect(url_for("view_folder", folder_key=folder.folder_key))

@app.route("/folder/delete/<int:folder_id>")
@login_required
def delete_folder(folder_id):
    """Delete a folder and all its photos."""
    folder = PhotoFolder.query.get_or_404(folder_id)
    
    # Check permissions
    if folder.user_id != current_user.id and not current_user.is_admin:
        if request.headers.get('Accept') == 'application/json':
            return jsonify({"success": False, "message": "You don't have permission to delete this folder."}), 403
        flash("You don't have permission to delete this folder.", "danger")
        return redirect(url_for("folders"))
    
    # Delete all photos in the folder
    for photo in folder.photos:
        # Delete local file if needed
        if photo.is_local and photo.local_path and os.path.exists(photo.local_path):
            try:
                os.remove(photo.local_path)
            except Exception as e:
                logger.error(f"Error deleting file: {str(e)}")
    
    # Delete the folder (cascade will delete photos)
    db.session.delete(folder)
    db.session.commit()
    
    # Return JSON if requested
    if request.headers.get('Accept') == 'application/json':
        return jsonify({
            "success": True,
            "message": "Folder and all photos deleted successfully."
        })
    
    flash("Folder and all photos deleted successfully.", "success")
    return redirect(url_for("folders"))