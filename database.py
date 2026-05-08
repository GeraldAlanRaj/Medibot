import sqlite3
import json
from datetime import datetime, timedelta
import os
import math
from geopy.geocoders import Nominatim # pyre-ignore[21]

DB_PATH = 'chat_memory.db'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password_hash TEXT,
            role TEXT,
            is_verified INTEGER DEFAULT 1,
            is_blocked INTEGER DEFAULT 0,
            created_at TIMESTAMP
        )
    ''')
    
    # Simple migration for existing DB
    try:
        c.execute('ALTER TABLE users ADD COLUMN is_verified INTEGER DEFAULT 1')
    except: pass
    try:
        c.execute('ALTER TABLE users ADD COLUMN is_blocked INTEGER DEFAULT 0')
    except: pass
    
    # New Location Columns Migration
    try:
        c.execute('ALTER TABLE doctors ADD COLUMN lat REAL')
        c.execute('ALTER TABLE doctors ADD COLUMN lon REAL')
    except: pass
    try:
        c.execute('ALTER TABLE doctors ADD COLUMN user_id INTEGER REFERENCES users(id)')
    except: pass
    try:
        c.execute('ALTER TABLE patient_info ADD COLUMN location TEXT')
        c.execute('ALTER TABLE patient_info ADD COLUMN lat REAL')
        c.execute('ALTER TABLE patient_info ADD COLUMN lon REAL')
    except: pass
    try:
        c.execute('ALTER TABLE patient_info ADD COLUMN gender TEXT')
    except: pass

    c.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            user_id INTEGER,
            created_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            role TEXT,
            content TEXT,
            timestamp TIMESTAMP,
            extracted_symptoms TEXT,
            FOREIGN KEY (session_id) REFERENCES sessions (session_id)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS doctors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            specialty TEXT,
            rating REAL,
            location TEXT,
            lat REAL,
            lon REAL,
            image_url TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS doctor_availability (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doctor_id INTEGER,
            day_of_week TEXT,
            start_time TEXT,
            end_time TEXT,
            FOREIGN KEY (doctor_id) REFERENCES doctors (id)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            doctor_id INTEGER,
            appointment_time TEXT,
            status TEXT DEFAULT 'pending',
            FOREIGN KEY (session_id) REFERENCES sessions (session_id),
            FOREIGN KEY (doctor_id) REFERENCES doctors (id)
        )
    ''')
    try:
        c.execute('ALTER TABLE appointments ADD COLUMN created_at TIMESTAMP')
    except: pass
    c.execute('''
        CREATE TABLE IF NOT EXISTS patient_info (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT,
            age INTEGER,
            gender TEXT,
            email TEXT,
            phone TEXT,
            location TEXT,
            lat REAL,
            lon REAL,
            medical_history TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            title TEXT,
            message TEXT,
            type TEXT,
            is_read INTEGER DEFAULT 0,
            metadata TEXT,
            created_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS doctor_certificates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            file_path TEXT,
            status TEXT DEFAULT 'pending',
            notes TEXT,
            reviewed_by INTEGER,
            uploaded_at TIMESTAMP,
            reviewed_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (reviewed_by) REFERENCES users (id)
        )
    ''')
    
    # Seed doctors if empty
    c.execute('SELECT COUNT(*) FROM doctors')
    if c.fetchone()[0] == 0:
        doctors = [
            ('Dr. Sarah Smith', 'Cardiologist', 4.9, 'New York, NY', 40.7128, -74.0060, 'https://images.unsplash.com/photo-1559839734-2b71f1e3c770?q=80&w=400&h=400&auto=format&fit=crop'),
            ('Dr. James Wilson', 'Dermatologist', 4.8, 'Los Angeles, CA', 34.0522, -118.2437, 'https://images.unsplash.com/photo-1612349317150-e413f6a5b16d?q=80&w=400&h=400&auto=format&fit=crop'),
            ('Dr. Emily Chen', 'Neurologist', 4.9, 'Chicago, IL', 41.8781, -87.6298, 'https://images.unsplash.com/photo-1594824476967-48c8b964273f?q=80&w=400&h=400&auto=format&fit=crop'),
            ('Dr. Michael Brown', 'Pediatrician', 4.7, 'Houston, TX', 29.7604, -95.3698, 'https://images.unsplash.com/photo-1622253692010-333f2da6031d?q=80&w=400&h=400&auto=format&fit=crop'),
            ('Dr. Lisa Gupta', 'General Physician', 4.6, 'San Francisco, CA', 37.7749, -122.4194, 'https://images.unsplash.com/photo-1544005313-94ddf0286df2?q=80&w=400&h=400&auto=format&fit=crop')
        ]
        c.executemany('INSERT INTO doctors (name, specialty, rating, location, lat, lon, image_url) VALUES (?, ?, ?, ?, ?, ?, ?)', doctors)
        
    c.execute('''
        CREATE TABLE IF NOT EXISTS translation_cache (
            lang TEXT,
            source_text TEXT,
            translated_text TEXT,
            PRIMARY KEY (lang, source_text)
        )
    ''')
    
    conn.commit()
    conn.close()

