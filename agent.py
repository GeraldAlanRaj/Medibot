from database import get_session_history
from ml_models import ml_models
from translations import TRANSLATIONS, SYMPTOM_TRANSLATIONS
import json

def get_translated_symptoms(symptoms, lang):
    if lang not in SYMPTOM_TRANSLATIONS:
        return [s.replace("_", " ") for s in symptoms]
    
    trans_map = SYMPTOM_TRANSLATIONS[lang]
    # Check if we have a translation, otherwise fallback to space-separated English
    return [trans_map.get(s, s.replace("_", " ")) for s in symptoms]

def handle_user_input(session_id, user_message, language="en"):
    # Ensure language is valid
    if language not in TRANSLATIONS:
        language = "en"
    
    t = TRANSLATIONS[language]
    history = get_session_history(session_id)
    
    # Extract symptoms from current message
    new_symptoms = ml_models.extract_symptoms(user_message)

    
    # Accumulate symptoms using history
    all_symptoms = set(new_symptoms)
    for msg in history:
        if msg.get('extracted_symptoms'):
            all_symptoms.update(msg['extracted_symptoms'])
            
    all_symptoms = list(all_symptoms)

    
    # 1. Handle Greetings
    greetings = ["hi", "hello", "hey", "good morning", "good afternoon", "greetings", "नमस्ते", "hola", "bonjour", "hallo"]
    if any(greet in user_message.lower().strip().split() for greet in greetings) and not new_symptoms:
        return {
            "reply": t["greeting"],
            "session_id": session_id,
            "is_diagnosis": False,
            "symptoms": all_symptoms,
            "new_symptoms": new_symptoms
        }

    # 2. Check for Red Flags
    if ml_models.check_red_flags(new_symptoms):
        return {
            "reply": t["emergency"],
            "session_id": session_id,
            "is_diagnosis": False,
            "symptoms": all_symptoms,
            "new_symptoms": new_symptoms
        }
        
    # 3. Determine Intent: Question vs Symptom Checking
    question_words = ["what", "how", "why", "is", "can", "cure", "treatment", "medicine", "tell me about", "क्या", "qué", "comment", "wie"]
    user_message_lower = user_message.lower().strip()
    user_words = set(user_message_lower.split())
    
    # Use word matching to avoid substring false positives (e.g., 'is' in 'yes')
    is_question = any(q in user_words for q in question_words)
    
    # Handle affirmative responses (e.g., "yes", "yeah")
    affirmatives = ["yes", "yeah", "yep", "ha", "haan", "जी", "sí", "oui", "ja"]
    is_affirmative = any(word in user_words for word in affirmatives)
    
    if is_affirmative:
        # Check if the last bot message was a clarifying question
        last_bot_msg = next((msg['content'] for msg in reversed(history) if msg['role'] == 'agent'), None)
        if last_bot_msg and ("do you also experience" in last_bot_msg.lower() or "experience any of these" in last_bot_msg.lower()):
            # Find symptoms mentioned in the last bot message
            potential_symptoms = ml_models.extract_symptoms(last_bot_msg)
            if potential_symptoms:
                new_symptoms = list(set(new_symptoms + potential_symptoms))
                all_symptoms = list(set(all_symptoms + potential_symptoms))
                print(f"DEBUG: Affirmative response detected. Added symptoms: {potential_symptoms}")

    # If it looks like a question or specific medical query, prioritize RAG answering
    if is_question and len(user_message.split()) >= 3 and not is_affirmative:
        answer = ml_models.rag_answer(user_message)
        if "Based on medical knowledge:" in answer and len(answer) > 30:
            return {
                "reply": answer,
                "session_id": session_id,
                "is_diagnosis": False,
                "symptoms": all_symptoms,
                "new_symptoms": new_symptoms
            }
        
    # 4. Fallback if no symptoms found
    if not all_symptoms:
        # Check if it was a greeting we missed or just short noise
        if len(user_message.split()) < 2:
             return {
                "reply": t["greeting"],
                "session_id": session_id,
                "is_diagnosis": False,
                "symptoms": [],
                "new_symptoms": []
            }
        return {
            "reply": t["fallback"].format(user_message=user_message),
            "session_id": session_id,
            "is_diagnosis": False,
            "symptoms": [],
            "new_symptoms": []
        }
        
    # Diagnosis Logic
    disease, confidence = ml_models.predict_disease(all_symptoms)
    confidence_pct = round(confidence * 100, 1)

    # 5. HIGH CONFIDENCE BRANCH: If we know the answer, give it immediately.
    # This prevents the bot from getting stuck if a user repeats a symptom.
    if confidence >= 0.7:
        translated_symptoms = get_translated_symptoms(all_symptoms, language)
        response_text = t["prediction"].format(
            symptoms=", ".join(translated_symptoms),
            disease=disease,
            confidence=confidence_pct
        )
        return {
            "reply": response_text,
            "session_id": session_id,
            "is_diagnosis": True,
            "diagnosis_data": {"disease": disease, "confidence": confidence_pct},
            "symptoms": all_symptoms,
            "new_symptoms": new_symptoms
        }

    # 6. LOW CONFIDENCE BRANCH: Try to ask more or force a diagnosis if no questions left.
    follow_ups = ml_models.get_relevant_followups(all_symptoms)
    if follow_ups:
        # Check if the user's latest input was redundant
        existing_symptoms = set()
        for msg in history:
            if msg.get('extracted_symptoms'):
                existing_symptoms.update(msg['extracted_symptoms'])
        
        is_new_info = any(s for s in new_symptoms if s not in existing_symptoms)
        
        # If it was redundant AND we are not diagnosing/confirming yet, warn user.
        if not is_new_info and not is_affirmative and not is_question:
             if new_symptoms:
                  reply = f"I've added those details to your records. Is there anything else you'd like to share, or any other symptoms you've noticed? (Currently tracking: {', '.join(get_translated_symptoms(all_symptoms, language))})"
             else:
                  reply = t["fallback"].format(user_message=user_message) + f" (I'm still keeping track of: {', '.join(get_translated_symptoms(all_symptoms, language))})"
             
             return {
                "reply": reply,
                "session_id": session_id,
                "is_diagnosis": False,
                "symptoms": all_symptoms,
                "new_symptoms": []
            }

        # Otherwise, ask follow-ups
        translated_symptoms = get_translated_symptoms(all_symptoms, language)
        translated_follow_ups = get_translated_symptoms(follow_ups, language)
        
        response_text = t["clarifying"].format(
            symptoms=", ".join(translated_symptoms),
            follow_ups=", ".join(translated_follow_ups)
        )
        return {
            "reply": response_text,
            "session_id": session_id,
            "is_diagnosis": False,
            "symptoms": all_symptoms,
            "new_symptoms": new_symptoms
        }

    # 7. EXHAUSTED BRANCH: We have low confidence but NO more questions. 
    # Provide the best guess regardless of confidence.
    translated_symptoms = get_translated_symptoms(all_symptoms, language)
    response_text = t["prediction"].format(
        symptoms=", ".join(translated_symptoms),
        disease=disease,
        confidence=confidence_pct
    )
    
    return {
        "reply": response_text,
        "session_id": session_id,
        "is_diagnosis": True,
        "diagnosis_data": {"disease": disease, "confidence": confidence_pct},
        "symptoms": all_symptoms,
        "new_symptoms": new_symptoms
    }
