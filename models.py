# models.py
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from database import get_db_connection # Import the database connection function

class User(UserMixin):
    """
    User model for Flask-Login.
    Represents a user in the 'users' table.
    """
    def __init__(self, id, username, password_hash, location_id, role):
        """
        Initializes a User object.
        :param id: User's unique ID from the database.
        :param username: User's username.
        :param password_hash: Hashed password.
        :param location_id: ID of the location the user is associated with (None for admin).
        :param role: User's role ('admin' or 'user').
        """
        self.id = id
        self.username = username
        self.password_hash = password_hash
        self.location_id = location_id
        self.role = role

    def get_id(self):
        """
        Required by Flask-Login to get the user's unique ID as a string.
        """
        return str(self.id)

    @staticmethod
    def get(user_id):
        """
        Static method to retrieve a user by their ID from the database.
        Used by Flask-Login's user_loader.
        """
        conn = get_db_connection()
        user_data = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        conn.close()
        if user_data:
            return User(user_data['id'], user_data['username'], user_data['password_hash'], user_data['location_id'], user_data['role'])
        return None

    @staticmethod
    def find_by_username(username):
        """
        Static method to retrieve a user by their username from the database.
        Used during login.
        """
        conn = get_db_connection()
        user_data = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()
        if user_data:
            return User(user_data['id'], user_data['username'], user_data['password_hash'], user_data['location_id'], user_data['role'])
        return None

    def check_password(self, password):
        """
        Checks if the provided password matches the stored hashed password.
        """
        return check_password_hash(self.password_hash, password)

    def is_admin(self):
        """
        Checks if the user has the 'admin' role.
        """
        return self.role == 'admin'

    def is_user(self):
        """
        Checks if the user has the 'user' role.
        """
        return self.role == 'user'
