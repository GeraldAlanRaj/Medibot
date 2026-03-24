from database import get_session_history
from database import get_doctors
from ml_models import ml_models
from translations import TRANSLATIONS, SYMPTOM_TRANSLATIONS
import json
import re

MAX_FOLLOWUP_ROUNDS = 6
MAX_NEGATIVE_STREAK = 3

def get_translated_symptoms(symptoms, lang):
    if lang not in SYMPTOM_TRANSLATIONS:
        return [s.replace("_", " ") for s in symptoms]
    
    trans_map = SYMPTOM_TRANSLATIONS[lang]
    # Check if we have a translation, otherwise fallback to space-separated English
    return [trans_map.get(s, s.replace("_", " ")) for s in symptoms]

def _looks_like_medical_query(text, user_words):
    text = (text or '').lower()
    medical_terms = [
        'symptom', 'disease', 'treatment', 'medicine', 'tablet', 'diagnosis',
        'fever', 'cough', 'pain', 'infection', 'allergy', 'viral', 'bacterial',
        'doctor', 'hospital', 'remedy', 'dose', 'side effect', 'what should i do'
    ]
    return ('?' in text) or any(term in text for term in medical_terms) or any(w in user_words for w in ['what', 'how', 'why'])

def _format_prediction_response(t, translated_symptoms, disease, confidence_pct, language):
    if language != 'en':
        return t["prediction"].format(
            symptoms=", ".join(translated_symptoms),
            disease=disease,
            confidence=confidence_pct
        )

    return (
        f"Here is my current assessment:\n"
        f"- Most likely condition: **{disease}**\n"
        f"- Confidence: **{confidence_pct}%**\n"
        f"- Symptoms considered: {', '.join(translated_symptoms)}\n\n"
        "What to do now:\n"
        "- Rest, hydrate, and monitor symptom progression over the next 24-48 hours.\n"
        "- Share severity and any worsening signs so I can refine the recommendation.\n\n"
        "Safety note: I am an AI assistant, not a doctor. For severe or worsening symptoms, consult a clinician promptly."
    )

def _format_guarded_response(t, disease, confidence_pct, translated_symptoms, language):
    if language != 'en':
        return t.get(
            'guarded_match',
            "Current best match based on available information is **{disease}** (confidence: {confidence}%). This is not final yet.\n\nTracked symptoms: {symptoms}.\nPlease continue sharing symptom progression for a safer conclusion."
        ).format(
            disease=disease,
            confidence=confidence_pct,
            symptoms=', '.join(translated_symptoms)
        )

    return (
        f"Current best match from available evidence: **{disease}** ({confidence_pct}% confidence).\n\n"
        f"Tracked symptoms: {', '.join(translated_symptoms)}.\n"
        "This is a provisional assessment, not a confirmed diagnosis.\n\n"
        "To improve accuracy, share:\n"
        "- Symptom severity (mild/moderate/severe)\n"
        "- Timing pattern (constant/intermittent/worse at night)\n"
        "- Any red-flag changes (breathlessness, chest pain, confusion, dehydration)"
    )


def _has_duration_info(text):
    text = (text or '').lower()
    if not text:
        return False
    if re.search(r'\b\d+\s*(day|days|week|weeks|month|months|hour|hours)\b', text):
        return True
    duration_words = [
        'today', 'yesterday', 'since', 'for', 'couple of days', 'few days',
        'few weeks', 'from morning', 'from last', 'last night', 'since morning',
        'din', 'desde', 'depuis', 'seit'
    ]
    return any(word in text for word in duration_words)


def _extract_duration_context(history, user_message):
    if _has_duration_info(user_message):
        return True
    for msg in reversed(history):
        if msg.get('role') == 'user' and _has_duration_info(msg.get('content', '')):
            return True
    return False


def _is_followup_prompt(content):
    lower = (content or '').lower()
    markers = [
        'do you also experience',
        'experience any of these',
        'do you have any of these',
        'since those are not present'
    ]
    return any(marker in lower for marker in markers)


def _count_followup_rounds(history):
    return sum(1 for msg in history if msg.get('role') == 'agent' and _is_followup_prompt(msg.get('content', '')))


def _last_agent_was_followup(history):
    last_agent = next((msg for msg in reversed(history) if msg.get('role') == 'agent'), None)
    if not last_agent:
        return False
    return _is_followup_prompt(last_agent.get('content', ''))