def geocode_address(address):
    try:
        geolocator = Nominatim(user_agent="medibot_ai")
        location = geolocator.geocode(address)
        if location:
            return location.latitude, location.longitude
    except Exception as e:
        print(f"Geocoding error: {e}")
    return None, None

def get_doctors():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        SELECT d.id, d.name, d.specialty, d.rating, d.location, d.lat, d.lon, d.image_url
        FROM doctors d
        JOIN users u ON d.user_id = u.id
        WHERE u.role = 'doctor' AND u.is_verified = 1 AND u.is_blocked = 0
    ''')
    rows = c.fetchall()
    conn.close()
    return [
        {
            'id': r[0], 'name': r[1], 'specialty': r[2], 'rating': r[3], 
            'location': r[4], 'lat': r[5], 'lon': r[6], 'image_url': r[7]
        }
        for r in rows
    ]


def is_doctor_verified(doctor_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        SELECT 1
        FROM doctors d
        JOIN users u ON d.user_id = u.id
        WHERE d.id = ? AND u.role = 'doctor' AND u.is_verified = 1 AND u.is_blocked = 0
    ''', (doctor_id,))
    row = c.fetchone()
    conn.close()
    return bool(row)

import math
def calculate_distance(lat1, lon1, lat2, lon2):
    if None in [lat1, lon1, lat2, lon2]: return None
    R = 6371 # Earth radius in km
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)
    a = math.sin(dLat/2) * math.sin(dLat/2) + \
        math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * \
        math.sin(dLon/2) * math.sin(dLon/2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def get_nearby_doctors(lat, lon, radius_km=50):
    all_doctors = get_doctors()
    nearby = []
    for doc in all_doctors:
        dist = calculate_distance(lat, lon, doc['lat'], doc['lon'])
        if dist is not None and dist <= radius_km:
            doc['distance'] = float(f"{dist:.2f}")
            nearby.append(doc)
    return sorted(nearby, key=lambda x: x['distance'])


def _parse_appointment_time(raw_time):
    if not raw_time:
        return None

    normalized = str(raw_time).strip().replace('Z', '')
    try:
        dt = datetime.fromisoformat(normalized)
        return dt.replace(second=0, microsecond=0)
    except ValueError:
        pass

    for fmt in ('%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M'):
        try:
            return datetime.strptime(normalized, fmt)
        except ValueError:
            continue
    return None

def book_appointment(session_id, doctor_id, time):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Only approved, active doctors can be booked.
    c.execute('''
        SELECT d.id
        FROM doctors d
        JOIN users u ON d.user_id = u.id
        WHERE d.id = ? AND u.role = 'doctor' AND u.is_verified = 1 AND u.is_blocked = 0
    ''', (doctor_id,))
    if not c.fetchone():
        conn.close()
        raise ValueError('Doctor is not available for booking.')

    appointment_dt = _parse_appointment_time(time)
    if not appointment_dt:
        conn.close()
        raise ValueError('Invalid appointment time format.')

    if appointment_dt < datetime.now().replace(second=0, microsecond=0):
        conn.close()
        raise ValueError('Cannot book an appointment in the past.')

    normalized_time = appointment_dt.strftime('%Y-%m-%dT%H:%M')

    # Enforce booking inside declared doctor availability windows.
    date_key = appointment_dt.strftime('%Y-%m-%d')
    free_day_slots = get_doctor_free_slots(doctor_id, start_date=date_key, days_ahead=1)
    allowed_slots = set()
    for row in free_day_slots:
        if row.get('date') == date_key:
            allowed_slots.update(row.get('slots') or [])
    if normalized_time not in allowed_slots:
        conn.close()
        raise ValueError('Selected slot is outside doctor availability or already booked.')

    # Enforce patient clash checks across all doctors/sessions.
    c.execute('SELECT user_id FROM sessions WHERE session_id = ?', (session_id,))
    session_row = c.fetchone()
    if not session_row or not session_row['user_id']:
        conn.close()
        raise ValueError('Invalid patient session. Please log in again.')

    patient_user_id = session_row['user_id']
    c.execute('''
        SELECT a.id
        FROM appointments a
        JOIN sessions s ON a.session_id = s.session_id
        WHERE s.user_id = ?
          AND a.appointment_time = ?
          AND a.status IN ('pending', 'accepted')
    ''', (patient_user_id, normalized_time))
    if c.fetchone():
        conn.close()
        raise ValueError('You already have another appointment at this time.')

    # Avoid duplicate booking by same patient-session.
    c.execute('''
        SELECT id FROM appointments
        WHERE session_id = ? AND doctor_id = ? AND appointment_time = ?
          AND status IN ('pending', 'accepted')
    ''', (session_id, doctor_id, normalized_time))
    if c.fetchone():
        conn.close()
        raise ValueError('You already have this appointment booked.')

    # Avoid double-booking a doctor slot.
    c.execute('''
        SELECT id FROM appointments
        WHERE doctor_id = ? AND appointment_time = ?
          AND status IN ('pending', 'accepted')
    ''', (doctor_id, normalized_time))
    if c.fetchone():
        conn.close()
        raise ValueError('This slot is no longer available. Please choose another slot.')

    c.execute('''
        INSERT INTO appointments (session_id, doctor_id, appointment_time, status, created_at)
        VALUES (?, ?, ?, 'pending', ?)
    ''', (session_id, doctor_id, normalized_time, datetime.now()))
    appointment_id = c.lastrowid
    conn.commit()
    conn.close()
    return appointment_id

def get_doctor_profile(user_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('SELECT * FROM doctors WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def get_doctor_user_id(doctor_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT user_id FROM doctors WHERE id = ?', (doctor_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None


def get_doctor_by_id(doctor_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('''
        SELECT d.id, d.user_id, d.name, d.specialty, d.location, d.lat, d.lon, d.image_url
        FROM doctors d
        WHERE d.id = ?
    ''', (doctor_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def save_doctor_profile(user_id, data):
    name = data.get('name')
    specialty = data.get('specialty')
    location = data.get('location')
    lat, lon = data.get('lat'), data.get('lon')
    image_url = data.get('image_url')

    try:
        lat = float(lat) if lat not in (None, '') else None
        lon = float(lon) if lon not in (None, '') else None
    except (TypeError, ValueError):
        lat, lon = None, None
    
    if location and (not lat or not lon):
        lat, lon = geocode_address(location)
        
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Check if doctor exists
    c.execute('SELECT id FROM doctors WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    
    if row:
        c.execute('''
            UPDATE doctors SET name=?, specialty=?, location=?, lat=?, lon=?, image_url=COALESCE(?, image_url)
            WHERE user_id=?
        ''', (name, specialty, location, lat, lon, image_url, user_id))
    else:
        # Get default image if not provided
        image_url = image_url or 'https://images.unsplash.com/photo-1612349317150-e413f6a5b16d?auto=format&fit=crop&q=80&w=200&h=200'
        c.execute('''
            INSERT INTO doctors (user_id, name, specialty, rating, location, lat, lon, image_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, name, specialty, 4.5, location, lat, lon, image_url))
        
    conn.commit()
    conn.close()

def get_doctor_appointments(doctor_id, date_filter=None):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    query = '''
        SELECT a.*,
               COALESCE(p.full_name, u.username) as patient_name,
               p.age as patient_age,
               p.gender as patient_gender,
               p.email as patient_email,
               p.phone as patient_phone,
               p.location as patient_location,
               p.medical_history as patient_medical_history
        FROM appointments a
        JOIN sessions s ON a.session_id = s.session_id
        JOIN users u ON s.user_id = u.id
        LEFT JOIN patient_info p ON s.user_id = p.user_id
        WHERE a.doctor_id = ?
    '''
    params = [doctor_id]
    if date_filter:
        query += ' AND a.appointment_time LIKE ?'
        params.append(f"{date_filter}%")
    query += ' ORDER BY a.appointment_time DESC'

    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_doctor_chats(doctor_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('''
        SELECT
            a.session_id,
            COALESCE(p.full_name, u.username) AS patient_name,
            COUNT(m.id) AS msg_count,
            COALESCE((
                SELECT m2.content
                FROM messages m2
                WHERE m2.session_id = a.session_id
                ORDER BY m2.timestamp DESC
                LIMIT 1
            ), '') AS last_msg,
            MAX(a.created_at) AS latest_booking
        FROM appointments a
        JOIN sessions s ON a.session_id = s.session_id
        JOIN users u ON s.user_id = u.id
        LEFT JOIN patient_info p ON s.user_id = p.user_id
        LEFT JOIN messages m ON m.session_id = a.session_id
        WHERE a.doctor_id = ?
        GROUP BY a.session_id, patient_name
        ORDER BY latest_booking DESC
    ''', (doctor_id,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def doctor_can_access_session(doctor_id, session_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        'SELECT 1 FROM appointments WHERE doctor_id = ? AND session_id = ? LIMIT 1',
        (doctor_id, session_id)
    )
    row = c.fetchone()
    conn.close()
    return bool(row)

def update_appointment_status(appointment_id, status):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE appointments SET status = ? WHERE id = ?', (status, appointment_id))
    conn.commit()
    conn.close()


def get_appointment_by_id(appointment_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('SELECT * FROM appointments WHERE id = ?', (appointment_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_id_by_session(session_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT user_id FROM sessions WHERE session_id = ?', (session_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None


def get_patient_appointments(user_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('''
        SELECT a.id, a.session_id, a.doctor_id, a.appointment_time, a.status,
               d.name AS doctor_name, d.specialty, d.location
        FROM appointments a
        JOIN sessions s ON a.session_id = s.session_id
        JOIN doctors d ON a.doctor_id = d.id
        WHERE s.user_id = ?
        ORDER BY a.appointment_time DESC
    ''', (user_id,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_doctor_availability(doctor_id, slots):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM doctor_availability WHERE doctor_id = ?', (doctor_id,))

    for slot in slots:
        day_of_week = slot.get('day_of_week')
        start_time = slot.get('start_time')
        end_time = slot.get('end_time')
        if not day_of_week or not start_time or not end_time:
            continue
        c.execute('''
            INSERT INTO doctor_availability (doctor_id, day_of_week, start_time, end_time)
            VALUES (?, ?, ?, ?)
        ''', (doctor_id, day_of_week, start_time, end_time))

    conn.commit()
    conn.close()


def get_doctor_availability(doctor_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('''
        SELECT day_of_week, start_time, end_time
        FROM doctor_availability
        WHERE doctor_id = ?
        ORDER BY day_of_week, start_time
    ''', (doctor_id,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _half_hour_slots_for_window(date_obj, start_time, end_time):
    slots = []
    try:
        start_dt = datetime.strptime(f"{date_obj.strftime('%Y-%m-%d')} {start_time}", '%Y-%m-%d %H:%M')
        end_dt = datetime.strptime(f"{date_obj.strftime('%Y-%m-%d')} {end_time}", '%Y-%m-%d %H:%M')
    except ValueError:
        return slots

    current = start_dt
    while current < end_dt:
        slots.append(current.strftime('%Y-%m-%dT%H:%M'))
        current += timedelta(minutes=30)
    return slots


def get_doctor_free_slots(doctor_id, start_date=None, days_ahead=7):
    availability = get_doctor_availability(doctor_id)
    if not availability:
        # Fallback schedule so newly approved doctors are still bookable before
        # they configure custom availability in their dashboard.
        availability = [
            {'day_of_week': day, 'start_time': '09:00', 'end_time': '17:00'}
            for day in ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')
        ]

    base_date = datetime.now().date() if not start_date else datetime.strptime(start_date, '%Y-%m-%d').date()
    now_floor = datetime.now().replace(second=0, microsecond=0)

    by_day = {}
    for row in availability:
        by_day.setdefault(row['day_of_week'].lower(), []).append(row)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    output = []

    for i in range(days_ahead):
        d = base_date + timedelta(days=i)
        weekday = d.strftime('%A').lower()
        windows = by_day.get(weekday, [])
        if not windows:
            continue

        all_slots = []
        for w in windows:
            all_slots.extend(_half_hour_slots_for_window(d, w['start_time'], w['end_time']))

        if not all_slots:
            continue

        c.execute('''
            SELECT appointment_time
            FROM appointments
            WHERE doctor_id = ?
              AND status IN ('pending', 'accepted')
              AND appointment_time LIKE ?
        ''', (doctor_id, f"{d.strftime('%Y-%m-%d')}%"))
        booked = {row[0][:16] for row in c.fetchall() if row[0]}

        free_slots = []
        for slot in sorted(set(all_slots)):
            if slot in booked:
                continue
            # Don't expose past slots in the picker.
            try:
                slot_dt = datetime.strptime(slot, '%Y-%m-%dT%H:%M')
            except ValueError:
                continue
            if slot_dt < now_floor:
                continue
            free_slots.append(slot)

        if free_slots:
            output.append({'date': d.strftime('%Y-%m-%d'), 'slots': free_slots})

    conn.close()
    return output


def get_session_analytics(session_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # Count symptoms per session
    c.execute('SELECT extracted_symptoms FROM messages WHERE session_id = ? AND role = "user"', (session_id,))
    rows = c.fetchall()
    
    all_symptoms = []
    for row in rows:
        if row[0]:
            try:
                all_symptoms.extend(json.loads(row[0]))
            except Exception:
                continue
            
    # Count messages
    c.execute('SELECT COUNT(*) FROM messages WHERE session_id = ?', (session_id,))
    message_count = c.fetchone()[0]

    c.execute('SELECT COUNT(*) FROM appointments WHERE session_id = ?', (session_id,))
    appointment_count = c.fetchone()[0]

    symptom_frequency = {}
    for symptom in all_symptoms:
        key = str(symptom).strip()
        if not key:
            continue
        symptom_frequency[key] = symptom_frequency.get(key, 0) + 1

    c.execute('''
        SELECT SUBSTR(timestamp, 1, 10) AS day_key, COUNT(*) AS total
        FROM messages
        WHERE session_id = ?
          AND SUBSTR(timestamp, 1, 10) >= DATE('now', '-6 day')
        GROUP BY day_key
        ORDER BY day_key ASC
    ''', (session_id,))
    daily_rows = c.fetchall()
    daily_map = {row['day_key']: row['total'] for row in daily_rows if row['day_key']}

    activity_labels = []
    activity_values = []
    for i in range(6, -1, -1):
        d = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
        activity_labels.append(d)
        activity_values.append(int(daily_map.get(d, 0)))

    symptom_signal = min(len(set(all_symptoms)) * 4, 24)
    message_signal = min(message_count * 3, 36)
    appointment_signal = min(appointment_count * 12, 24)
    health_index = max(0, min(100, 20 + symptom_signal + message_signal + appointment_signal))
    
    conn.close()
    
    return {
        'symptom_count': len(set(all_symptoms)),
        'message_count': message_count,
        'appointment_count': appointment_count,
        'unique_symptoms': list(set(all_symptoms)),
        'symptom_frequency': symptom_frequency,
        'activity_labels': activity_labels,
        'activity_values': activity_values,
        'health_index': health_index
    }

def create_user(username, password_hash, role):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute('INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)',
                  (username, password_hash, role, datetime.now()))
        user_id = c.lastrowid
        conn.commit()
        return user_id
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()

def get_user_by_username(username):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        SELECT id, username, password_hash, role, is_verified, is_blocked
        FROM users WHERE username = ?
    ''', (username,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            'id': row[0],
            'username': row[1],
            'password_hash': row[2],
            'role': row[3],
            'is_verified': bool(row[4]),
            'is_blocked': bool(row[5])
        }
    return None

def get_user_by_id(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        SELECT id, username, password_hash, role, is_verified, is_blocked
        FROM users WHERE id = ?
    ''', (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            'id': row[0],
            'username': row[1],
            'password_hash': row[2],
            'role': row[3],
            'is_verified': bool(row[4]),
            'is_blocked': bool(row[5])
        }
    return None

def create_session(session_id, user_id=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO sessions (session_id, user_id, created_at) VALUES (?, ?, ?)', 
              (session_id, user_id, datetime.now()))
    conn.commit()
    conn.close()

def save_patient_info(user_id, info):
    # Geocode if location is provided but lat/lon are not
    lat, lon = info.get('lat'), info.get('lon')
    if info.get('location') and (not lat or not lon):
        lat, lon = geocode_address(info['location'])

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO patient_info (
            user_id, full_name, age, gender, email, phone, location, lat, lon, medical_history
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        user_id,
        info.get('full_name'),
        info.get('age'),
        info.get('gender'),
        info.get('email'),
        info.get('phone'),
        info.get('location'),
        lat,
        lon,
        info.get('medical_history')
    ))
    conn.commit()
    conn.close()

def get_patient_info(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        SELECT full_name, age, gender, email, phone, location, lat, lon, medical_history
        FROM patient_info WHERE user_id = ?
    ''', (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            'full_name': row[0],
            'age': row[1],
            'gender': row[2],
            'email': row[3],
            'phone': row[4],
            'location': row[5],
            'lat': row[6],
            'lon': row[7],
            'medical_history': row[8]
        }
    return None


def create_notification(user_id, title, message, ntype='info', metadata=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    metadata_json = json.dumps(metadata) if metadata is not None else None
    c.execute('''
        INSERT INTO notifications (user_id, title, message, type, is_read, metadata, created_at)
        VALUES (?, ?, ?, ?, 0, ?, ?)
    ''', (user_id, title, message, ntype, metadata_json, datetime.now()))
    conn.commit()
    notification_id = c.lastrowid
    conn.close()
    return notification_id


def get_notifications(user_id, unread_only=False, limit=100):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    if unread_only:
        c.execute('''
            SELECT id, title, message, type, is_read, metadata, created_at
            FROM notifications
            WHERE user_id = ? AND is_read = 0
            ORDER BY created_at DESC
            LIMIT ?
        ''', (user_id, limit))
    else:
        c.execute('''
            SELECT id, title, message, type, is_read, metadata, created_at
            FROM notifications
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        ''', (user_id, limit))
    rows = c.fetchall()
    conn.close()

    notifications = []
    for row in rows:
        item = dict(row)
        try:
            item['metadata'] = json.loads(item['metadata']) if item.get('metadata') else None
        except Exception:
            item['metadata'] = None
        notifications.append(item)
    return notifications


def get_unread_notification_count(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0', (user_id,))
    count = c.fetchone()[0]
    conn.close()
    return count


def mark_notification_read(notification_id, user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE notifications SET is_read = 1 WHERE id = ? AND user_id = ?', (notification_id, user_id))
    conn.commit()
    conn.close()


def mark_all_notifications_read(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE notifications SET is_read = 1 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()


def save_doctor_certificate(user_id, file_path):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO doctor_certificates (user_id, file_path, status, uploaded_at)
        VALUES (?, ?, 'pending', ?)
    ''', (user_id, file_path, datetime.now()))
    conn.commit()
    cert_id = c.lastrowid
    conn.close()
    return cert_id


def get_latest_doctor_certificate(user_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('''
        SELECT * FROM doctor_certificates
        WHERE user_id = ?
        ORDER BY uploaded_at DESC
        LIMIT 1
    ''', (user_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def get_certificate_by_id(cert_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('SELECT * FROM doctor_certificates WHERE id = ?', (cert_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def list_pending_certificates():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('''
        SELECT dc.id, dc.user_id, dc.file_path, dc.status, dc.notes, dc.uploaded_at,
               u.username, d.name AS doctor_name, d.specialty
        FROM doctor_certificates dc
        JOIN users u ON dc.user_id = u.id
        LEFT JOIN doctors d ON d.user_id = u.id
        WHERE dc.status = 'pending'
        ORDER BY dc.uploaded_at DESC
    ''')
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def review_doctor_certificate(cert_id, status, reviewed_by, notes=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        UPDATE doctor_certificates
        SET status = ?, notes = ?, reviewed_by = ?, reviewed_at = ?
        WHERE id = ?
    ''', (status, notes, reviewed_by, datetime.now(), cert_id))

    # Keep user verification status in sync with certificate review.
    if status in ('approved', 'rejected'):
        c.execute('SELECT user_id FROM doctor_certificates WHERE id = ?', (cert_id,))
        row = c.fetchone()
        if row:
            verified = 1 if status == 'approved' else 0
            c.execute('UPDATE users SET is_verified = ? WHERE id = ?', (verified, row[0]))

    conn.commit()
    conn.close()

def clear_session_messages(session_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM messages WHERE session_id = ?', (session_id,))
    conn.commit()
    conn.close()

def add_message(session_id, role, content, extracted_symptoms=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    symptoms_json = json.dumps(extracted_symptoms) if extracted_symptoms else None
    c.execute('''
        INSERT INTO messages (session_id, role, content, timestamp, extracted_symptoms)
        VALUES (?, ?, ?, ?, ?)
    ''', (session_id, role, content, datetime.now(), symptoms_json))
    conn.commit()
    conn.close()

def get_session_history(session_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT role, content, extracted_symptoms FROM messages WHERE session_id = ? ORDER BY timestamp ASC', (session_id,))
    rows = c.fetchall()
    conn.close()
    
    history = []
    for row in rows:
        history.append({
            'role': row[0],
            'content': row[1],
            'extracted_symptoms': json.loads(row[2]) if row[2] else []
        })
    return history

def get_all_users():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id, username, role, is_verified, is_blocked, created_at FROM users')
    rows = c.fetchall()
    conn.close()
    return [{
        'id': r[0], 'username': r[1], 'role': r[2], 
        'is_verified': bool(r[3]), 'is_blocked': bool(r[4]),
        'created_at': r[5]
    } for r in rows]

def update_user_status(user_id, is_verified=None, is_blocked=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if is_verified is not None:
        c.execute('UPDATE users SET is_verified = ? WHERE id = ?', (int(is_verified), user_id))
    if is_blocked is not None:
        c.execute('UPDATE users SET is_blocked = ? WHERE id = ?', (int(is_blocked), user_id))
    conn.commit()
    conn.close()

def delete_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM users WHERE id = ?', (user_id,))
    c.execute('DELETE FROM patient_info WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def get_all_chats():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        SELECT s.session_id, u.username, u.role, COUNT(m.id) as msg_count
        FROM sessions s
        JOIN users u ON s.user_id = u.id
        LEFT JOIN messages m ON s.session_id = m.session_id
        GROUP BY s.session_id
        ORDER BY s.created_at DESC
    ''')
    rows = c.fetchall()
    conn.close()
    return [{
        'session_id': r[0], 'username': r[1], 'role': r[2], 'msg_count': r[3]
    } for r in rows]

def get_admin_stats():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    stats = {}
    c.execute('SELECT COUNT(*) FROM users')
    stats['total_users'] = c.fetchone()[0]
    
    c.execute('SELECT COUNT(*) FROM users WHERE role = "doctor" AND is_verified = 0')
    stats['pending_doctors'] = c.fetchone()[0]
    
    c.execute('SELECT COUNT(*) FROM messages')
    stats['total_messages'] = c.fetchone()[0]
    
    c.execute('SELECT COUNT(*) FROM sessions')
    stats['total_sessions'] = c.fetchone()[0]
    
    conn.close()
    return stats


def get_cached_translation(lang, source_text):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT translated_text FROM translation_cache WHERE lang = ? AND source_text = ?', (lang, source_text))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None


def cache_translation(lang, source_text, translated_text):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO translation_cache (lang, source_text, translated_text) VALUES (?, ?, ?)',
              (lang, source_text, translated_text))
    conn.commit()
    conn.close()

