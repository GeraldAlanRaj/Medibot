import sqlite3
import json
from datetime import datetime
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
    c.execute('''
        CREATE TABLE IF NOT EXISTS patient_info (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT,
            age INTEGER,
            email TEXT,
            phone TEXT,
            location TEXT,
            lat REAL,
            lon REAL,
            medical_history TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id)
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
    c.execute('SELECT id, name, specialty, rating, location, lat, lon, image_url FROM doctors WHERE user_id IS NOT NULL')
    rows = c.fetchall()
    conn.close()
    return [
        {
            'id': r[0], 'name': r[1], 'specialty': r[2], 'rating': r[3], 
            'location': r[4], 'lat': r[5], 'lon': r[6], 'image_url': r[7]
        }
        for r in rows
    ]

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

def book_appointment(session_id, doctor_id, time):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO appointments (session_id, doctor_id, appointment_time) VALUES (?, ?, ?)',
              (session_id, doctor_id, time))
    conn.commit()
    conn.close()

def get_doctor_profile(user_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('SELECT * FROM doctors WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def save_doctor_profile(user_id, data):
    name = data.get('name')
    specialty = data.get('specialty')
    location = data.get('location')
    lat, lon = data.get('lat'), data.get('lon')
    
    if location and (not lat or not lon):
        lat, lon = geocode_address(location)
        
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Check if doctor exists
    c.execute('SELECT id FROM doctors WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    
    if row:
        c.execute('''
            UPDATE doctors SET name=?, specialty=?, location=?, lat=?, lon=?
            WHERE user_id=?
        ''', (name, specialty, location, lat, lon, user_id))
    else:
        # Get default image if not provided
        image_url = data.get('image_url', 'https://images.unsplash.com/photo-1612349317150-e413f6a5b16d?auto=format&fit=crop&q=80&w=200&h=200')
        c.execute('''
            INSERT INTO doctors (user_id, name, specialty, rating, location, lat, lon, image_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, name, specialty, 4.5, location, lat, lon, image_url))
        
    conn.commit()
    conn.close()

def get_doctor_appointments(doctor_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    # Join with patient_info if possible, but appointments currently uses session_id
    # We'll need to join sessions to get user_id, then patient_info
    c.execute('''
        SELECT a.*, COALESCE(p.full_name, u.username) as patient_name, p.phone as patient_phone
        FROM appointments a
        JOIN sessions s ON a.session_id = s.session_id
        JOIN users u ON s.user_id = u.id
        LEFT JOIN patient_info p ON s.user_id = p.user_id
        WHERE a.doctor_id = ?
        ORDER BY a.appointment_time DESC
    ''', (doctor_id,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_appointment_status(appointment_id, status):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE appointments SET status = ? WHERE id = ?', (status, appointment_id))
    conn.commit()
    conn.close()


def get_session_analytics(session_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Count symptoms per session
    c.execute('SELECT extracted_symptoms FROM messages WHERE session_id = ? AND role = "user"', (session_id,))
    rows = c.fetchall()
    
    all_symptoms = []
    for row in rows:
        if row[0]:
            all_symptoms.extend(json.loads(row[0]))
            
    # Count messages
    c.execute('SELECT COUNT(*) FROM messages WHERE session_id = ?', (session_id,))
    message_count = c.fetchone()[0]
    
    conn.close()
    
    return {
        'symptom_count': len(set(all_symptoms)),
        'message_count': message_count,
        'unique_symptoms': list(set(all_symptoms))
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
    c.execute('SELECT id, username, password_hash, role FROM users WHERE username = ?', (username,))
    row = c.fetchone()
    conn.close()
    if row:
        return {'id': row[0], 'username': row[1], 'password_hash': row[2], 'role': row[3]}
    return None

def get_user_by_id(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id, username, password_hash, role FROM users WHERE id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {'id': row[0], 'username': row[1], 'password_hash': row[2], 'role': row[3]}
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
        INSERT OR REPLACE INTO patient_info (user_id, full_name, age, email, phone, location, lat, lon, medical_history)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, info['full_name'], info.get('age'), info['email'], info['phone'], 
          info.get('location'), lat, lon, info['medical_history']))
    conn.commit()
    conn.close()

def get_patient_info(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT full_name, age, email, phone, location, lat, lon, medical_history FROM patient_info WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            'full_name': row[0],
            'age': row[1],
            'email': row[2],
            'phone': row[3],
            'location': row[4],
            'lat': row[5],
            'lon': row[6],
            'medical_history': row[7]
        }
    return None

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

