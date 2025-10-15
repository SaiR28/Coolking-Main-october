# app.py
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, g
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash
import json
import csv
from io import StringIO, BytesIO
import os
from datetime import datetime, timedelta
try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

# Import configuration and database functions
from config import Config
from database import init_db, get_db_connection, get_cold_room_by_sensor, insert_temperature_data, \
                     get_all_locations, add_location, get_location_by_id, update_location, delete_location, \
                     get_cold_rooms_by_location, add_cold_room, get_cold_room_by_id, update_cold_room, delete_cold_room, \
                     get_temperature_data_for_cold_room, get_24h_temperature_stats, \
                     get_sensors_by_cold_room, add_sensor, get_sensor_by_id, update_sensor, delete_sensor, \
                     get_all_users, add_user, update_user, delete_user, format_timestamp_indian, \
                     log_esp32_error, get_esp32_errors_for_cold_room, get_all_unresolved_errors, resolve_esp32_error
from models import User

app = Flask(__name__)
app.config.from_object(Config)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)

# --- Custom Decorators for Role-Based Access Control ---

def admin_required(f):
    @login_required
    def wrapper(*args, **kwargs):
        if not current_user.is_admin():
            flash('Admin access required.', 'danger')
            return redirect(url_for('user_dashboard'))
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

def location_user_required(f):
    @login_required
    def wrapper(*args, **kwargs):
        if current_user.is_admin():
            return f(*args, **kwargs)
        
        if not current_user.location_id:
            flash('You are not assigned to any location. Please contact an administrator.', 'warning')
            return redirect(url_for('user_dashboard'))

        cold_room_id = kwargs.get('cold_room_id')
        if cold_room_id:
            cold_room = get_cold_room_by_id(cold_room_id)
            if not cold_room or cold_room['location_id'] != current_user.location_id:
                flash('Access denied to this cold room data.', 'danger')
                return redirect(url_for('user_dashboard'))
        
        location_id = kwargs.get('location_id')
        if location_id and location_id != current_user.location_id:
            flash('Access denied to this location data.', 'danger')
            return redirect(url_for('user_dashboard'))

        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

# --- Before Request Hook ---
@app.before_request
def before_request():
    if not os.path.exists(app.config['DATABASE_PATH']):
        init_db()

# --- Routes ---

@app.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.is_admin():
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('user_dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.find_by_username(username)

        if user and user.check_password(password):
            login_user(user)
            flash('Logged in successfully!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

# --- ESP32 API Endpoint ---

@app.route('/api/data', methods=['POST'])
def receive_esp32_data():
    # API Key check bypassed for testing
    # api_key = request.headers.get('X-API-Key')
    # if api_key != 'Cool2814': # <<< CHANGE THIS KEY!
    #     return jsonify({"status": "error", "message": "Unauthorized API Key"}), 401

    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "Invalid JSON"}), 400

        esp32_mac = data.get('esp32_mac')
        readings = data.get('readings')

        if not esp32_mac or not readings:
            return jsonify({"status": "error", "message": "Missing esp32_mac or readings"}), 400

        processed_count = 0
        error_count = 0

        for reading in readings:
            sensor_id = reading.get('sensor_id')
            temperature = reading.get('temperature')

            if sensor_id and temperature is not None:
                cold_room = get_cold_room_by_sensor(sensor_id)
                if cold_room:
                    insert_temperature_data(cold_room['id'], temperature)
                    processed_count += 1
                else:
                    # Log ESP32 error for unregistered sensor
                    log_esp32_error(
                        esp32_mac,
                        sensor_id,
                        'UNREGISTERED_SENSOR',
                        f"Unregistered sensor_id '{sensor_id}' attempting to send data"
                    )
                    error_count += 1
                    print(f"Warning: Unregistered sensor_id '{sensor_id}' from ESP32 '{esp32_mac}'")
            else:
                # Log ESP32 error for malformed data
                log_esp32_error(
                    esp32_mac,
                    sensor_id or 'UNKNOWN',
                    'MALFORMED_DATA',
                    f"Malformed reading: sensor_id={sensor_id}, temperature={temperature}"
                )
                error_count += 1
                print(f"Warning: Malformed reading in payload: {reading}")

        response_message = f"Processed {processed_count} readings."
        if error_count > 0:
            response_message += f" {error_count} errors logged."

        return jsonify({"status": "success", "message": response_message}), 200

    except Exception as e:
        print(f"Error processing ESP32 data: {e}")
        return jsonify({"status": "error", "message": "Internal server error"}), 500

