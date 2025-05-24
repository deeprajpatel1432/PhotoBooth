import os
import uuid
import requests
import logging
import base64
import time
from datetime import datetime
from werkzeug.utils import secure_filename
from app import app
import qrcode
from qrcode import constants
from io import BytesIO
from flask import current_app

# Configure logging
logger = logging.getLogger(__name__)

def allowed_file(filename):
    """Check if the file has an allowed extension."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def get_file_info(file):
    """Get file information."""
    return {
        'filename': secure_filename(file.filename),
        'size': file.content_length,
        'mime_type': file.content_type
    }

def save_local_file(file, filename):
    """Save file to local storage."""
    try:
        # Create a unique filename to avoid collisions
        unique_filename = f"{uuid.uuid4()}_{secure_filename(filename)}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        
        # Save the file
        file.save(file_path)
        
        # Return the relative URL (for serving through the app)
        relative_path = os.path.join('uploads', unique_filename)
        file_url = f"/static/{relative_path}"
        
        return {
            'success': True,
            'file_url': file_url,
            'local_path': file_path,
            'file_name': unique_filename,
            'original_name': filename
        }
    except Exception as e:
        logger.error(f"Error saving local file: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }

def upload_to_catbox(file):
    """Upload a file to catbox.moe."""
    try:
        logger.info(f"Attempting to upload file to catbox.moe: {file.filename}")
        
        # Create a unique filename for local storage
        unique_filename = f"{uuid.uuid4()}_{secure_filename(file.filename)}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        
        # Save the file locally first
        file.save(file_path)
        
        # Prepare the local fallback result in case the catbox upload fails
        local_fallback_result = {
            'success': True,
            'file_url': f"/static/uploads/{unique_filename}",
            'file_name': unique_filename,
            'original_name': file.filename,
            'local_path': file_path,
            'is_fallback': True
        }
        
        # Upload to catbox.moe
        try:
            url = 'https://catbox.moe/user/api.php'
            
            with open(file_path, 'rb') as f:
                files = {
                    'fileToUpload': (file.filename, f, file.content_type)
                }
                data = {
                    'reqtype': 'fileupload',
                    'userhash': ''  # Anonymous upload
                }
                
                logger.info("Sending request to catbox.moe API")
                response = requests.post(url, files=files, data=data, timeout=10)
                
                if response.status_code == 200 and response.text.startswith('https://'):
                    logger.info(f"Successfully uploaded to catbox.moe: {response.text}")
                    return {
                        'success': True,
                        'file_url': response.text,
                        'file_name': os.path.basename(response.text),
                        'original_name': file.filename,
                        'local_path': file_path,  # Keep the local path for fallback/deletion
                        'is_cloud': True
                    }
                else:
                    logger.error(f"Error from catbox.moe: {response.text}")
                    return local_fallback_result
        except Exception as e:
            logger.error(f"Error during catbox.moe upload: {str(e)}")
            return local_fallback_result
    except Exception as e:
        logger.error(f"Error in file upload process: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }

def generate_qr_url(data):
    """Generate QR code image from data."""
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Save the QR code
        filename = f"{uuid.uuid4()}.png"
        file_path = os.path.join(app.config['QR_CODE_FOLDER'], filename)
        img.save(file_path)
        
        # Return the URL to the QR code
        return f"/static/qr_codes/{filename}"
    except Exception as e:
        logger.error(f"Error generating QR code: {str(e)}")
        return None

def generate_share_token(photo_id):
    """Generate a token for sharing a photo.
    
    Simple implementation using base64 encoding with a timestamp to allow expiration.
    In a production system, you would want to use a more secure token system.
    """
    # Create a payload with photo ID and timestamp (24-hour validity)
    timestamp = int(time.time()) + (24 * 60 * 60)  # Current time + 24 hours
    payload = f"{photo_id}:{timestamp}"
    
    # Encode the payload using base64
    token = base64.urlsafe_b64encode(payload.encode()).decode()
    
    return token

def decode_share_token(token):
    """Decode a share token and return the photo ID if valid."""
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
            logger.warning(f"Share token expired: {token}")
            return None
        
        return photo_id
    except Exception as e:
        logger.error(f"Error decoding share token: {str(e)}")
        return None