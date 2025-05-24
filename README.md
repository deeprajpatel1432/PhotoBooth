# Photobooth Application

A Flask-based web application for managing photos with QR code integration, secure sharing, and flexible storage options.

## Key Features

- **User Authentication**: Register, login, and manage user profiles
- **Photo Management**: Upload, view, download, share, and delete photos
- **Folder Organization**: Create folders to organize photos with custom settings
- **QR Code Integration**: Generate QR codes for easy photo uploads from mobile devices
- **Dual Storage Options**: Store photos locally or in the cloud via catbox.moe
- **Advanced QR Code Expiration**: Set time limits for QR code access with expiration options
- **Secure Sharing**: Generate secure, time-limited sharing links for photos
- **Mobile-Friendly Interface**: Responsive design that works on all devices
- **Camera Integration**: Take photos directly from the browser

## System Architecture

### Backend
- **Flask**: Web framework for serving the application
- **SQLAlchemy**: ORM for database interactions
- **PostgreSQL**: Database for storing user data, photos, and folders
- **Flask-Login**: User authentication management
- **QRCode**: For generating QR codes

### Frontend
- **Bootstrap 5**: Responsive CSS framework
- **JavaScript**: Dynamic client-side functionality
- **Font Awesome**: Icon library

## Database Schema

### Users
- Basic user information (email, name, password hash)
- Authentication state and preferences
- Relationships to folders and photos

### Photo Folders
- Organization structure for photos
- QR code generation with configurable expiration
- Storage preference settings (local vs. cloud)

### Photos
- Photo metadata and storage locations
- Ownership and organization information
- Sharing capabilities

## Key Routes

- `/`: Home page
- `/login` & `/register`: User authentication
- `/profile`: User profile management
- `/folders`: View and manage folders
- `/generate`: Create new QR codes for photo uploads
- `/scan/<folder_key>`: QR code upload interface
- `/view_folder/<folder_key>`: View photos in a folder
- `/photo/share/<photo_id>`: Generate shareable links
- `/folder/deactivate_qr/<folder_id>`: Manually deactivate QR codes

## QR Code Expiration System

The application implements a dual-layer QR code expiration system:

1. **Session Expiration**: 60-second timeout for QR code scanning sessions with auto-refresh
2. **Permanent Expiration**: Configurable time-based expiration (in hours) after which a QR code becomes permanently invalid
3. **Manual Deactivation**: Option to manually deactivate QR codes while keeping the folder accessible

## Storage System

Photos can be stored using two methods:

1. **Local Storage**: Photos stored on the server's filesystem
2. **Cloud Storage**: Photos uploaded to catbox.moe with local fallback

## Running the Application

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export DATABASE_URL=postgresql://user:password@localhost/photobooth
export SESSION_SECRET=your-secret-key

# Run the application
python main.py
```

The application will be available at http://localhost:5000.

## Deployment

This application is configured for easy deployment on Replit or any other platform supporting Python/Flask applications. It includes a Procfile for Heroku deployment and configuration for PostgreSQL databases.