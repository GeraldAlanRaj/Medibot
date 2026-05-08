import requests # pyre-ignore[21]
import os
import uuid
from datetime import datetime
from flask import Flask, request, jsonify, render_template, session, send_file # pyre-ignore[21]
from flask_cors import CORS # pyre-ignore[21]
from werkzeug.security import generate_password_hash, check_password_hash # pyre-ignore[21]
from werkzeug.utils import secure_filename # pyre-ignore[21]
from functools import wraps
from database import ( # pyre-ignore[21]
    init_db, create_session, add_message, get_session_history,
    get_doctors, book_appointment, save_patient_info, get_session_analytics,
    create_user, get_user_by_username, get_user_by_id, get_patient_info,
    clear_session_messages, get_all_users, update_user_status, delete_user, 
    get_all_chats, get_admin_stats, get_nearby_doctors, geocode_address,
    get_doctor_profile, save_doctor_profile, get_doctor_appointments, update_appointment_status,
    get_patient_appointments, save_doctor_availability, get_doctor_availability,
    get_doctor_free_slots, create_notification, get_notifications, mark_notification_read,
    mark_all_notifications_read, get_unread_notification_count, get_user_id_by_session,
    get_appointment_by_id, save_doctor_certificate, get_latest_doctor_certificate,
    list_pending_certificates, review_doctor_certificate, get_doctor_user_id,
    get_certificate_by_id, get_doctor_chats, doctor_can_access_session,
    get_doctor_by_id,
    is_doctor_verified
)
from dotenv import load_dotenv
load_dotenv()
import os
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
from agent import handle_user_input # pyre-ignore[21]

template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'templates'))
static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'static'))

app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
app.secret_key = os.urandom(24)
CORS(app)

CERT_UPLOAD_DIR = os.path.join(os.path.dirname(__file__), 'data', 'certificates')
os.makedirs(CERT_UPLOAD_DIR, exist_ok=True)
ALLOWED_CERT_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}
PROFILE_IMG_UPLOAD_DIR = os.path.join(static_dir, 'uploads', 'doctor_profiles')
os.makedirs(PROFILE_IMG_UPLOAD_DIR, exist_ok=True)
ALLOWED_PROFILE_IMG_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
NYC_LAT = 40.7128
NYC_LNG = -74.0060
NY_BOUNDS = {
    'min_lat': 40.30,
    'max_lat': 41.20,
    'min_lng': -74.40,
    'max_lng': -73.40,
}

# Helper for role-based access
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('role') != 'admin':
            return jsonify({"error": "Admin access required"}), 403
        return f(*args, **kwargs)
    return decorated_function


def _allowed_cert_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_CERT_EXTENSIONS


def _allowed_profile_image_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_PROFILE_IMG_EXTENSIONS


def _doctor_is_verified(user_id):
    user = get_user_by_id(user_id)
    return bool(user and user.get('role') == 'doctor' and user.get('is_verified'))


def _is_new_york_coordinate(lat, lng):
    if lat is None or lng is None:
        return False
    return (
        NY_BOUNDS['min_lat'] <= float(lat) <= NY_BOUNDS['max_lat']
        and NY_BOUNDS['min_lng'] <= float(lng) <= NY_BOUNDS['max_lng']
    )


def _normalize_new_york_coordinates(lat, lng):
    if lat is None or lng is None:
        return NYC_LAT, NYC_LNG
    return float(lat), float(lng)

