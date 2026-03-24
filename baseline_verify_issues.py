import json
import time
import uuid
import requests

BASE = "http://127.0.0.1:5000"

def out(name, passed, details):
    print(json.dumps({"check": name, "passed": bool(passed), "details": details}, ensure_ascii=False))


def signup(username, password, role, **extra):
    payload = {"username": username, "password": password, "role": role}
    payload.update(extra)
    s = requests.Session()
    r = s.post(f"{BASE}/api/signup", json=payload, timeout=30)
    return s, r


def login(username, password):
    s = requests.Session()
    r = s.post(f"{BASE}/api/login", json={"username": username, "password": password}, timeout=30)
    return s, r


def try_json(r):
    try:
        return r.json()
    except Exception:
        return {"text": r.text[:500]}


def main():
    ts = int(time.time())
    patient_u = f"pt_{ts}"
    doctor_u = f"dr_{ts}"
    admin_u = f"ad_{ts}"
    pw = "Pass123!"

    # Create users
    p_s, p_signup = signup(patient_u, pw, "patient")
    d_s, d_signup = signup(doctor_u, pw, "doctor", name=f"Dr {doctor_u}", specialty="General Physician", location="New York, NY")
    a_s, a_signup = signup(admin_u, pw, "admin")

    out("signup_patient", p_signup.status_code == 200 and try_json(p_signup).get("success"), try_json(p_signup))
    out("signup_doctor", d_signup.status_code == 200 and try_json(d_signup).get("success"), try_json(d_signup))
    out("signup_admin", a_signup.status_code == 200 and try_json(a_signup).get("success"), try_json(a_signup))

    # Login sessions
    p, p_login = login(patient_u, pw)
    d, d_login = login(doctor_u, pw)
    a, a_login = login(admin_u, pw)
    out("login_patient", p_login.status_code == 200 and try_json(p_login).get("success"), try_json(p_login))
    out("login_doctor", d_login.status_code == 200 and try_json(d_login).get("success"), try_json(d_login))
    out("login_admin", a_login.status_code == 200 and try_json(a_login).get("success"), try_json(a_login))

    # Chat flow: symptom then no
    c1 = p.post(f"{BASE}/api/chat", json={"message": "I have headache and fever", "language": "en"}, timeout=60)
    c1j = try_json(c1)
    sid = c1j.get("session_id")
    c2 = p.post(f"{BASE}/api/chat", json={"session_id": sid, "message": "no", "language": "en"}, timeout=60)
    c2j = try_json(c2)
    out("chat_no_question_handling", c2.status_code == 200, c2j)

    # Translation sample
    c3 = p.post(f"{BASE}/api/chat", json={"session_id": sid, "message": "Tengo fiebre y dolor de cabeza", "language": "es"}, timeout=60)
    c3j = try_json(c3)
    out("translation_response_spanish", c3.status_code == 200, c3j)

    # Profile update: includes gender (currently expected missing)
    profile_payload = {
        "profile": {
            "full_name": "Test Patient",
            "age": 29,
            "gender": "female",
            "email": "pt@example.com",
            "phone": "1234567890",
            "location": "New York",
            "medical_history": "none"
        }
    }
    sp = p.post(f"{BASE}/api/save_profile", json=profile_payload, timeout=30)
    me = p.get(f"{BASE}/api/me", timeout=30)
    out("patient_profile_update_with_gender", sp.status_code == 200 and me.status_code == 200, {"save": try_json(sp), "me": try_json(me)})

    # Doctors list and nearby specialists
    docs = p.get(f"{BASE}/api/doctors", timeout=30)
    docsj = try_json(docs)
    out("doctors_list_nonempty", docs.status_code == 200 and isinstance(docsj, list), {"count": len(docsj) if isinstance(docsj, list) else None, "sample": docsj[:1] if isinstance(docsj, list) and docsj else docsj})

    nearby = p.get(f"{BASE}/api/doctors/nearby?lat=40.7128&lng=-74.0060", timeout=30)
    out("nearby_specialists", nearby.status_code == 200, try_json(nearby)[:2] if isinstance(try_json(nearby), list) else try_json(nearby))

    # Book appointment twice same slot (duplicate)
    doctor_id = docsj[0]["id"] if isinstance(docsj, list) and docsj else None
    if doctor_id:
        tslot = "2026-03-20T10:00"
        b1 = p.post(f"{BASE}/api/book_appointment", json={"session_id": sid, "doctor_id": doctor_id, "time": tslot}, timeout=30)
        b2 = p.post(f"{BASE}/api/book_appointment", json={"session_id": sid, "doctor_id": doctor_id, "time": tslot}, timeout=30)
        out("duplicate_appointment_allowed", b1.status_code == 200 and b2.status_code == 200, {"first": try_json(b1), "second": try_json(b2)})

        # Doctor appointment status action
        d_apps = d.get(f"{BASE}/api/doctor/appointments", timeout=30)
        d_apps_j = try_json(d_apps)
        out("doctor_can_view_appointments", d_apps.status_code == 200, {"count": len(d_apps_j) if isinstance(d_apps_j, list) else None, "sample": d_apps_j[:1] if isinstance(d_apps_j, list) else d_apps_j})
        if isinstance(d_apps_j, list) and d_apps_j:
            app_id = d_apps_j[0].get("id")
            st = d.post(f"{BASE}/api/doctor/appointment/status", json={"appointment_id": app_id, "status": "accepted"}, timeout=30)
            out("doctor_accept_reject", st.status_code == 200 and try_json(st).get("success"), try_json(st))
    else:
        out("duplicate_appointment_allowed", False, "No doctors available to test booking")
        out("doctor_can_view_appointments", False, "No doctors available to test appointments")
        out("doctor_accept_reject", False, "No appointments available to update")

    # Notifications and slots endpoints expected missing in current code
    n1 = p.get(f"{BASE}/api/notifications", timeout=30)
    out("notifications_endpoint_exists", n1.status_code != 404, {"status": n1.status_code, "body": try_json(n1)})

    s1 = p.get(f"{BASE}/api/doctor/slots?doctor_id=1", timeout=30)
    out("doctor_free_slots_endpoint_exists", s1.status_code != 404, {"status": s1.status_code, "body": try_json(s1)})

    # Admin chat history check
    ach = a.get(f"{BASE}/api/admin/chats", timeout=30)
    achj = try_json(ach)
    if isinstance(achj, list) and achj:
        sess = achj[0].get("session_id")
        one = a.get(f"{BASE}/api/admin/chat/{sess}", timeout=30)
        out("admin_can_view_chat_history", one.status_code == 200 and isinstance(try_json(one), list), {"list_count": len(achj), "history_count": len(try_json(one)) if isinstance(try_json(one), list) else None})
    else:
        out("admin_can_view_chat_history", False, {"admin_chats_status": ach.status_code, "data": achj})

    # Certificate upload endpoint expected missing
    cert = d.post(f"{BASE}/api/doctor/certificate", timeout=30)
    out("doctor_certificate_upload_endpoint_exists", cert.status_code != 404, {"status": cert.status_code, "body": try_json(cert)})


if __name__ == "__main__":
    main()