# --- Admin Dashboard Routes ---

@app.route('/admin')
@admin_required
def admin_dashboard():
    # Corrected path for admin_dashboard.html
    return render_template('admin/admin_dashboard.html')

@app.route('/admin/locations')
@admin_required
def manage_locations():
    locations = get_all_locations()
    return render_template('admin/locations.html', locations=locations)

@app.route('/admin/locations/add', methods=['GET', 'POST'])
@admin_required
def add_new_location():
    if request.method == 'POST':
        name = request.form['name']
        description = request.form.get('description', '')
        if add_location(name, description):
            flash('Location added successfully!', 'success')
            return redirect(url_for('manage_locations'))
        else:
            flash('Error: Location name already exists or invalid data.', 'danger')
    return render_template('admin/add_edit_location.html', title='Add New Location', location=None)

@app.route('/admin/locations/edit/<int:location_id>', methods=['GET', 'POST'])
@admin_required
def edit_location(location_id):
    location = get_location_by_id(location_id)
    if not location:
        flash('Location not found.', 'danger')
        return redirect(url_for('manage_locations'))

    if request.method == 'POST':
        name = request.form['name']
        description = request.form.get('description', '')
        if update_location(location_id, name, description):
            flash('Location updated successfully!', 'success')
            return redirect(url_for('manage_locations'))
        else:
            flash('Error: Location name already exists or invalid data.', 'danger')
    return render_template('admin/add_edit_location.html', title='Edit Location', location=location)

@app.route('/admin/locations/delete/<int:location_id>', methods=['POST'])
@admin_required
def delete_location_route(location_id):
    delete_location(location_id)
    flash('Location and all associated cold rooms, sensors, and data deleted.', 'success')
    return redirect(url_for('manage_locations'))

@app.route('/admin/locations/<int:location_id>/cold_rooms')
@admin_required
def manage_cold_rooms(location_id):
    location = get_location_by_id(location_id)
    if not location:
        flash('Location not found.', 'danger')
        return redirect(url_for('manage_locations'))
    cold_rooms = get_cold_rooms_by_location(location_id)
    return render_template('admin/cold_rooms.html', location=location, cold_rooms=cold_rooms)

@app.route('/admin/locations/<int:location_id>/cold_rooms/add', methods=['GET', 'POST'])
@admin_required
def add_new_cold_room(location_id):
    location = get_location_by_id(location_id)
    if not location:
        flash('Location not found.', 'danger')
        return redirect(url_for('manage_locations'))

    if request.method == 'POST':
        name = request.form['name']
        sensor_id = request.form.get('sensor_id', '').strip() or None

        if add_cold_room(name, location_id, sensor_id):
            flash('Cold Room added successfully!', 'success')
            return redirect(url_for('manage_cold_rooms', location_id=location_id))
        else:
            flash('Error: Cold Room name already exists or invalid data.', 'danger')
    
    return render_template('admin/add_edit_cold_room.html', 
                         title='Add New Cold Room',
                         location=location,
                         cold_room=None)

@app.route('/admin/cold_rooms/edit/<int:cold_room_id>', methods=['GET', 'POST'])
@admin_required
def edit_cold_room(cold_room_id):
    cold_room = get_cold_room_by_id(cold_room_id)
    if not cold_room:
        flash('Cold Room not found.', 'danger')
        return redirect(url_for('manage_locations'))

    location = get_location_by_id(cold_room['location_id'])

    if request.method == 'POST':
        name = request.form['name']
        sensor_id = request.form.get('sensor_id', '').strip() or None

        if update_cold_room(cold_room_id, name, sensor_id):
            flash('Cold Room updated successfully!', 'success')
            return redirect(url_for('manage_cold_rooms', location_id=location['id']))
        else:
            flash('Error: Cold Room name already exists or invalid data.', 'danger')
    
    return render_template('admin/add_edit_cold_room.html',
                         title='Edit Cold Room',
                         location=location,
                         cold_room=cold_room)