# Initialize database
init_db()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/signup', methods=['POST'])
def signup():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    role = (data.get('role') or 'patient').strip().lower()  # default to patient

    if role == 'admin':
        return jsonify({"success": False, "error": "Admin signup is disabled."}), 403

    if role not in {'patient', 'doctor'}:
        return jsonify({"success": False, "error": "Invalid role selected."}), 400
    
    if not username or not password:
        return jsonify({"success": False, "error": "Username and password required"}), 400
        
    if get_user_by_username(username):
        return jsonify({"success": False, "error": "Username already exists"}), 400
        
    password_hash = generate_password_hash(password)
    
    # Default verification: Doctors need approval (0), others approved (1)
    is_verified = 0 if role == 'doctor' else 1
    
    user_id = create_user(username, password_hash, role)
    
    if user_id:
        # Update initial verification if role-based
        if role == 'doctor':
             update_user_status(user_id, is_verified=0)
             # Save additional doctor info immediately
             doc_data = {
                 'name': data.get('name', username),
                 'specialty': data.get('specialty', 'General Physician'),
                 'location': data.get('location', 'Not specified')
             }
             save_doctor_profile(user_id, doc_data)

             return jsonify({
                 "success": True,
                 "pending_verification": True,
                 "message": "Doctor account created. Upload certificate and wait for admin approval before login.",
                 "user": {"id": user_id, "username": username, "role": role}
             })

        session['user_id'] = user_id
        session['username'] = username
        session['role'] = role
        return jsonify({"success": True, "user": {"id": user_id, "username": username, "role": role}})
    return jsonify({"success": False, "error": "Failed to create user"}), 500

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    user = get_user_by_username(username)
    if user and check_password_hash(user['password_hash'], password):
        if user.get('is_blocked'):
            return jsonify({"success": False, "error": "Account is blocked. Please contact admin."}), 403
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['role'] = user['role']
        pending_verification = user.get('role') == 'doctor' and not user.get('is_verified')
        return jsonify({
            "success": True, 
            "pending_verification": pending_verification,
            "user": {
                "id": user['id'],
                "username": user['username'],
                "role": user['role']
            }
        })
    return jsonify({"success": False, "error": "Invalid username or password"}), 401

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({"success": True})

@app.route('/api/me', methods=['GET'])
def get_me():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"authenticated": False})
    
    user = get_user_by_id(user_id)
    if not user:
        return jsonify({"authenticated": False})
        
    profile = None
    doctor_info = None
    certificate = None
    if user['role'] == 'patient':
        profile = get_patient_info(user_id)
    elif user['role'] == 'doctor':
        doctor_info = get_doctor_profile(user_id)
        certificate = get_latest_doctor_certificate(user_id)
        
    return jsonify({
        "authenticated": True, 
        "user": user, 
        "profile": profile,
        "doctor_info": doctor_info,
        "certificate": certificate,
        "unread_notifications": get_unread_notification_count(user_id)
    })

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.json
    session_id = data.get('session_id')
    user_message = data.get('message')
    language = data.get('language', 'en')
    
    if not session_id:
        session_id = str(uuid.uuid4())
        user_id = session.get('user_id')
        create_session(session_id, user_id)
        
    if not user_message:
        return jsonify({"error": "Message is required"}), 400
        
    # Process through Agent
    response_data = handle_user_input(session_id, user_message, language=language)

    # Log user message with extracted symptoms
    new_symptoms = response_data.get('new_symptoms', [])
    add_message(session_id, 'user', user_message, new_symptoms)
    
    # Log agent response
    add_message(session_id, 'agent', response_data['reply'])
    
    return jsonify(response_data)

@app.route('/api/doctors', methods=['GET'])
def get_all_doctors():
    doctors = get_doctors()
    return jsonify(doctors)

