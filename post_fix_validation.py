import json
import time
import requests
from datetime import datetime, timedelta

BASE = "http://127.0.0.1:5000"


def jprint(name, ok, data):
    print(json.dumps({"check": name, "passed": bool(ok), "details": data}, ensure_ascii=False))


def login(username, password):
    s = requests.Session()
    r = s.post(f"{BASE}/api/login", json={"username": username, "password": password}, timeout=30)
    return s, r


def signup(username, password, role, **extra):
    s = requests.Session()
    payload = {"username": username, "password": password, "role": role}
    payload.update(extra)
    r = s.post(f"{BASE}/api/signup", json=payload, timeout=30)
    return s, r


def pick_next_weekday(target_weekday):
    # Monday=0 ... Sunday=6
    today = datetime.now().date()
    days_ahead = (target_weekday - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return today + timedelta(days=days_ahead)


def main():
    ts = int(time.time())
    pw = "Pass123!"

    patient_u = f"pt_fx_{ts}"
    doctor_u = f"dr_fx_{ts}"
    admin_u = f"ad_fx_{ts}"

    # Create users
    _, sp = signup(patient_u, pw, "patient")
    _, sd = signup(doctor_u, pw, "doctor", name=f"Dr {doctor_u}", specialty="General Physician", location="New York, NY")
    _, sa = signup(admin_u, pw, "admin")

    jprint("signup_users", all([sp.status_code == 200, sd.status_code == 200, sa.status_code == 200]), {
        "patient": sp.json(), "doctor": sd.json(), "admin": sa.json()
    })

    patient, lp = login(patient_u, pw)
    doctor, ld = login(doctor_u, pw)
    admin, la = login(admin_u, pw)
    jprint("login_users", all([lp.status_code == 200, ld.status_code == 200, la.status_code == 200]), {
        "patient": lp.json(), "doctor": ld.json(), "admin": la.json()
    })

    # Doctor sets weekly availability
    slots_payload = {
        "slots": [
            {"day_of_week": "Monday", "start_time": "09:00", "end_time": "12:00"},
            {"day_of_week": "Tuesday", "start_time": "10:00", "end_time": "13:00"}
        ]
    }
    sav = doctor.post(f"{BASE}/api/doctor/availability", json=slots_payload, timeout=30)
    gav = doctor.get(f"{BASE}/api/doctor/availability", timeout=30)
    jprint("doctor_set_availability", sav.status_code == 200 and sav.json().get("success") and len(gav.json()) >= 2, {
        "save": sav.json(), "get": gav.json()
    })

    # Get doctor id
    me_doc = doctor.get(f"{BASE}/api/me", timeout=30).json()
    doctor_id = me_doc.get("doctor_info", {}).get("id")

    # Get free slots for next Monday
    date = pick_next_weekday(0).strftime("%Y-%m-%d")
    free = patient.get(f"{BASE}/api/doctor/slots?doctor_id={doctor_id}&date={date}&days=1", timeout=30)
    freej = free.json()
    has_slots = isinstance(freej, list) and len(freej) > 0 and len(freej[0].get("slots", [])) > 0
    jprint("patient_can_see_doctor_free_slots", free.status_code == 200 and has_slots, freej)

    slot = freej[0]["slots"][0]

    # Start chat investigation and test "no" handling
    c1 = patient.post(f"{BASE}/api/chat", json={"message": "I have headache and fever", "language": "en"}, timeout=60).json()
    sid = c1.get("session_id")
    c2 = patient.post(f"{BASE}/api/chat", json={"session_id": sid, "message": "no", "language": "en"}, timeout=60).json()
    c3 = patient.post(f"{BASE}/api/chat", json={"session_id": sid, "message": "for 3 days", "language": "en"}, timeout=60).json()
    jprint("conversation_no_and_duration_handling", (
        "Thanks for confirming" in c2.get("reply", "") and "duration" in c3.get("reply", "").lower() or c3.get("is_diagnosis") is False
    ), {"after_no": c2, "after_duration": c3})

    # Book appointment with slot; duplicate should fail
    b1 = patient.post(f"{BASE}/api/book_appointment", json={"session_id": sid, "doctor_id": doctor_id, "time": slot}, timeout=30)
    b2 = patient.post(f"{BASE}/api/book_appointment", json={"session_id": sid, "doctor_id": doctor_id, "time": slot}, timeout=30)
    jprint("duplicate_appointment_blocked", b1.status_code == 200 and b2.status_code == 409, {
        "first": b1.json(), "second": b2.json()
    })

    # Doctor sees and accepts appointment
    da = doctor.get(f"{BASE}/api/doctor/appointments", timeout=30).json()
    appt = da[0] if da else None
    ok_view = bool(appt and appt.get("session_id") == sid)
    jprint("doctor_views_patient_appointment", ok_view, {"count": len(da), "sample": appt})

    if appt:
        up = doctor.post(f"{BASE}/api/doctor/appointment/status", json={"appointment_id": appt["id"], "status": "accepted"}, timeout=30)
        jprint("doctor_accepts_appointment", up.status_code == 200 and up.json().get("success"), up.json())

    # Notifications appear for patient and doctor
    pn = patient.get(f"{BASE}/api/notifications", timeout=30).json()
    dn = doctor.get(f"{BASE}/api/notifications", timeout=30).json()
    p_ok = any("Appointment" in i.get("title", "") for i in pn.get("items", []))
    d_ok = any("Appointment" in i.get("title", "") for i in dn.get("items", []))
    jprint("notifications_work_for_both_roles", p_ok and d_ok, {
        "patient_unread": pn.get("unread_count"),
        "doctor_unread": dn.get("unread_count"),
        "patient_top": pn.get("items", [])[:2],
        "doctor_top": dn.get("items", [])[:2]
    })

    # Certificate upload and admin review
    fake_pdf = b"%PDF-1.4\n% fake certificate\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
    files = {"certificate": ("proof.pdf", fake_pdf, "application/pdf")}
    cu = doctor.post(f"{BASE}/api/doctor/certificate", files=files, timeout=30)
    cert_ok = cu.status_code == 200 and cu.json().get("success")

    pending = admin.get(f"{BASE}/api/admin/doctor/certificates", timeout=30).json()
    this_pending = next((c for c in pending if c.get("user_id") == me_doc["user"]["id"]), None)
    review_ok = False
    if this_pending:
        rv = admin.post(
            f"{BASE}/api/admin/doctor/certificate/review",
            json={"certificate_id": this_pending["id"], "status": "approved", "notes": "Verified"},
            timeout=30
        )
        review_ok = rv.status_code == 200 and rv.json().get("success")

    jprint("doctor_certificate_upload_and_admin_review", cert_ok and review_ok, {
        "upload": cu.json() if cu.content else {},
        "pending_found": bool(this_pending),
        "review_ok": review_ok
    })

    # Admin chat history still works
    chats = admin.get(f"{BASE}/api/admin/chats", timeout=30).json()
    row = next((c for c in chats if c.get("session_id") == sid), None)
    hist = admin.get(f"{BASE}/api/admin/chat/{sid}", timeout=30).json()
    jprint("admin_can_view_patient_chat_history", bool(row) and isinstance(hist, list) and len(hist) > 0, {
        "chat_row": row,
        "history_count": len(hist) if isinstance(hist, list) else None
    })


if __name__ == "__main__":
    main()
