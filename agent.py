from database import get_session_history
from database import get_doctors
from ml_models import ml_models
import json
import re
import hashlib

MAX_FOLLOWUP_ROUNDS = 6

def _get_current_context_history(history):
    """
    Keep only the latest coherent symptom episode so older complaints
    do not pollute a fresh complaint.
    """
    if not history:
        return []

    context_start = 0
    context_symptoms = set()

    for idx, msg in enumerate(history):
        if msg.get('role') != 'user':
            continue
        msg_symptoms = set(msg.get('extracted_symptoms') or [])
        if not msg_symptoms:
            continue

        if not context_symptoms:
            context_symptoms = set(msg_symptoms)
            context_start = idx
            continue

        # If there's an overlap or it's a small history, assume continuation
        if context_symptoms.intersection(msg_symptoms) or len(history) - idx < 5:
            context_symptoms.update(msg_symptoms)
        else:
            # New disjoint complaint started here.
            context_start = idx
            context_symptoms = set(msg_symptoms)

    return history[context_start:]

def _extract_asked_followups(history):
    asked = set()
    for msg in history:
        if msg.get('role') != 'agent':
            continue
        content = msg.get('content', '')
        # Simple extraction from agent messages
        asked.update(ml_models.extract_symptoms(content))
    return asked

def _count_followup_rounds(history):
    # Count how many times the agent asked clarifying questions
    return sum(1 for msg in history if msg.get('role') == 'agent' and '?' in msg.get('content', ''))

def _has_duration_info(text):
    text = (text or '').lower()
    if not text:
        return False
    # Common duration patterns
    if re.search(r'\b\d+\s*(day|days|week|weeks|month|months|hour|hours|दिन|हफ्ते|महीने)\b', text):
        return True
    duration_words = ['since', 'for', 'yesterday', 'today', 'morning', 'night', 'कल', 'आज', 'सुबह']
    return any(word in text for word in duration_words)

def _extract_duration_context(history, user_message):
    if _has_duration_info(user_message):
        return True
    for msg in reversed(history):
        if msg.get('role') == 'user' and _has_duration_info(msg.get('content', '')):
            return True
    return False

def _recommend_specialty(disease):
    disease_lower = (disease or '').lower()
    mapping = [
        (['heart', 'cardio', 'hypertension'], 'Cardiologist'),
        (['skin', 'fungal', 'acne', 'psoriasis', 'dermatitis'], 'Dermatologist'),
        (['brain', 'migraine', 'neuro', 'paralysis', 'vertigo'], 'Neurologist'),
        (['diabetes', 'thyroid', 'hormone'], 'Endocrinologist'),
        (['kidney', 'urine'], 'Nephrologist'),
        (['lung', 'asthma', 'bronchitis', 'pneumonia', 'rhinitis', 'sneezing', 'cough'], 'Pulmonologist'),
        (['stomach', 'liver', 'gastro', 'ulcer'], 'Gastroenterologist')
    ]
    for keywords, specialty in mapping:
        if any(k in disease_lower for k in keywords):
            return specialty
    return 'General Physician'

def _doctor_recommendations(disease):
    doctors = get_doctors()
    if not doctors:
        return ''

    # Filter for New York area (example constraint)
    doctors = [
        d for d in doctors
        if d.get('lat') is not None
        and d.get('lon') is not None
        and 40.30 <= float(d.get('lat')) <= 41.20
        and -74.40 <= float(d.get('lon')) <= -73.40
    ]
    
    specialty = _recommend_specialty(disease)
    matched = [d for d in doctors if specialty.lower() in (d.get('specialty') or '').lower()]
    candidates = matched if matched else sorted(doctors, key=lambda d: d.get('rating') or 0, reverse=True)
    top = candidates[:3]
    
    if not top:
        return ''

    doctor_lines = [f"- {d.get('name')} ({d.get('specialty')}, {d.get('location')})" for d in top]
    return (
        f"\n\nSuggested specialist: **{specialty}**.\n"
        "Doctors you can book now:\n" + "\n".join(doctor_lines)
    )