@app.route('/api/book_appointment', methods=['POST'])
def handle_book_appointment():
    data = request.json
    session_id = data.get('session_id')
    doctor_id = data.get('doctor_id')
    time = data.get('time')
    
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"success": False, "error": "Login required to book appointments"}), 401

    # Ensure session exists
    if not session_id or session_id == "null":
        session_id = str(uuid.uuid4())
        create_session(session_id, user_id)
    else:
        # If the browser sends an older anonymous or foreign session id,
        # create a fresh user-bound session so booking can proceed.
        owner_id = get_user_id_by_session(session_id)
        if owner_id != user_id:
            session_id = str(uuid.uuid4())
            create_session(session_id, user_id)
        
    if not all([doctor_id, time]):
        return jsonify({"success": False, "error": "Doctor and time slot required"}), 400
        
    try:
        appointment_id = book_appointment(session_id, doctor_id, time)
        doctor_info = get_doctor_by_id(doctor_id)
        doctor_name = doctor_info.get('name') if doctor_info else 'doctor'

        # Notify patient
        create_notification(
            user_id,
            'Appointment Requested',
            f'Your appointment request with {doctor_name} for {time} was submitted and is awaiting doctor confirmation.',
            'appointment',
            {'appointment_id': appointment_id, 'doctor_id': doctor_id, 'doctor_name': doctor_name, 'time': time, 'status': 'pending'}
        )

        # Notify doctor
        doctor_user_id = get_doctor_user_id(doctor_id)
        if doctor_user_id:
            create_notification(
                doctor_user_id,
                'New Appointment Request',
                f'New appointment request scheduled for {time}.',
                'appointment',
                {'appointment_id': appointment_id, 'doctor_id': doctor_id, 'doctor_name': doctor_name, 'time': time, 'status': 'pending'}
            )

        return jsonify({
            "success": True, 
            "message": "Appointment booked successfully",
            "session_id": session_id,
            "appointment_id": appointment_id
        })
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 409
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/save_profile', methods=['POST'])
def handle_save_profile():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"success": False, "error": "Not authenticated"}), 401
        
    data = request.json
    profile_data = data.get('profile')
    
    if not profile_data:
        return jsonify({"success": False, "error": "Missing profile data"}), 400
        
    save_patient_info(user_id, profile_data)
    create_notification(
        user_id,
        'Profile Updated',
        'Your patient profile was updated successfully.',
        'profile'
    )
    return jsonify({"success": True, "message": "Profile saved successfully"})

@app.route('/api/doctor/profile', methods=['GET', 'POST'])
def handle_doctor_profile():
    user_id = session.get('user_id')
    if not user_id or session.get('role') != 'doctor':
        return jsonify({"success": False, "error": "Unauthorized"}), 403
        
    if request.method == 'POST':
        data = request.json.get('profile')
        save_doctor_profile(user_id, data)
        create_notification(
            user_id,
            'Doctor Profile Updated',
            'Your professional profile has been updated.',
            'profile'
        )
        return jsonify({"success": True, "message": "Doctor profile updated"})
    
    profile = get_doctor_profile(user_id)
    return jsonify(profile if profile else {})

@app.route('/api/doctor/appointments', methods=['GET'])
def handle_doctor_appointments():
    user_id = session.get('user_id')
    if not user_id or session.get('role') != 'doctor':
        return jsonify({"success": False, "error": "Unauthorized"}), 403
    if not _doctor_is_verified(user_id):
        return jsonify({"success": False, "error": "Doctor account is pending verification."}), 403
        
    doctor = get_doctor_profile(user_id)
    if not doctor:
        return jsonify([])

    date_filter = request.args.get('date')
    appointments = get_doctor_appointments(doctor['id'], date_filter=date_filter)
    return jsonify(appointments)


@app.route('/api/doctor/chats', methods=['GET'])
def handle_doctor_chats():
    user_id = session.get('user_id')
    if not user_id or session.get('role') != 'doctor':
        return jsonify({"success": False, "error": "Unauthorized"}), 403
    if not _doctor_is_verified(user_id):
        return jsonify({"success": False, "error": "Doctor account is pending verification."}), 403

    doctor = get_doctor_profile(user_id)
    if not doctor:
        return jsonify([])

    return jsonify(get_doctor_chats(doctor['id']))


@app.route('/api/doctor/chat/<session_id>', methods=['GET'])
def handle_doctor_chat_history(session_id):
    user_id = session.get('user_id')
    if not user_id or session.get('role') != 'doctor':
        return jsonify({"success": False, "error": "Unauthorized"}), 403
    if not _doctor_is_verified(user_id):
        return jsonify({"success": False, "error": "Doctor account is pending verification."}), 403

    doctor = get_doctor_profile(user_id)
    if not doctor:
        return jsonify({"success": False, "error": "Doctor profile not found"}), 404

    if not doctor_can_access_session(doctor['id'], session_id):
        return jsonify({"success": False, "error": "Unauthorized chat access"}), 403

    return jsonify(get_session_history(session_id))


@app.route('/api/patient/appointments', methods=['GET'])
def handle_patient_appointments():
    user_id = session.get('user_id')
    if not user_id or session.get('role') != 'patient':
        return jsonify({"success": False, "error": "Unauthorized"}), 403
    return jsonify(get_patient_appointments(user_id))


