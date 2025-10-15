# config.py
import os

class Config:
    """
    Configuration settings for the Flask application.
    """
    # Secret key for session management.
    # IMPORTANT: In a production environment, this should be a strong, randomly generated key
    # and ideally loaded from an environment variable (e.g., using os.environ.get).
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your_super_secret_key_change_this_in_production!'

    # Path to the SQLite database file.
    # os.path.abspath(os.path.dirname(__file__)) gets the directory of the current file (config.py).
    DATABASE_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'cold_room_monitor.db')

    # You can add other configurations here, e.g., API keys for external services if you extend the app.
    # For example, if you were to add email alerts:
    # MAIL_SERVER = 'smtp.example.com'
    # MAIL_PORT = 587
    # MAIL_USE_TLS = True
    # MAIL_USERNAME = os.environ.get('EMAIL_USERNAME')
    # MAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD')