def handle_user_input(session_id, user_message, language="en"):
    """
    Orchestrates the conversation using an LLM-first approach.
    """
    from llm_api import ask_llm
    
    # Get conversation history for context
    history = get_session_history(session_id)
    
    # 1. Symptom Extraction (Hybrid LLM + Regex)
    new_symptoms = ml_models.extract_symptoms(user_message, language=language)
    
    # Build current context symptoms
    context_history = _get_current_context_history(history)
    current_context_symptoms = set()
    for msg in context_history:
        if msg.get('extracted_symptoms'):
            current_context_symptoms.update(msg['extracted_symptoms'])
    
    all_symptoms = list(current_context_symptoms.union(set(new_symptoms)))

    # 2. Clinical Model Logic (Run earlier to support Emergency Analysis)
    disease, confidence = (None, 0)
    specialty = "General Physician"
    if all_symptoms:
        disease, confidence = ml_models.predict_disease(all_symptoms)
        specialty = _recommend_specialty(disease)

    def prettify(s):
        return s.replace('_', ' ').title()
    
    pretty_all = [prettify(s) for s in all_symptoms]
    pretty_new = [prettify(s) for s in new_symptoms]

    # 3. Safety Check (Red Flags)
    if ml_models.check_red_flags(new_symptoms):
        # Professional Emergency Prompt for India
        emergency_prompt = (
            f"The user reports potentially life-threatening symptoms: {', '.join(pretty_new)}.\n"
            "STRUCTURE YOUR ENTIRE RESPONSE AS FOLLOWS (CRITICAL):\n"
            "1. Header: '# URGENT EMERGENCY WARNING'.\n"
            "2. Explain promptly that symptoms require immediate medical attention.\n"
            "3. Instruction: 'PLEASE CALL EMERGENCY SERVICES (102 or 112) IMMEDIATELY'.\n"
            "4. Practical steps: 'Try to stay calm and wait for help. If you're with someone, ask them to call for you.'\n"
            "5. Section 'AI ANALYSIS':\n"
            f"   - Symptoms identified: {', '.join(pretty_all)}\n"
            f"   - Condition match: {disease or 'Under investigation'} (Confidence: {confidence*100:.1f}%)\n"
            "6. A brief closing line: 'Please follow the above steps to get the medical help you need.'\n"
            "7. NO AI disclaimer, NO 'REMEMBER' section, and NO extra spacing between lines.\n\n"
            f"Respond entirely in {language}."
        )
        reply = ask_llm(emergency_prompt, language=language, history=history)
        
        # Add doctor recommendations to the bottom
        if disease:
            # Add doctor recommendations - will include its own specialist header
            reply += _doctor_recommendations(disease)
            
        return {
            "reply": reply,
            "session_id": session_id,
            "is_diagnosis": False,
            "symptoms": all_symptoms,
            "new_symptoms": new_symptoms
        }

    # 4. LLM Response Generation
    triage_info = ""
    if all_symptoms:
        triage_info = f"Current symptoms identified: {', '.join(all_symptoms)}. "
        if disease:
            triage_info += f"Clinical match: {disease} (Confidence: {confidence:.2f}). "

    # Determine if we should finalize the triage
    is_terminal = (confidence >= 0.85 and len(all_symptoms) >= 3) or (_count_followup_rounds(context_history) >= MAX_FOLLOWUP_ROUNDS)
    
    # Construct targeted prompt for Gemini
    if is_terminal and disease:
        user_prompt = (
            f"{user_message}\n\n"
            f"[Internal context: The triage is complete. The clinical model predicts {disease} with {confidence*100:.1f}% confidence. "
            f"Explain this condition, suggest care steps, and emphasize the disclaimer. "
            f"Include appropriate specialist recommendation based on {disease}.]"
        )
        reply = ask_llm(user_prompt, language=language, history=history)
        
        # Add doctor recommendations if it's a final diagnosis presentation
        if "**" in reply or "diagnosis" in reply.lower(): # Basic heuristic that it followed instructions
            reply += _doctor_recommendations(disease)
            
    else:
        # Guidance for more triage or QA
        duration_context = "User has NOT provided duration." if not _extract_duration_context(context_history, user_message) else "Duration is known."
        user_prompt = (
            f"{user_message}\n\n"
            f"[Internal context: {triage_info} {duration_context} "
            "Continue the conversation. if symptoms are reported, ask one clarifying question about them. "
            "If it's a general health question, answer it fully.]"
        )
        reply = ask_llm(user_prompt, language=language, history=history)

    return {
        "reply": reply,
        "session_id": session_id,
        "is_diagnosis": is_terminal,
        "diagnosis_data": {"disease": disease, "confidence": round(confidence * 100, 1)} if is_terminal else None,
        "symptoms": all_symptoms,
        "new_symptoms": new_symptoms
    }