@app.route('/api/doctor/availability', methods=['GET', 'POST'])
def handle_doctor_availability():
    user_id = session.get('user_id')
    if not user_id or session.get('role') != 'doctor':
        return jsonify({"success": False, "error": "Unauthorized"}), 403
    if not _doctor_is_verified(user_id):
        return jsonify({"success": False, "error": "Doctor account is pending verification."}), 403

    doctor = get_doctor_profile(user_id)
    if not doctor:
        return jsonify({"success": False, "error": "Doctor profile not found"}), 404

    if request.method == 'POST':
        slots = request.json.get('slots', [])
        save_doctor_availability(doctor['id'], slots)
        create_notification(
            user_id,
            'Availability Updated',
            'Your free time slots were updated successfully.',
            'availability'
        )
        return jsonify({"success": True, "message": "Availability updated"})

    return jsonify(get_doctor_availability(doctor['id']))


@app.route('/api/doctor/slots', methods=['GET'])
def handle_doctor_slots():
    doctor_id = request.args.get('doctor_id', type=int)
    start_date = request.args.get('date')
    days = request.args.get('days', default=7, type=int)
    if not doctor_id:
        return jsonify({"success": False, "error": "doctor_id is required"}), 400
    if not is_doctor_verified(doctor_id):
        return jsonify({"success": False, "error": "Doctor is not available for booking."}), 403
    return jsonify(get_doctor_free_slots(doctor_id, start_date=start_date, days_ahead=max(1, min(days, 14))))

@app.route('/api/doctor/appointment/status', methods=['POST'])
def handle_appointment_status():
    user_id = session.get('user_id')
    if not user_id or session.get('role') != 'doctor':
        return jsonify({"success": False, "error": "Unauthorized"}), 403
    if not _doctor_is_verified(user_id):
        return jsonify({"success": False, "error": "Doctor account is pending verification."}), 403
        
    data = request.json
    appointment_id = data.get('appointment_id')
    status = data.get('status') # 'accepted', 'rejected', 'completed'

    if status not in ('accepted', 'rejected', 'completed'):
        return jsonify({"success": False, "error": "Invalid status"}), 400

    appointment = get_appointment_by_id(appointment_id)
    if not appointment:
        return jsonify({"success": False, "error": "Appointment not found"}), 404

    # Ensure doctor can update only their own appointments.
    doctor = get_doctor_profile(user_id)
    if not doctor or int(appointment['doctor_id']) != int(doctor['id']):
        return jsonify({"success": False, "error": "Unauthorized appointment update"}), 403
    
    update_appointment_status(appointment_id, status)
    doctor_name = doctor.get('name') if doctor else 'Doctor'

    patient_user_id = get_user_id_by_session(appointment['session_id'])
    if patient_user_id:
        create_notification(
            patient_user_id,
            'Appointment Status Updated',
            f'Your appointment with {doctor_name} on {appointment["appointment_time"]} was {status}.',
            'appointment',
            {'appointment_id': appointment_id, 'doctor_id': appointment.get('doctor_id'), 'doctor_name': doctor_name, 'time': appointment.get('appointment_time'), 'status': status}
        )

    create_notification(
        user_id,
        'Appointment Updated',
            f'Appointment with patient session {appointment.get("session_id", "-")} at {appointment.get("appointment_time", "-")} marked as {status}.',
        'appointment',
            {'appointment_id': appointment_id, 'time': appointment.get('appointment_time'), 'status': status}
    )
    return jsonify({"success": True, "message": f"Appointment {status}"})


@app.route('/api/notifications', methods=['GET'])
def handle_notifications():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"success": False, "error": "Unauthorized"}), 403
    unread_only = request.args.get('unread_only', '0') == '1'
    return jsonify({
        'items': get_notifications(user_id, unread_only=unread_only),
        'unread_count': get_unread_notification_count(user_id)
    })


@app.route('/api/notifications/read', methods=['POST'])
def handle_mark_notification_read():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    data = request.json or {}
    notification_id = data.get('notification_id')
    mark_all = data.get('all', False)
    if mark_all:
        mark_all_notifications_read(user_id)
    elif notification_id:
        mark_notification_read(notification_id, user_id)
    else:
        return jsonify({"success": False, "error": "notification_id or all=true is required"}), 400

    return jsonify({
        'success': True,
        'unread_count': get_unread_notification_count(user_id)
    })