@app.route('/admin/cold_rooms/delete/<int:cold_room_id>', methods=['POST'])
@admin_required
def delete_cold_room_route(cold_room_id):
    cold_room = get_cold_room_by_id(cold_room_id)
    if not cold_room:
        flash('Cold Room not found.', 'danger')
        return redirect(url_for('admin_dashboard'))

    location_id = cold_room['location_id']
    delete_cold_room(cold_room_id)
    flash('Cold Room and all associated sensors and data deleted.', 'success')
    return redirect(url_for('manage_cold_rooms', location_id=location_id))

# --- Sensor Management Routes ---

@app.route('/admin/cold_rooms/<int:cold_room_id>/sensors')
@admin_required
def manage_sensors(cold_room_id):
    cold_room = get_cold_room_by_id(cold_room_id)
    if not cold_room:
        flash('Cold Room not found.', 'danger')
        return redirect(url_for('manage_locations'))

    location = get_location_by_id(cold_room['location_id'])
    sensors = get_sensors_by_cold_room(cold_room_id)
    return render_template('admin/sensors.html', cold_room=cold_room, location=location, sensors=sensors)

@app.route('/admin/cold_rooms/<int:cold_room_id>/sensors/add', methods=['GET', 'POST'])
@admin_required
def add_new_sensor(cold_room_id):
    cold_room = get_cold_room_by_id(cold_room_id)
    if not cold_room:
        flash('Cold Room not found.', 'danger')
        return redirect(url_for('manage_locations'))

    location = get_location_by_id(cold_room['location_id'])

    if request.method == 'POST':
        sensor_id = request.form['sensor_id']
        name = request.form['name']

        if add_sensor(cold_room_id, sensor_id, name, None):
            flash('Sensor added successfully!', 'success')
            return redirect(url_for('manage_sensors', cold_room_id=cold_room_id))
        else:
            flash('Error: Sensor ID already exists or invalid data.', 'danger')

    return render_template('admin/add_edit_sensor.html',
                         title='Add New Sensor',
                         cold_room=cold_room,
                         location=location,
                         sensor=None)

@app.route('/admin/sensors/edit/<int:sensor_id>', methods=['GET', 'POST'])
@admin_required
def edit_sensor(sensor_id):
    sensor = get_sensor_by_id(sensor_id)
    if not sensor:
        flash('Sensor not found.', 'danger')
        return redirect(url_for('manage_locations'))

    cold_room = get_cold_room_by_id(sensor['cold_room_id'])
    location = get_location_by_id(cold_room['location_id'])

    if request.method == 'POST':
        sensor_unique_id = request.form['sensor_id']
        name = request.form['name']

        if update_sensor(sensor_id, sensor['cold_room_id'], sensor_unique_id, name, None):
            flash('Sensor updated successfully!', 'success')
            return redirect(url_for('manage_sensors', cold_room_id=sensor['cold_room_id']))
        else:
            flash('Error: Sensor ID already exists or invalid data.', 'danger')

    return render_template('admin/add_edit_sensor.html',
                         title='Edit Sensor',
                         cold_room=cold_room,
                         location=location,
                         sensor=sensor)

@app.route('/admin/sensors/delete/<int:sensor_id>', methods=['POST'])
@admin_required
def delete_sensor_route(sensor_id):
    sensor = get_sensor_by_id(sensor_id)
    if not sensor:
        flash('Sensor not found.', 'danger')
        return redirect(url_for('manage_locations'))

    cold_room_id = sensor['cold_room_id']
    delete_sensor(sensor_id)
    flash('Sensor and all associated data deleted.', 'success')
    return redirect(url_for('manage_sensors', cold_room_id=cold_room_id))

@app.route('/admin/users')
@admin_required
def manage_users():
    users = get_all_users()
    return render_template('admin/users.html', users=users)

