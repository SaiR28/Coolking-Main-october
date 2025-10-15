# database.py
import sqlite3
import os
from werkzeug.security import generate_password_hash
from datetime import datetime # Import datetime for formatting

# Define the path to the SQLite database file.
DATABASE_FILE = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'cold_room_monitor.db')

def get_db_connection():
    """
    Establishes a connection to the SQLite database.
    Sets row_factory to sqlite3.Row to allow accessing columns by name.
    """
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """
    Initializes the database by creating tables if they don't exist.
    Also creates a default 'admin' user if no users exist.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    schema = """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        location_id INTEGER,
        role TEXT NOT NULL DEFAULT 'user'
    );

    CREATE TABLE IF NOT EXISTS locations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL
    );

    CREATE TABLE IF NOT EXISTS cold_rooms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        location_id INTEGER NOT NULL,
        sensor_id TEXT UNIQUE,
        esp32_mac_address TEXT,
        FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS temperature_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cold_room_id INTEGER NOT NULL,
        temperature REAL NOT NULL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (cold_room_id) REFERENCES cold_rooms(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS esp32_errors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        esp32_mac TEXT NOT NULL,
        sensor_id TEXT,
        error_type TEXT NOT NULL,
        error_message TEXT NOT NULL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        resolved BOOLEAN DEFAULT 0
    );
    """
    cursor.executescript(schema)
    conn.commit()

    cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
    if cursor.fetchone()[0] == 0:
        admin_username = 'admin'
        admin_password = 'Cool2814'
        hashed_password = generate_password_hash(admin_password)
        cursor.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (admin_username, hashed_password, 'admin')
        )
        conn.commit()
        print(f"Default admin user '{admin_username}' created with password '{admin_password}'. Please change it!")

    conn.close()

# --- Timestamp Formatting Helper ---
def format_timestamp_indian(timestamp_str):
    """
    Formats a timestamp string (e.g., 'YYYY-MM-DD HH:MM:SS') to Indian format.
    Returns 'N/A' if input is invalid or None.
    """
    if not timestamp_str:
        return 'N/A'
    try:
        dt_obj = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
        return dt_obj.strftime('%d-%m-%Y %H:%M:%S')
    except ValueError:
        try: # Try parsing without seconds if needed (some DBs omit :00)
            dt_obj = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M')
            return dt_obj.strftime('%d-%m-%Y %H:%M:%S')
        except ValueError:
            return timestamp_str # Return original if still fails, or 'Invalid Format'

# --- Database Helper Functions (with timestamp formatting where applicable) ---

def get_all_locations():
    conn = get_db_connection()
    locations = conn.execute('SELECT * FROM locations').fetchall()
    conn.close()
    return locations

def get_location_by_id(location_id):
    conn = get_db_connection()
    location = conn.execute('SELECT * FROM locations WHERE id = ?', (location_id,)).fetchone()
    conn.close()
    return location

def add_location(name, description=None):
    # Description parameter kept for compatibility but ignored
    conn = get_db_connection()
    try:
        cursor = conn.execute('INSERT INTO locations (name) VALUES (?)', (name,))
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()

def update_location(location_id, name, description=None):
    # Description parameter kept for compatibility but ignored
    conn = get_db_connection()
    try:
        conn.execute('UPDATE locations SET name = ? WHERE id = ?', (name, location_id))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def delete_location(location_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM locations WHERE id = ?', (location_id,))
    conn.commit()
    conn.close()

def get_cold_rooms_by_location(location_id):
    conn = get_db_connection()
    cold_rooms = conn.execute('SELECT * FROM cold_rooms WHERE location_id = ?', (location_id,)).fetchall()
    conn.close()
    return cold_rooms

def get_cold_room_by_id(cold_room_id):
    conn = get_db_connection()
    cold_room = conn.execute('SELECT * FROM cold_rooms WHERE id = ?', (cold_room_id,)).fetchone()
    conn.close()
    return cold_room

def add_cold_room(name, location_id, sensor_id=None):
    conn = get_db_connection()
    try:
        cursor = conn.execute(
            'INSERT INTO cold_rooms (name, location_id, sensor_id) VALUES (?, ?, ?)',
            (name, location_id, sensor_id)
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()

def update_cold_room(cold_room_id, name, sensor_id=None):
    conn = get_db_connection()
    try:
        conn.execute(
            'UPDATE cold_rooms SET name = ?, sensor_id = ? WHERE id = ?',
            (name, sensor_id, cold_room_id)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def delete_cold_room(cold_room_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM cold_rooms WHERE id = ?', (cold_room_id,))
    conn.commit()
    conn.close()

def get_sensors_by_cold_room(cold_room_id):
    conn = get_db_connection()
    sensors = conn.execute('SELECT * FROM sensors WHERE cold_room_id = ?', (cold_room_id,)).fetchall()
    conn.close()
    return sensors

def get_sensor_by_id(sensor_db_id):
    conn = get_db_connection()
    sensor = conn.execute('SELECT * FROM sensors WHERE id = ?', (sensor_db_id,)).fetchone()
    conn.close()
    return sensor

def get_sensor_by_unique_ids(sensor_unique_id, esp32_mac):
    """
    Fetches a sensor using its unique DS18B20 ID and the ESP32 MAC address.
    This is used by the API endpoint to map incoming data.
    """
    conn = get_db_connection()
    sensor = conn.execute(
        'SELECT * FROM sensors WHERE sensor_id = ? AND esp32_mac_address = ?',
        (sensor_unique_id, esp32_mac)
    ).fetchone()
    conn.close()
    return sensor

def add_sensor(cold_room_id, sensor_id, name, esp32_mac_address):
    """Adds a new sensor."""
    conn = get_db_connection()
    try:
        cursor = conn.execute(
            'INSERT INTO sensors (cold_room_id, sensor_id, name, esp32_mac_address) VALUES (?, ?, ?, ?)',
            (cold_room_id, sensor_id, name, esp32_mac_address)
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        return None # sensor_id (DS18B20 address) must be unique
    finally:
        conn.close()

def update_sensor(sensor_db_id, cold_room_id, sensor_id, name, esp32_mac_address):
    """Updates an existing sensor."""
    conn = get_db_connection()
    try:
        conn.execute(
            'UPDATE sensors SET cold_room_id = ?, sensor_id = ?, name = ?, esp32_mac_address = ? WHERE id = ?',
            (cold_room_id, sensor_id, name, esp32_mac_address, sensor_db_id)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False # sensor_id (DS18B20 address) must be unique
    finally:
        conn.close()

def delete_sensor(sensor_db_id):
    """Deletes a sensor and its associated temperature data."""
    conn = get_db_connection()
    conn.execute('DELETE FROM sensors WHERE id = ?', (sensor_db_id,))
    conn.commit()
    conn.close()

def insert_temperature_data(cold_room_id, temperature):
    """
    Inserts a new temperature reading for a cold room.
    """
    conn = get_db_connection()
    try:
        cursor = conn.execute(
            'INSERT INTO temperature_data (cold_room_id, temperature) VALUES (?, ?)',
            (cold_room_id, temperature)
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()

def get_temperature_data_for_sensor(sensor_unique_id, limit=None):
    """Fetches temperature data for a specific sensor."""
    conn = get_db_connection()
    query = 'SELECT * FROM temperature_data WHERE sensor_id = ? ORDER BY timestamp DESC'
    params = [sensor_unique_id]
    if limit:
        query += ' LIMIT ?'
        params.append(limit)
    data = conn.execute(query, params).fetchall()
    conn.close()
    # Format timestamps for display
    formatted_data = []
    for row in data:
        row_dict = dict(row)
        row_dict['timestamp_formatted'] = format_timestamp_indian(row['timestamp'])
        formatted_data.append(row_dict)
    return formatted_data

def get_temperature_data_for_cold_room(cold_room_id, limit=None):
    """
    Retrieves temperature data for a specific cold room.
    Optionally limits the number of records returned.
    Returns data sorted by timestamp in descending order (newest first).
    """
    conn = get_db_connection()
    query = '''
        SELECT temperature, timestamp,
               (julianday('now') - julianday(timestamp)) * 86400 as seconds_ago
        FROM temperature_data
        WHERE cold_room_id = ?
        ORDER BY timestamp DESC
    '''
    if limit:
        query += ' LIMIT ?'
        data = conn.execute(query, (cold_room_id, limit)).fetchall()
    else:
        data = conn.execute(query, (cold_room_id,)).fetchall()
    conn.close()

    result = []
    for row in data:
        is_active = row['seconds_ago'] is None or row['seconds_ago'] <= 900  # 15 minutes = 900 seconds
        result.append({
            'temperature': row['temperature'],
            'timestamp': format_timestamp_indian(row['timestamp']),
            'seconds_ago': row['seconds_ago'],
            'is_active': is_active
        })

    return result

def get_24h_temperature_stats(cold_room_id):
    """
    Gets 24-hour temperature statistics for a cold room.
    Returns average, min, max temperatures and trend indicator.
    """
    conn = get_db_connection()

    # Get last 24 hours of data
    query = '''
        SELECT temperature, timestamp
        FROM temperature_data
        WHERE cold_room_id = ?
        AND datetime(timestamp) >= datetime('now', '-24 hours')
        ORDER BY timestamp DESC
    '''

    data = conn.execute(query, (cold_room_id,)).fetchall()
    conn.close()

    if not data:
        return {
            'avg_temp': None,
            'min_temp': None,
            'max_temp': None,
            'readings_count': 0,
            'trend': 'stable',
            'last_24h_data': []
        }

    temperatures = [row['temperature'] for row in data]

    # Calculate statistics
    avg_temp = sum(temperatures) / len(temperatures)
    min_temp = min(temperatures)
    max_temp = max(temperatures)

    # Calculate trend (compare first and last readings)
    trend = 'stable'
    if len(temperatures) >= 2:
        recent_avg = sum(temperatures[:5]) / min(5, len(temperatures))  # Last 5 readings
        older_avg = sum(temperatures[-5:]) / min(5, len(temperatures))   # First 5 readings

        if recent_avg > older_avg + 0.5:
            trend = 'rising'
        elif recent_avg < older_avg - 0.5:
            trend = 'falling'

    return {
        'avg_temp': round(avg_temp, 1),
        'min_temp': round(min_temp, 1),
        'max_temp': round(max_temp, 1),
        'readings_count': len(temperatures),
        'trend': trend,
        'last_24h_data': [{'temp': t, 'time': format_timestamp_indian(data[i]['timestamp'])}
                          for i, t in enumerate(temperatures[:48])]  # Last 48 readings for mini chart
    }

def get_all_users():
    """Fetches all users."""
    conn = get_db_connection()
    users = conn.execute('SELECT u.*, l.name AS location_name FROM users u LEFT JOIN locations l ON u.location_id = l.id').fetchall()
    conn.close()
    return users

def add_user(username, password, location_id, role):
    """Adds a new user."""
    conn = get_db_connection()
    try:
        hashed_password = generate_password_hash(password)
        cursor = conn.execute(
            'INSERT INTO users (username, password_hash, location_id, role) VALUES (?, ?, ?, ?)',
            (username, hashed_password, location_id, role)
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()

def update_user(user_id, username, location_id, role):
    """Updates an existing user (excluding password)."""
    conn = get_db_connection()
    try:
        conn.execute(
            'UPDATE users SET username = ?, location_id = ?, role = ? WHERE id = ?',
            (username, location_id, role, user_id)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def delete_user(user_id):
    """Deletes a user."""
    conn = get_db_connection()
    conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()

def get_cold_room_by_sensor(sensor_id):
    """
    Fetches a cold room using its sensor ID.
    This is used by the API endpoint to map incoming data.
    """
    conn = get_db_connection()
    cold_room = conn.execute(
        'SELECT * FROM cold_rooms WHERE sensor_id = ?',
        (sensor_id,)
    ).fetchone()
    conn.close()
    return cold_room

# --- ESP32 Error Logging Functions ---

def log_esp32_error(esp32_mac, sensor_id, error_type, error_message):
    """
    Logs an ESP32 communication error.
    """
    conn = get_db_connection()
    try:
        cursor = conn.execute(
            'INSERT INTO esp32_errors (esp32_mac, sensor_id, error_type, error_message) VALUES (?, ?, ?, ?)',
            (esp32_mac, sensor_id, error_type, error_message)
        )
        conn.commit()
        return cursor.lastrowid
    except Exception as e:
        print(f"Error logging ESP32 error: {e}")
        return None
    finally:
        conn.close()

def get_esp32_errors_for_cold_room(cold_room_id, limit=10):
    """
    Gets recent ESP32 errors for a specific cold room.
    """
    conn = get_db_connection()
    # Get sensor_id for this cold room
    cold_room = conn.execute('SELECT sensor_id FROM cold_rooms WHERE id = ?', (cold_room_id,)).fetchone()

    if not cold_room or not cold_room['sensor_id']:
        conn.close()
        return []

    query = '''
        SELECT * FROM esp32_errors
        WHERE sensor_id = ? AND resolved = 0
        ORDER BY timestamp DESC
        LIMIT ?
    '''

    errors = conn.execute(query, (cold_room['sensor_id'], limit)).fetchall()
    conn.close()

    return [{
        'id': row['id'],
        'esp32_mac': row['esp32_mac'],
        'error_type': row['error_type'],
        'error_message': row['error_message'],
        'timestamp': format_timestamp_indian(row['timestamp']),
        'resolved': bool(row['resolved'])
    } for row in errors]

def get_all_unresolved_errors():
    """
    Gets all unresolved ESP32 errors for admin overview.
    """
    conn = get_db_connection()
    query = '''
        SELECT e.*, c.name as cold_room_name, l.name as location_name
        FROM esp32_errors e
        LEFT JOIN cold_rooms c ON e.sensor_id = c.sensor_id
        LEFT JOIN locations l ON c.location_id = l.id
        WHERE e.resolved = 0
        ORDER BY e.timestamp DESC
    '''

    errors = conn.execute(query).fetchall()
    conn.close()

    return [{
        'id': row['id'],
        'esp32_mac': row['esp32_mac'],
        'sensor_id': row['sensor_id'],
        'cold_room_name': row['cold_room_name'] or 'Unknown Room',
        'location_name': row['location_name'] or 'Unknown Location',
        'error_type': row['error_type'],
        'error_message': row['error_message'],
        'timestamp': format_timestamp_indian(row['timestamp'])
    } for row in errors]

def resolve_esp32_error(error_id):
    """
    Marks an ESP32 error as resolved.
    """
    conn = get_db_connection()
    try:
        conn.execute('UPDATE esp32_errors SET resolved = 1 WHERE id = ?', (error_id,))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error resolving ESP32 error: {e}")
        return False
    finally:
        conn.close()