@app.route('/api/clear_chat', methods=['POST'])
def handle_clear_chat():
    data = request.json
    session_id = data.get('session_id')
    
    if not session_id:
        return jsonify({"success": False, "error": "Session ID required"}), 400
        
    clear_session_messages(session_id)
    return jsonify({"success": True, "message": "Chat history cleared"})

@app.route('/api/analytics', methods=['GET'])
def get_analytics():
    session_id = request.args.get('session_id')
    if not session_id:
        return jsonify({"error": "Session ID is required"}), 400
        
    analytics = get_session_analytics(session_id)
    return jsonify(analytics)

@app.route('/api/hospitals', methods=['GET'])
def get_nearby_hospitals():
    lat = request.args.get('lat', type=float)
    lng = request.args.get('lng', type=float)
    radius = request.args.get('radius', default=15000, type=int)
    radius = max(3000, min(radius, 25000))

    if not lat or not lng:
        user_id = session.get('user_id')
        if user_id:
            profile = get_patient_info(user_id)
            if profile and profile.get('lat') and profile.get('lon'):
                lat = float(profile['lat'])
                lng = float(profile['lon'])

    # Keep locator New York specific regardless of remote client geolocation.
    lat, lng = _normalize_new_york_coordinates(lat, lng)
    
    # If coordinates provided, use Overpass API
    if lat and lng:
        overpass_url = "http://overpass-api.de/api/interpreter"
        overpass_query = f"""
        [out:json];
        (
          node["amenity"~"hospital|clinic"](around:{radius}, {lat}, {lng});
          way["amenity"~"hospital|clinic"](around:{radius}, {lat}, {lng});
          relation["amenity"~"hospital|clinic"](around:{radius}, {lat}, {lng});
        );
        out center;
        """
        try:
            response = requests.get(
                overpass_url,
                params={'data': overpass_query},
                headers={'User-Agent': 'MediBotAI/1.0 (+health-assistant)'},
                timeout=12
            )
            response.raise_for_status()
            data = response.json()
            hospitals = []
            seen = set()
            for element in data.get('elements', []):
                name = element.get('tags', {}).get('name', 'Medical Facility')
                h_lat = element.get('lat') or element.get('center', {}).get('lat')
                h_lng = element.get('lon') or element.get('center', {}).get('lon')
                addr = element.get('tags', {}).get('addr:full') or element.get('tags', {}).get('addr:street', 'Nearby Location')
                
                if h_lat and h_lng:
                    key = (name.strip().lower(), round(float(h_lat), 4), round(float(h_lng), 4))
                    if key in seen:
                        continue
                    seen.add(key)
                    hospitals.append({
                        "name": name,
                        "lat": h_lat,
                        "lng": h_lng,
                        "address": addr
                    })
            if hospitals:
                return jsonify(hospitals[:30])
        except Exception as e:
            print(f"Overpass API error: {e}")

    # Fallback/Mock data
    return jsonify([
        {"name": "City General Hospital", "lat": 40.7128, "lng": -74.0060, "address": "123 Health St, NY"},
        {"name": "St. Jude Children's Hospital", "lat": 40.7306, "lng": -73.9352, "address": "456 Kids Ave, NY"},
        {"name": "Metro Care Hospital", "lat": 40.7215, "lng": -73.9902, "address": "22 Park Ave, NY"},
        {"name": "Riverside Medical Center", "lat": 40.7422, "lng": -74.0008, "address": "89 Riverside Dr, NY"},
        {"name": "Unity Trauma Hospital", "lat": 40.7061, "lng": -74.0124, "address": "17 Liberty St, NY"},
        {"name": "Greenfield Multispecialty", "lat": 40.7351, "lng": -73.9807, "address": "300 East St, NY"},
        {"name": "Downtown Emergency Clinic", "lat": 40.7164, "lng": -73.9980, "address": "55 Pine St, NY"},
        {"name": "Hope Community Hospital", "lat": 40.7268, "lng": -74.0155, "address": "120 Harbor Blvd, NY"},
        {"name": "Northside Medical Hub", "lat": 40.7486, "lng": -73.9681, "address": "410 North Ave, NY"},
        {"name": "WellSpring Hospital", "lat": 40.7007, "lng": -73.9652, "address": "208 Wellness Rd, NY"}
    ])

