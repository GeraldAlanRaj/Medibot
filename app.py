import requests # pyre-ignore[21]
import os
import uuid
from flask import Flask, request, jsonify, render_template, session, send_file # pyre-ignore[21]
from flask_cors import CORS # pyre-ignore[21]
from werkzeug.security import generate_password_hash, check_password_hash # pyre-ignore[21]
from functools import wraps
from database import ( # pyre-ignore[21]
    init_db, create_session, add_message, get_session_history,
    get_doctors, book_appointment, save_patient_info, get_session_analytics,
    create_user, get_user_by_username, get_user_by_id, get_patient_info,
    clear_session_messages, get_all_users, update_user_status, delete_user, 
    get_all_chats, get_admin_stats, get_nearby_doctors, geocode_address,
    get_doctor_profile, save_doctor_profile, get_doctor_appointments, update_appointment_status
)
from agent import handle_user_input # pyre-ignore[21]

template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'templates'))
static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'static'))

app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
app.secret_key = os.urandom(24)
CORS(app)

# Helper for role-based access
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('role') != 'admin':
            return jsonify({"error": "Admin access required"}), 403
        return f(*args, **kwargs)
    return decorated_function

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
    role = data.get('role', 'patient') # default to patient
    
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
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['role'] = user['role']
        return jsonify({
            "success": True, 
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
    if user['role'] == 'patient':
        profile = get_patient_info(user_id)
    elif user['role'] == 'doctor':
        doctor_info = get_doctor_profile(user_id)
        
    return jsonify({
        "authenticated": True, 
        "user": user, 
        "profile": profile,
        "doctor_info": doctor_info
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
        
    if not all([doctor_id, time]):
        return jsonify({"success": False, "error": "Doctor and time slot required"}), 400
        
    try:
        book_appointment(session_id, doctor_id, time)
        return jsonify({
            "success": True, 
            "message": "Appointment booked successfully",
            "session_id": session_id
        })
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
    return jsonify({"success": True, "message": "Profile saved successfully"})

@app.route('/api/doctor/profile', methods=['GET', 'POST'])
def handle_doctor_profile():
    user_id = session.get('user_id')
    if not user_id or session.get('role') != 'doctor':
        return jsonify({"success": False, "error": "Unauthorized"}), 403
        
    if request.method == 'POST':
        data = request.json.get('profile')
        save_doctor_profile(user_id, data)
        return jsonify({"success": True, "message": "Doctor profile updated"})
    
    profile = get_doctor_profile(user_id)
    return jsonify(profile if profile else {})

@app.route('/api/doctor/appointments', methods=['GET'])
def handle_doctor_appointments():
    user_id = session.get('user_id')
    if not user_id or session.get('role') != 'doctor':
        return jsonify({"success": False, "error": "Unauthorized"}), 403
        
    doctor = get_doctor_profile(user_id)
    if not doctor:
        return jsonify([])
        
    appointments = get_doctor_appointments(doctor['id'])
    return jsonify(appointments)

@app.route('/api/doctor/appointment/status', methods=['POST'])
def handle_appointment_status():
    user_id = session.get('user_id')
    if not user_id or session.get('role') != 'doctor':
        return jsonify({"success": False, "error": "Unauthorized"}), 403
        
    data = request.json
    appointment_id = data.get('appointment_id')
    status = data.get('status') # 'accepted', 'rejected', 'completed'
    
    update_appointment_status(appointment_id, status)
    return jsonify({"success": True, "message": f"Appointment {status}"})

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
    lat = request.args.get('lat')
    lng = request.args.get('lng')
    
    # If coordinates provided, use Overpass API
    if lat and lng:
        overpass_url = "http://overpass-api.de/api/interpreter"
        overpass_query = f"""
        [out:json];
        (node["amenity"="hospital"](around:10000, {lat}, {lng});
         way["amenity"="hospital"](around:10000, {lat}, {lng});
         relation["amenity"="hospital"](around:10000, {lat}, {lng}););
        out center;
        """
        try:
            response = requests.get(overpass_url, params={'data': overpass_query}, timeout=10)
            data = response.json()
            hospitals = []
            for element in data.get('elements', []):
                name = element.get('tags', {}).get('name', 'Medical Facility')
                h_lat = element.get('lat') or element.get('center', {}).get('lat')
                h_lng = element.get('lon') or element.get('center', {}).get('lon')
                addr = element.get('tags', {}).get('addr:full') or element.get('tags', {}).get('addr:street', 'Nearby Location')
                
                if h_lat and h_lng:
                    hospitals.append({
                        "name": name,
                        "lat": h_lat,
                        "lng": h_lng,
                        "address": addr
                    })
            return jsonify([h for i, h in enumerate(hospitals) if i < 12]) # Top 12 results
        except Exception as e:
            print(f"Overpass API error: {e}")

    # Fallback/Mock data
    return jsonify([
        {"name": "City General Hospital", "lat": 40.7128, "lng": -74.0060, "address": "123 Health St, NY"},
        {"name": "St. Jude Children's Hospital", "lat": 40.7306, "lng": -73.9352, "address": "456 Kids Ave, NY"}
    ])

@app.route('/api/doctors/nearby', methods=['GET'])
def fetch_nearby_doctors():
    lat = request.args.get('lat', type=float)
    lng = request.args.get('lng', type=float)
    radius = request.args.get('radius', default=100, type=int)
    
    if not lat or not lng:
        # Try to get from user profile
        user_id = session.get('user_id')
        if user_id:
            profile = get_patient_info(user_id)
            if profile and profile.get('lat') and profile.get('lon'):
                lat, lng = profile['lat'], profile['lon']
    
    if lat and lng:
        return jsonify(get_nearby_doctors(lat, lng, radius))
    return jsonify(get_doctors())

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
    update_user_status(user_id, is_verified, is_blocked)
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

if __name__ == '__main__':
    app.run(debug=True, port=5000)