def _last_agent_was_terminal_assessment(history):
    last_agent = next((msg for msg in reversed(history) if msg.get('role') == 'agent'), None)
    if not last_agent:
        return False
    content = (last_agent.get('content') or '').lower()
    terminal_markers = [
        'current best match',
        'predicted diagnosis',
        'recommended specialist',
        'please consult a healthcare professional'
    ]
    return any(marker in content for marker in terminal_markers)


def _is_new_symptom_statement(text, extracted_symptoms):
    text = (text or '').strip().lower()
    if not extracted_symptoms or _is_continuation_turn(text):
        return False
    starters = [
        'i have', 'i am having', 'i\'ve been having', 'my symptoms',
        'suffering from', 'i got', 'i feel'
    ]
    return any(text.startswith(prefix) for prefix in starters)


def _last_user_had_no_symptoms(history):
    for msg in reversed(history):
        if msg.get('role') == 'user':
            return not bool(msg.get('extracted_symptoms'))
    return False


def _last_agent_is_reset_anchor(history):
    last_agent = next((msg for msg in reversed(history) if msg.get('role') == 'agent'), None)
    if not last_agent:
        return False
    content = (last_agent.get('content') or '').lower()
    markers = [
        'how can i help you today',
        'how can i assist you today',
        'you can describe your symptoms to me',
        'i can help in two ways'
    ]
    return any(marker in content for marker in markers)


def _is_continuation_turn(text):
    text = (text or '').strip().lower()
    if not text:
        return False

    # Short confirmations/continuations should keep prior context.
    words = text.split()
    if len(words) <= 3 and any(w in words for w in ['yes', 'no', 'haan', 'nahi', 'yep', 'nope', 'nah']):
        return True

    continuation_prefixes = [
        'and ', 'also ', 'plus ', 'still ', 'same ', 'again ',
        'since ', 'for ', 'from ', 'yes', 'no', 'haan', 'nahi'
    ]
    return any(text.startswith(prefix) for prefix in continuation_prefixes)


def _get_current_context_history(history):
    """
    Keep only the latest coherent symptom episode so older complaints
    (e.g., last week fever) do not pollute a fresh complaint.
    """
    if not history:
        return []

    def _user_message_follows_agent_followup(user_idx):
        for j in range(user_idx - 1, -1, -1):
            role = history[j].get('role')
            if role == 'agent':
                return _is_followup_prompt(history[j].get('content', ''))
            if role == 'user':
                return False
        return False

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

        if (
            context_symptoms.intersection(msg_symptoms)
            or _is_continuation_turn(msg.get('content', ''))
            or _user_message_follows_agent_followup(idx)
        ):
            context_symptoms.update(msg_symptoms)
        else:
            # New disjoint complaint started here.
            context_start = idx
            context_symptoms = set(msg_symptoms)

    return history[context_start:]


def _extract_asked_followups(history):
    asked = set()
    followup_markers = [
        'do you also experience',
        'experience any of these',
        'do you have any of these',
        'since those are not present'
    ]
    for msg in history:
        if msg.get('role') != 'agent':
            continue
        content = msg.get('content', '')
        lower = content.lower()
        candidate_segments = []

        # Most follow-up templates place candidate symptoms after a ':' and end with '?'.
        if ':' in content and '?' in content:
            candidate_segments.append(content.split(':', 1)[1])

        # Fallback for legacy templates.
        if any(marker in lower for marker in followup_markers):
            candidate_segments.append(content)

        for segment in candidate_segments:
            asked.update(ml_models.extract_symptoms(segment))
    return asked


def _count_negative_streak(history, negatives_set):
    streak = 0
    for msg in reversed(history):
        if msg.get('role') != 'user':
            continue
        words = set((msg.get('content') or '').lower().strip().split())
        if any(word in words for word in negatives_set):
            streak += 1
        else:
            break
    return streak


def _recommend_specialty(disease):
    disease_lower = (disease or '').lower()

    if disease_lower.strip() in ('allergy', 'common cold'):
        return 'General Physician'

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


def _doctor_recommendations(disease, t=None):
    doctors = get_doctors()
    if not doctors:
        return ''

    specialty = _recommend_specialty(disease)
    matched = [d for d in doctors if specialty.lower() in (d.get('specialty') or '').lower()]
    candidates = matched if matched else sorted(doctors, key=lambda d: d.get('rating') or 0, reverse=True)
    top = candidates[:3]
    if not top:
        return ''

    doctor_lines = [f"- {d.get('name')} ({d.get('specialty')}, {d.get('location')})" for d in top]
    t = t or {}
    specialist_line = t.get('recommended_specialist_line', 'Recommended specialist: **{specialty}**.').format(specialty=specialty)
    doctors_line = t.get('doctors_you_can_book_now', 'Doctors you can book now:')
    return (
        f"\n\n{specialist_line}\n"
        f"{doctors_line}\n" + "\n".join(doctor_lines)
    )

