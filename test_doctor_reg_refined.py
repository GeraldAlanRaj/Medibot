import requests
import json

BASE_URL = "http://127.0.0.1:5000"

print("1. Registering new doctor bypassing username field")
signup_payload = {
    # Note: NO explicit username passed from frontend form anymore
    "password": "password123",
    "role": "doctor",
    "name": "Dr. NoUsername",
    "username": "Dr. NoUsername", # Payload building logic in app.js assigns Full Name to username
    "specialty": "Orthopedics",
    "location": "Bone Clinic, NY"
}
signup_res = requests.post(f"{BASE_URL}/api/signup", json=signup_payload)
print(f"Signup Status: {signup_res.status_code}")
print(f"Signup Response: {signup_res.json()}")