@app.route('/admin/users/add', methods=['GET', 'POST'])
@admin_required
def add_new_user():
    locations = get_all_locations()
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']
        location_id = request.form.get('location_id')
        
        if location_id and location_id != 'None':
            location_id = int(location_id)
        else:
            location_id = None

        if add_user(username, password, location_id, role):
            flash('User added successfully!', 'success')
            return redirect(url_for('manage_users'))
        else:
            flash('Error: Username already exists.', 'danger')
    return render_template('admin/add_edit_user.html', title='Add New User', user=None, locations=locations)

@app.route('/admin/users/edit/<int:user_id>', methods=['GET', 'POST'])
@admin_required
def edit_user(user_id):
    user_to_edit = User.get(user_id)
    if not user_to_edit:
        flash('User not found.', 'danger')
        return redirect(url_for('manage_users'))

    locations = get_all_locations()

    if request.method == 'POST':
        username = request.form['username']
        role = request.form['role']
        location_id = request.form.get('location_id')

        if location_id and location_id != 'None':
            location_id = int(location_id)
        else:
            location_id = None
        
        if user_id == current_user.id and not current_user.is_admin():
            flash('You cannot edit your own role or location.', 'warning')
            return redirect(url_for('manage_users'))

        if update_user(user_id, username, location_id, role):
            flash('User updated successfully!', 'success')
            return redirect(url_for('manage_users'))
        else:
            flash('Error: Username already exists.', 'danger')
    return render_template('admin/add_edit_user.html', title='Edit User', user=user_to_edit, locations=locations)

@app.route('/admin/users/delete/<int:user_id>', methods=['POST'])
@admin_required
def delete_user_route(user_id):
    if user_id == current_user.id:
        flash('You cannot delete your own account.', 'danger')
        return redirect(url_for('manage_users'))
    
    delete_user(user_id)
    flash('User deleted successfully!', 'success')
    return redirect(url_for('manage_users'))


# --- User Dashboard Routes ---