@app.route('/api/doctors/nearby', methods=['GET'])
def fetch_nearby_doctors():
    lat = request.args.get('lat', type=float)
    lng = request.args.get('lng', type=float)
    radius = request.args.get('radius', default=30, type=int)
    radius = max(5, min(radius, 120))
    
    if not lat or not lng:
        # Try to get from user profile
        user_id = session.get('user_id')
        if user_id:
            profile = get_patient_info(user_id)
            if profile and profile.get('lat') and profile.get('lon'):
                lat, lng = profile['lat'], profile['lon']
            elif profile and profile.get('location'):
                g_lat, g_lng = geocode_address(profile.get('location'))
                if g_lat and g_lng:
                    lat, lng = g_lat, g_lng

    lat, lng = _normalize_new_york_coordinates(lat, lng)
    
    nearby = get_nearby_doctors(lat, lng, radius)
    return jsonify(nearby)


@app.route('/api/doctor/profile-image', methods=['POST'])
def upload_doctor_profile_image():
    user_id = session.get('user_id')
    if not user_id or session.get('role') != 'doctor':
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    if 'image' not in request.files:
        return jsonify({"success": False, "error": "No image file uploaded"}), 400

    file = request.files['image']
    if not file or not file.filename:
        return jsonify({"success": False, "error": "Invalid file"}), 400

    if not _allowed_profile_image_file(file.filename):
        return jsonify({"success": False, "error": "Unsupported image type. Use JPG/PNG/WEBP."}), 400

    safe_name = secure_filename(file.filename)
    stamp = datetime.now().strftime('%Y%m%d%H%M%S')
    filename = f'doc_{user_id}_{stamp}_{safe_name}'
    target_path = os.path.join(PROFILE_IMG_UPLOAD_DIR, filename)
    file.save(target_path)

    image_url = f'/static/uploads/doctor_profiles/{filename}'
    current = get_doctor_profile(user_id) or {}
    save_doctor_profile(user_id, {
        'name': current.get('name') or session.get('username') or 'Doctor',
        'specialty': current.get('specialty') or 'General Physician',
        'location': current.get('location') or '',
        'lat': current.get('lat'),
        'lon': current.get('lon'),
        'image_url': image_url,
    })

    return jsonify({"success": True, "image_url": image_url})

