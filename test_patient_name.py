import requests
import sqlite3
import uuid

BASE_URL = "http://127.0.0.1:5000"
DB_PATH = 'chat_memory.db'

# 1. Create a dummy patient
requests.post(f"{BASE_URL}/api/signup", json={
    "username": "tester_patient_123",
    "password": "password",
    "role": "patient"
})

# 2. Get the patient user_id
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute("SELECT id FROM users WHERE username = 'tester_patient_123'")
patient_id = c.fetchone()[0]

# 3. Create a session for them
session_id = str(uuid.uuid4())
c.execute("INSERT INTO sessions (session_id, user_id, created_at) VALUES (?, ?, CURRENT_TIMESTAMP)", (session_id, patient_id))

# 4. Book an appointment for a doctor (we will use doctor_id 1)
c.execute("INSERT INTO appointments (session_id, doctor_id, appointment_time, status) VALUES (?, 1, 'Tomorrow 10 AM', 'pending')", (session_id,))
conn.commit()
conn.close()

# 5. Fetch doctor's appointments by calling the database function directly to test the SQL
from database import get_doctor_appointments
appointments = get_doctor_appointments(1)

success = False
for app in appointments:
    if app['session_id'] == session_id:
        print(f"Appointment ID: {app['id']}")
        print(f"Patient Name Returned: {app['patient_name']}")
        if app['patient_name'] == 'tester_patient_123':
            success = True
            print("SUCCESS: Patient name fallback to username works!")
            break

if not success:
    print("FAILED: Did not find the correct patient name fallback.")

# Cleanup
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute("DELETE FROM appointments WHERE session_id = ?", (session_id,))
c.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
c.execute("DELETE FROM users WHERE username = 'tester_patient_123'")
conn.commit()
conn.close()