@app.route('/dashboard')
@login_required
def user_dashboard():
    # Show user-style dashboard for everyone, including admins
    # This gives admins a way to see the user experience

    if current_user.is_admin():
        # For admin users, show location-based view with selector
        locations = get_all_locations()

        # Check if a specific location is selected via query parameter
        selected_location_id = request.args.get('location_id', type=int)

        if selected_location_id:
            # Show specific location
            selected_location = get_location_by_id(selected_location_id)
            if selected_location:
                cold_rooms = get_cold_rooms_by_location(selected_location_id)
                room_data = []

                for room in cold_rooms:
                    room_dict = dict(room)
                    # Get latest temperature reading for this cold room
                    latest_data = get_temperature_data_for_cold_room(room['id'], limit=1)

                    if latest_data:
                        latest = latest_data[0]
                        room_dict['latest_temp'] = latest['temperature'] if latest['is_active'] else None
                        room_dict['latest_time'] = latest['timestamp']
                        room_dict['is_sensor_active'] = latest['is_active']
                        room_dict['minutes_ago'] = round(latest['seconds_ago'] / 60, 1) if latest['seconds_ago'] else 0
                    else:
                        room_dict['latest_temp'] = None
                        room_dict['latest_time'] = None
                        room_dict['is_sensor_active'] = False
                        room_dict['minutes_ago'] = None

                    # Get ESP32 errors for admin view
                    if current_user.is_admin():
                        room_dict['esp32_errors'] = get_esp32_errors_for_cold_room(room['id'], limit=3)

                    room_data.append(room_dict)

                return render_template('user/enhanced_dashboard.html',
                                     location=selected_location,
                                     cold_rooms=room_data,
                                     all_locations=locations,
                                     selected_location_id=selected_location_id,
                                     is_admin_view=True)

        # Default: Show all locations combined or first location if multiple exist
        if len(locations) > 1:
            # Multiple locations - show location selector with message
            return render_template('user/enhanced_dashboard.html',
                                 location=None,
                                 cold_rooms=[],
                                 all_locations=locations,
                                 selected_location_id=None,
                                 is_admin_view=True,
                                 show_location_selector=True)
        elif len(locations) == 1:
            # Single location - show it directly
            location = locations[0]
            cold_rooms = get_cold_rooms_by_location(location['id'])
            room_data = []

            for room in cold_rooms:
                room_dict = dict(room)
                # Get latest temperature reading for this cold room
                latest_data = get_temperature_data_for_cold_room(room['id'], limit=1)

                if latest_data:
                    latest = latest_data[0]
                    room_dict['latest_temp'] = latest['temperature'] if latest['is_active'] else None
                    room_dict['latest_time'] = latest['timestamp']
                    room_dict['is_sensor_active'] = latest['is_active']
                    room_dict['minutes_ago'] = round(latest['seconds_ago'] / 60, 1) if latest['seconds_ago'] else 0
                else:
                    room_dict['latest_temp'] = None
                    room_dict['latest_time'] = None
                    room_dict['is_sensor_active'] = False
                    room_dict['minutes_ago'] = None

                # Get ESP32 errors for admin view
                if current_user.is_admin():
                    room_dict['esp32_errors'] = get_esp32_errors_for_cold_room(room['id'], limit=3)

                room_data.append(room_dict)

            return render_template('user/enhanced_dashboard.html',
                                 location=location,
                                 cold_rooms=room_data,
                                 all_locations=locations,
                                 selected_location_id=location['id'],
                                 is_admin_view=True)
        else:
            # No locations
            return render_template('user/mobile_table_dashboard.html',
                                 location=None,
                                 cold_rooms=[],
                                 all_locations=[],
                                 is_admin_view=True)
    else:
        # For regular users, show only their assigned location
        if not current_user.location_id:
            flash('You are not assigned to any location. Please contact an administrator.', 'warning')
            return render_template('user/mobile_table_dashboard.html', location=None, cold_rooms=[])
        
        location = get_location_by_id(current_user.location_id)
        if not location:
            flash('Your assigned location was not found. Please contact an administrator.', 'warning')
            return render_template('user/mobile_table_dashboard.html', location=None, cold_rooms=[])
        
        cold_rooms = get_cold_rooms_by_location(location['id'])
        room_data = []

        # Combined stats for all rooms
        all_active_temps = []
        all_24h_temps = []
        most_recent_time = None
        most_recent_minutes_ago = None

        for room in cold_rooms:
            room_dict = dict(room)
            # Get latest temperature reading for this cold room
            latest_data = get_temperature_data_for_cold_room(room['id'], limit=1)

            if latest_data:
                latest = latest_data[0]
                room_dict['latest_temp'] = latest['temperature'] if latest['is_active'] else None
                room_dict['latest_time'] = latest['timestamp']
                room_dict['is_sensor_active'] = latest['is_active']
                room_dict['minutes_ago'] = round(latest['seconds_ago'] / 60, 1) if latest['seconds_ago'] else 0

                # Collect data for combined stats
                if latest['is_active'] and latest['temperature'] is not None:
                    all_active_temps.append(latest['temperature'])
                    if most_recent_time is None or (latest['seconds_ago'] or 0) < (most_recent_minutes_ago or float('inf')):
                        most_recent_time = latest['timestamp']
                        most_recent_minutes_ago = latest['seconds_ago']
            else:
                room_dict['latest_temp'] = None
                room_dict['latest_time'] = None
                room_dict['is_sensor_active'] = False
                room_dict['minutes_ago'] = None

            # Get 24-hour statistics
            stats_24h = get_24h_temperature_stats(room['id'])
            room_dict.update(stats_24h)

            # Collect 24h temperatures from active sensors
            if stats_24h.get('last_24h_data'):
                for temp_data in stats_24h['last_24h_data']:
                    all_24h_temps.append(temp_data['temp'])

            # Get ESP32 errors for admin view
            if current_user.is_admin():
                room_dict['esp32_errors'] = get_esp32_errors_for_cold_room(room['id'], limit=3)

            # Add status classification for template logic
            if room_dict['latest_temp'] is not None and room_dict['is_sensor_active']:
                temp = room_dict['latest_temp']
                if -5 <= temp <= 5:
                    room_dict['temp_status'] = 'normal'
                else:
                    room_dict['temp_status'] = 'alert'
            else:
                room_dict['temp_status'] = 'offline'

            room_data.append(room_dict)

        # Calculate combined location stats
        combined_stats = {
            'live_temp': round(sum(all_active_temps) / len(all_active_temps), 1) if all_active_temps else None,
            'avg_24h': round(sum(all_24h_temps) / len(all_24h_temps), 1) if all_24h_temps else None,
            'min_24h': round(min(all_24h_temps), 1) if all_24h_temps else None,
            'max_24h': round(max(all_24h_temps), 1) if all_24h_temps else None,
            'last_update': most_recent_time,
            'minutes_ago': round(most_recent_minutes_ago / 60, 1) if most_recent_minutes_ago else None,
            'online_count': sum(1 for room in room_data if room['is_sensor_active']),
            'total_count': len(room_data)
        }
        
        return render_template('user/mobile_table_dashboard.html',
                                     location=location,
                                     cold_rooms=room_data,
                                     combined_stats=combined_stats,
                                     all_locations=get_all_locations(),
                                     selected_location_id=current_user.location_id)

