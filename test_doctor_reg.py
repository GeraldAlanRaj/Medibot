import requests
import json

BASE_URL = "http://127.0.0.1:5000"

print("1. Registering new doctor...")
signup_payload = {
    "username": "dr_dynamic",
    "password": "password123",
    "role": "doctor",
    "name": "Dr. Dynamic Tester",
    "specialty": "Neurologist",
    "location": "Dynamic Clinic, NY"
}
signup_res = requests.post(f"{BASE_URL}/api/signup", json=signup_payload)
print(f"Signup Status: {signup_res.status_code}")
print(f"Signup Response: {signup_res.json()}")

print("\n2. Fetching list of all doctors for Book Doctor view...")
doctors_res = requests.get(f"{BASE_URL}/api/doctors")
print(f"Doctors list status: {doctors_res.status_code}")
doctors_list = doctors_res.json()
print("Registered Doctors:")
for doc in doctors_list:
    print(f" - {doc['name']} ({doc['specialty']} @ {doc['location']})")
    
if any(d['name'] == 'Dr. Sarah Smith' for d in doctors_list):
    print("WARNING: Hardcoded dummy doctor found in output.")
else:
    print("SUCCESS: Hardcoded doctors are successfully hidden.")
    
if any(d['name'] == 'Dr. Dynamic Tester' for d in doctors_list):
    print("SUCCESS: Newly registered doctor 'Dr. Dynamic Tester' is present in the list.")
else:
    print("WARNING: Newly registered doctor is missing from the list.")