def handle_user_input(session_id, user_message, language="en"):
    # Ensure language is valid
    if language not in TRANSLATIONS:
        language = "en"
    
    t = TRANSLATIONS[language]
    history = get_session_history(session_id)
    context_history = _get_current_context_history(history)
    asked_followups = _extract_asked_followups(history)
    
    # Extract symptoms from current message
    new_symptoms = ml_models.extract_symptoms(user_message)

    # Build running symptoms only from current context history.
    context_symptoms = set()
    for msg in context_history:
        if msg.get('extracted_symptoms'):
            context_symptoms.update(msg['extracted_symptoms'])

    # If user provides a disjoint new symptom sentence, start a new context immediately.
    should_reset_context = False
    if new_symptoms and context_symptoms and not _last_agent_was_followup(context_history):
        if set(new_symptoms).isdisjoint(context_symptoms) and not _is_continuation_turn(user_message):
            should_reset_context = True
        elif _last_agent_was_terminal_assessment(context_history) and _is_new_symptom_statement(user_message, new_symptoms):
            should_reset_context = True
        elif _is_new_symptom_statement(user_message, new_symptoms) and _last_user_had_no_symptoms(history):
            # Common UX path: user says greeting/chit-chat, then starts a fresh symptom complaint.
            # Reset episode so old stored symptoms do not pollute this triage.
            should_reset_context = True
        elif _is_new_symptom_statement(user_message, new_symptoms) and _last_agent_is_reset_anchor(history):
            # Strong reset anchor: greeting/onboarding/fallback prompt implies a fresh complaint start.
            should_reset_context = True

    if should_reset_context:
        all_symptoms = list(set(new_symptoms))
        context_history = []
    else:
        all_symptoms = list(context_symptoms.union(set(new_symptoms)))

    user_message_lower = user_message.lower().strip()
    user_words = set(user_message_lower.split())
    duration_known = _extract_duration_context(context_history, user_message)
    asked_followups = _extract_asked_followups(context_history)

    # 1. Handle Greetings
    greetings = ["hi", "hello", "hey", "good morning", "good afternoon", "greetings", "नमस्ते", "hola", "bonjour", "hallo"]
    if any(greet in user_words for greet in greetings) and not new_symptoms:
        return {
            "reply": t["greeting"],
            "session_id": session_id,
            "is_diagnosis": False,
            "symptoms": all_symptoms,
            "new_symptoms": new_symptoms
        }

    # 2. Check for Red Flags
    severe_text_triggers = [
        'severe chest pain', 'can\'t breathe', 'cannot breathe', 'fainted',
        'blood in vomit', 'blood in stool', 'unconscious', 'suicidal'
    ]
    if ml_models.check_red_flags(new_symptoms) or any(s in user_message_lower for s in severe_text_triggers):
        return {
            "reply": t["emergency"],
            "session_id": session_id,
            "is_diagnosis": False,
            "symptoms": all_symptoms,
            "new_symptoms": new_symptoms
        }
        
    # 3. Determine Intent: Question vs Symptom Checking
    question_words = ["what", "how", "why", "is", "can", "cure", "treatment", "medicine", "tell", "about", "क्या", "qué", "comment", "wie"]
    
    # Use word matching to avoid substring false positives (e.g., 'is' in 'yes')
    is_question = ('?' in user_message_lower) or any(q in user_words for q in question_words)
    is_medical_query = _looks_like_medical_query(user_message_lower, user_words)
    
    # Handle affirmative and negative responses in multiple languages.
    affirmatives = ["yes", "yeah", "yep", "ha", "haan", "जी", "sí", "oui", "ja", "correct"]
    negatives = ["no", "nope", "nah", "nahi", "नहीं", "na", "non", "nein"]
    negatives_set = set(negatives)
    # Treat yes/no as control replies only when message is short and doesn't add new symptoms.
    is_affirmative = (not new_symptoms) and (len(user_words) <= 4) and any(word in user_words for word in affirmatives)
    is_negative = (not new_symptoms) and (len(user_words) <= 4) and any(word in user_words for word in negatives)
    followup_rounds = _count_followup_rounds(context_history)
    negative_streak = _count_negative_streak(context_history, negatives_set) + (1 if is_negative else 0)
    
    if is_affirmative:
        # Check if the last bot message was a clarifying question
        last_bot_msg = next((msg['content'] for msg in reversed(context_history) if msg['role'] == 'agent'), None)
        if last_bot_msg and ("do you also experience" in last_bot_msg.lower() or "experience any of these" in last_bot_msg.lower()):
            # Find symptoms mentioned in the last bot message
            potential_symptoms = ml_models.extract_symptoms(last_bot_msg)
            if potential_symptoms:
                new_symptoms = list(set(new_symptoms + potential_symptoms))
                all_symptoms = list(set(all_symptoms + potential_symptoms))
                print(f"DEBUG: Affirmative response detected. Added symptoms: {potential_symptoms}")

    if is_negative and all_symptoms:
        if duration_known and (followup_rounds >= MAX_FOLLOWUP_ROUNDS or negative_streak >= MAX_NEGATIVE_STREAK):
            disease, confidence = ml_models.predict_disease(all_symptoms)
            confidence_pct = round(confidence * 100, 1)
            translated_symptoms = get_translated_symptoms(all_symptoms, language)

            if confidence >= 0.8:
                response_text = _format_prediction_response(
                    t,
                    translated_symptoms,
                    disease,
                    confidence_pct,
                    language
                )
                response_text += _doctor_recommendations(disease, t=t)
                return {
                    "reply": response_text,
                    "session_id": session_id,
                    "is_diagnosis": True,
                    "diagnosis_data": {"disease": disease, "confidence": confidence_pct},
                    "symptoms": all_symptoms,
                    "new_symptoms": []
                }

            response_text = _format_guarded_response(
                t,
                disease,
                confidence_pct,
                translated_symptoms,
                language
            )
            response_text += _doctor_recommendations(disease, t=t)
            return {
                "reply": response_text,
                "session_id": session_id,
                "is_diagnosis": False,
                "diagnosis_data": {"disease": disease, "confidence": confidence_pct},
                "symptoms": all_symptoms,
                "new_symptoms": []
            }

        follow_ups = ml_models.get_relevant_followups(
            all_symptoms,
            user_message=user_message,
            excluded_symptoms=asked_followups
        )
        remaining = [f for f in follow_ups if f not in all_symptoms and f not in asked_followups][:2]
        if remaining:
            translated_remaining = get_translated_symptoms(remaining, language)
            return {
                "reply": t.get(
                    'negative_followup',
                    "Thanks for confirming. Since those are not present, do you have any of these: {follow_ups}?"
                ).format(follow_ups=', '.join(translated_remaining)),
                "session_id": session_id,
                "is_diagnosis": False,
                "symptoms": all_symptoms,
                "new_symptoms": []
            }
        if not duration_known:
            return {
                "reply": t.get(
                    'duration_prompt',
                    "To improve accuracy, please tell me the duration of these symptoms (for example: 2 days, 1 week)."
                ),
                "session_id": session_id,
                "is_diagnosis": False,
                "symptoms": all_symptoms,
                "new_symptoms": []
            }
        return {
            "reply": t.get(
                'more_details_prompt',
                "Thanks. Please share any additional symptom details (severity, timing, triggers) so I can improve the assessment."
            ),
            "session_id": session_id,
            "is_diagnosis": False,
            "symptoms": all_symptoms,
            "new_symptoms": []
        }

    # If it looks like a question or specific medical query, prioritize RAG answering
    if is_medical_query and len(user_message.split()) >= 3 and not is_affirmative and not is_negative and not new_symptoms and not all_symptoms:
        answer = ml_models.rag_answer(user_message, language=language)
        if answer and len(answer) > 30:
            return {
                "reply": answer,
                "session_id": session_id,
                "is_diagnosis": False,
                "symptoms": all_symptoms,
                "new_symptoms": new_symptoms
            }
        
    # 4. Fallback if no symptoms found
    if not all_symptoms:
        if len(user_message.split()) >= 2:
            return {
                "reply": t.get(
                    'triage_or_qa_prompt',
                    "I can help in two ways:\n"
                    "- Symptom triage: tell me your symptoms + duration\n"
                    "- Medical Q&A: ask any health question and I will answer with evidence when available\n\n"
                    "Example: 'I have sore throat and fever for 3 days'"
                ),
                "session_id": session_id,
                "is_diagnosis": False,
                "symptoms": [],
                "new_symptoms": []
            }
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
        
    # Require symptom duration before diagnosis for safer assessments.
    if not duration_known:
        return {
            "reply": t.get(
                'duration_prompt',
                "To improve accuracy, please tell me the duration of these symptoms (for example: since yesterday, 3 days, or 2 weeks)."
            ),
            "session_id": session_id,
            "is_diagnosis": False,
            "symptoms": all_symptoms,
            "new_symptoms": new_symptoms
        }

    # Prefer deeper investigation before generating diagnosis.
    if len(all_symptoms) < 3:
        follow_ups = ml_models.get_relevant_followups(
            all_symptoms,
            user_message=user_message,
            excluded_symptoms=asked_followups
        )
        follow_ups = [f for f in follow_ups if f not in all_symptoms]
        translated_symptoms = get_translated_symptoms(all_symptoms, language)
        translated_follow_ups = get_translated_symptoms(follow_ups, language)
        return {
            "reply": t["clarifying"].format(
                symptoms=", ".join(translated_symptoms),
                follow_ups=", ".join(translated_follow_ups)
            ),
            "session_id": session_id,
            "is_diagnosis": False,
            "symptoms": all_symptoms,
            "new_symptoms": new_symptoms
        }

    # Diagnosis Logic
    disease, confidence = ml_models.predict_disease(all_symptoms)
    confidence_pct = round(confidence * 100, 1)

    # 5. HIGH CONFIDENCE BRANCH: diagnose only when investigation is sufficient.
    if confidence >= 0.8:
        translated_symptoms = get_translated_symptoms(all_symptoms, language)
        response_text = _format_prediction_response(
            t,
            translated_symptoms,
            disease,
            confidence_pct,
            language
        )
        response_text += _doctor_recommendations(disease, t=t)
        return {
            "reply": response_text,
            "session_id": session_id,
            "is_diagnosis": True,
            "diagnosis_data": {"disease": disease, "confidence": confidence_pct},
            "symptoms": all_symptoms,
            "new_symptoms": new_symptoms
        }

    # 6. LOW CONFIDENCE BRANCH: ask for more evidence.
    follow_ups = ml_models.get_relevant_followups(
        all_symptoms,
        user_message=user_message,
        excluded_symptoms=asked_followups
    )
    follow_ups = [f for f in follow_ups if f not in all_symptoms]
    if follow_ups:
        # Check if the user's latest input was redundant
        existing_symptoms = set()
        for msg in context_history:
            if msg.get('extracted_symptoms'):
                existing_symptoms.update(msg['extracted_symptoms'])
        
        is_new_info = any(s for s in new_symptoms if s not in existing_symptoms)
        
        # If it was redundant AND we are not diagnosing/confirming yet, warn user.
        if not is_new_info and not is_affirmative and not is_question and not _has_duration_info(user_message):
            if new_symptoms:
                reply = t.get(
                    'details_recorded_prompt',
                    "I've added those details. Is there anything else you'd like to share? Currently tracking: {symptoms}."
                ).format(symptoms=', '.join(get_translated_symptoms(all_symptoms, language)))
            else:
                reply = t["fallback"].format(user_message=user_message)
                reply += " " + t.get(
                    'tracking_note',
                    "I'm still keeping track of: {symptoms}."
                ).format(symptoms=', '.join(get_translated_symptoms(all_symptoms, language)))

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
        response_text += "\n\n" + t.get(
            'severity_prompt',
            'Please also include symptom severity (mild/moderate/severe).'
        )
        return {
            "reply": response_text,
            "session_id": session_id,
            "is_diagnosis": False,
            "symptoms": all_symptoms,
            "new_symptoms": new_symptoms
        }

    # 7. EXHAUSTED BRANCH: avoid overconfident output; provide guarded best guess.
    translated_symptoms = get_translated_symptoms(all_symptoms, language)
    response_text = _format_guarded_response(
        t,
        disease,
        confidence_pct,
        translated_symptoms,
        language
    )
    response_text += _doctor_recommendations(disease, t=t)

    return {
        "reply": response_text,
        "session_id": session_id,
        "is_diagnosis": False,
        "diagnosis_data": {"disease": disease, "confidence": confidence_pct},
        "symptoms": all_symptoms,
        "new_symptoms": new_symptoms
    }