@app.route('/cold_room/<int:cold_room_id>/data')
@location_user_required
def view_cold_room_data(cold_room_id):
    cold_room = get_cold_room_by_id(cold_room_id)
    if not cold_room:
        flash('Cold Room not found.', 'danger')
        return redirect(url_for('user_dashboard'))

    location = get_location_by_id(cold_room['location_id'])

    # Note: Based on the current schema, sensors are embedded in cold_rooms
    # The cold_room itself contains the sensor_id, not separate sensor records
    sensors = []

    # Fetch temperature data for this cold room
    raw_data = get_temperature_data_for_cold_room(cold_room_id, limit=200)

    # Prepare data for Chart.js - filter out any None values
    timestamps = []
    temperatures = []

    for row in raw_data:
        if row['timestamp'] and row['temperature'] is not None:
            timestamps.append(row['timestamp'])
            temperatures.append(row['temperature'])

    # Create chart data structure expected by JavaScript (sensor-based structure)
    sensor_name = cold_room['name'] + (f" (Sensor: {cold_room['sensor_id']})" if cold_room['sensor_id'] else " (No Sensor)")
    chart_data = {
        sensor_name: {
            'timestamps': timestamps,
            'temperatures': temperatures
        }
    }

    return render_template('user/cold_room_data.html',
                         cold_room=cold_room,
                         location=location,
                         sensors=sensors,
                         chart_data=chart_data)

@app.route('/cold_room/<int:cold_room_id>/download_csv')
@location_user_required
def download_cold_room_csv(cold_room_id):
    cold_room = get_cold_room_by_id(cold_room_id)
    if not cold_room:
        flash('Cold Room not found.', 'danger')
        return redirect(url_for('user_dashboard'))

    data = get_temperature_data_for_cold_room(cold_room_id)

    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['Timestamp', 'Temperature'])

    for row in data:
        cw.writerow([
            row['timestamp'],
            row['temperature']
        ])

    output = si.getvalue()
    si.close()

    return send_file(
        StringIO(output),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'cold_room_{cold_room_id}_data.csv'
    )

@app.route('/cold_room/<int:cold_room_id>/export')
@location_user_required
def export_cold_room_data(cold_room_id):
    cold_room = get_cold_room_by_id(cold_room_id)
    if not cold_room:
        flash('Cold Room not found.', 'danger')
        return redirect(url_for('user_dashboard'))

    # Get query parameters
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    aggregation = request.args.get('aggregation', 'full')
    format_type = request.args.get('format', 'csv')

    try:
        # Get data with date filtering
        data = get_temperature_data_with_filters(cold_room_id, date_from, date_to, aggregation)

        if format_type == 'excel':
            return export_to_excel(data, cold_room, date_from, date_to, aggregation)
        else:
            return export_to_csv(data, cold_room, date_from, date_to, aggregation)

    except Exception as e:
        flash(f'Export failed: {str(e)}', 'danger')
        return redirect(url_for('user_dashboard'))