@app.route('/api/route', methods=['GET'])
def get_osrm_route():
    start_lat = request.args.get('start_lat')
    start_lng = request.args.get('start_lng')
    end_lat = request.args.get('end_lat')
    end_lng = request.args.get('end_lng')
    
    if not all([start_lat, start_lng, end_lat, end_lng]):
        return jsonify({"error": "Missing coordinates"}), 400
        
    osrm_url = f"http://router.project-osrm.org/route/v1/driving/{start_lng},{start_lat};{end_lng},{end_lat}?overview=full&geometries=geojson"
    try:
        response = requests.get(osrm_url)
        return jsonify(response.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/download_dataset', methods=['GET'])
def download_dataset():
    dataset_path = os.path.join(os.path.dirname(__file__), "data", "Training.csv")
    if os.path.exists(dataset_path):
        return send_file(dataset_path, as_attachment=True)
    return jsonify({"error": "Dataset not found"}), 404

# Admin Routes
@app.route('/api/admin/users', methods=['GET'])
@admin_required
def admin_get_users():
    return jsonify(get_all_users())

@app.route('/api/admin/user/status', methods=['POST'])
@admin_required
def admin_update_user():
    data = request.json
    user_id = data.get('user_id')
    is_verified = data.get('is_verified')
    is_blocked = data.get('is_blocked')

    target_user = get_user_by_id(user_id)
    if not target_user:
        return jsonify({"success": False, "error": "User not found"}), 404

    if target_user.get('role') == 'doctor' and is_verified is not None:
        return jsonify({
            "success": False,
            "error": "Doctor verification must be done through certificate review."
        }), 400

    update_user_status(user_id, is_verified, is_blocked)

    if is_verified is not None:
        verdict = 'verified' if int(is_verified) == 1 else 'marked unverified'
        create_notification(
            user_id,
            'Account Verification Update',
            f'Your doctor account has been {verdict} by admin.',
            'verification'
        )

    if is_blocked is not None:
        block_text = 'blocked' if int(is_blocked) == 1 else 'unblocked'
        create_notification(
            user_id,
            'Account Status Update',
            f'Your account has been {block_text} by admin.',
            'account'
        )
    return jsonify({"success": True})

@app.route('/api/admin/user/delete', methods=['POST'])
@admin_required
def admin_delete_user():
    user_id = request.json.get('user_id')
    delete_user(user_id)
    return jsonify({"success": True})

@app.route('/api/admin/chats', methods=['GET'])
@admin_required
def admin_get_chats():
    return jsonify(get_all_chats())

@app.route('/api/admin/chat/<session_id>', methods=['GET'])
@admin_required
def admin_get_chat_history(session_id):
    return jsonify(get_session_history(session_id))

@app.route('/api/admin/stats', methods=['GET'])
@admin_required
def admin_get_stats():
    return jsonify(get_admin_stats())


@app.route('/api/doctor/certificate', methods=['POST', 'GET'])
def handle_doctor_certificate():
    user_id = session.get('user_id')
    if not user_id or session.get('role') != 'doctor':
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    if request.method == 'GET':
        cert = get_latest_doctor_certificate(user_id)
        return jsonify(cert if cert else {})

    if 'certificate' not in request.files:
        return jsonify({"success": False, "error": "No certificate file uploaded"}), 400

    file = request.files['certificate']
    if not file or not file.filename:
        return jsonify({"success": False, "error": "Invalid file"}), 400

    if not _allowed_cert_file(file.filename):
        return jsonify({"success": False, "error": "Unsupported file type. Use PDF/JPG/PNG."}), 400

    safe_name = secure_filename(file.filename)
    stamp = datetime.now().strftime('%Y%m%d%H%M%S')
    filename = f'{user_id}_{stamp}_{safe_name}'
    path = os.path.join(CERT_UPLOAD_DIR, filename)
    file.save(path)

    cert_id = save_doctor_certificate(user_id, path)
    create_notification(
        user_id,
        'Certificate Submitted',
        'Your certificate was submitted and is pending admin review.',
        'verification',
        {'certificate_id': cert_id}
    )
    return jsonify({"success": True, "certificate_id": cert_id})


@app.route('/api/admin/doctor/certificates', methods=['GET'])
@admin_required
def admin_list_certificates():
    return jsonify(list_pending_certificates())


@app.route('/api/admin/doctor/certificate/<int:cert_id>/download', methods=['GET'])
@admin_required
def admin_download_certificate(cert_id):
    cert = get_certificate_by_id(cert_id)
    if not cert:
        return jsonify({"success": False, "error": "Certificate not found"}), 404
    path = cert.get('file_path')
    if not path or not os.path.exists(path):
        return jsonify({"success": False, "error": "Certificate file missing"}), 404
    return send_file(path, as_attachment=True)


@app.route('/api/admin/doctor/certificate/review', methods=['POST'])
@admin_required
def admin_review_certificate():
    data = request.json or {}
    cert_id = data.get('certificate_id')
    status = data.get('status')
    notes = data.get('notes')
    if status not in ('approved', 'rejected'):
        return jsonify({"success": False, "error": "Invalid review status"}), 400
    if not cert_id:
        return jsonify({"success": False, "error": "certificate_id is required"}), 400

    cert = get_certificate_by_id(cert_id)
    if not cert:
        return jsonify({"success": False, "error": "Certificate not found"}), 404

    review_doctor_certificate(cert_id, status, session.get('user_id'), notes=notes)

    # Notify doctor about verification result.
    reviewed_user_id = cert.get('user_id')

    if reviewed_user_id:
        create_notification(
            reviewed_user_id,
            'Certificate Review Completed',
            f'Your certificate has been {status}.',
            'verification',
            {'certificate_id': cert_id, 'status': status}
        )

    return jsonify({"success": True})

if __name__ == '__main__':
    debug_mode = os.getenv('APP_DEBUG', '0').lower() in ('1', 'true', 'yes')
    app.run(debug=debug_mode, use_reloader=debug_mode, port=5000)