# Helper functions for data export
def get_temperature_data_with_filters(cold_room_id, date_from, date_to, aggregation):
    """Get temperature data with date filtering and aggregation options."""
    conn = get_db_connection()

    base_query = '''
        SELECT temperature, timestamp
        FROM temperature_data
        WHERE cold_room_id = ?
    '''
    params = [cold_room_id]

    if date_from:
        base_query += ' AND DATE(timestamp) >= ?'
        params.append(date_from)

    if date_to:
        base_query += ' AND DATE(timestamp) <= ?'
        params.append(date_to)

    if aggregation == 'full':
        query = base_query + ' ORDER BY timestamp DESC'
        data = conn.execute(query, params).fetchall()
        conn.close()
        return [{'timestamp': row['timestamp'], 'temperature': row['temperature']} for row in data]

    elif aggregation == 'hourly':
        query = base_query + '''
            GROUP BY DATE(timestamp), HOUR(timestamp)
            ORDER BY timestamp DESC
        '''
        # For SQLite, we need a different approach for hourly aggregation
        query = '''
            SELECT
                strftime('%Y-%m-%d %H:00:00', timestamp) as timestamp,
                AVG(temperature) as temperature,
                MIN(temperature) as min_temp,
                MAX(temperature) as max_temp,
                COUNT(*) as readings
            FROM temperature_data
            WHERE cold_room_id = ?
        '''
        if date_from:
            query += ' AND DATE(timestamp) >= ?'
        if date_to:
            query += ' AND DATE(timestamp) <= ?'

        query += '''
            GROUP BY strftime('%Y-%m-%d %H:00:00', timestamp)
            ORDER BY timestamp DESC
        '''

        data = conn.execute(query, params).fetchall()
        conn.close()
        return [dict(row) for row in data]

    elif aggregation == 'daily':
        query = '''
            SELECT
                DATE(timestamp) as timestamp,
                AVG(temperature) as temperature,
                MIN(temperature) as min_temp,
                MAX(temperature) as max_temp,
                COUNT(*) as readings
            FROM temperature_data
            WHERE cold_room_id = ?
        '''
        if date_from:
            query += ' AND DATE(timestamp) >= ?'
        if date_to:
            query += ' AND DATE(timestamp) <= ?'

        query += '''
            GROUP BY DATE(timestamp)
            ORDER BY timestamp DESC
        '''

        data = conn.execute(query, params).fetchall()
        conn.close()
        return [dict(row) for row in data]

def export_to_csv(data, cold_room, date_from, date_to, aggregation):
    """Export temperature data to CSV format."""
    si = StringIO()
    cw = csv.writer(si)

    # Write header based on aggregation type
    if aggregation == 'full':
        cw.writerow(['Timestamp', 'Temperature (°C)'])
        for row in data:
            cw.writerow([row['timestamp'], row['temperature']])
    else:
        cw.writerow(['Timestamp', 'Average Temperature (°C)', 'Min Temperature (°C)', 'Max Temperature (°C)', 'Number of Readings'])
        for row in data:
            cw.writerow([
                row['timestamp'],
                round(row['temperature'], 2),
                round(row['min_temp'], 2),
                round(row['max_temp'], 2),
                row['readings']
            ])

    output = si.getvalue()
    si.close()

    filename = f"{cold_room['name']}_{aggregation}_{date_from}_to_{date_to}.csv"

    return send_file(
        BytesIO(output.encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=filename
    )

def export_to_excel(data, cold_room, date_from, date_to, aggregation):
    """Export temperature data to Excel format (requires pandas)."""
    if not PANDAS_AVAILABLE:
        # Fallback to CSV if pandas is not available
        return export_to_csv(data, cold_room, date_from, date_to, aggregation)

    try:
        # Convert data to DataFrame
        df = pd.DataFrame(data)

        # Create Excel file in memory
        output = BytesIO()

        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Temperature Data', index=False)

            # Get the workbook and worksheet objects
            workbook = writer.book
            worksheet = writer.sheets['Temperature Data']

            # Add some formatting
            header_format = workbook.add_format({
                'bold': True,
                'text_wrap': True,
                'valign': 'top',
                'fg_color': '#D7E4BC',
                'border': 1
            })

            # Write the column headers with the defined format
            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, header_format)

        output.seek(0)

        filename = f"{cold_room['name']}_{aggregation}_{date_from}_to_{date_to}.xlsx"

        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        # Fallback to CSV if Excel export fails
        return export_to_csv(data, cold_room, date_from, date_to, aggregation)

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
