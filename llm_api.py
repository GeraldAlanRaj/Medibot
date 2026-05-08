# import os
# from groq import Groq
# from dotenv import load_dotenv

# # Load .env so GROQ_API_KEY is available
# load_dotenv()

# MEDICAL_SYSTEM_PROMPT = (
#     "You are MediBot AI, a high-performance Medical Assistant. "
#     "Your goal is to assist users with health concerns through two modes:\n"
#     "1. TRIAGE MODE: When a user reports symptoms, ask clarifying questions (one at a time) about duration, severity, and specific details. "
#     "Do not give a final diagnosis immediately unless you have sufficient information. "
#     "2. QA MODE: When a user asks a general health question (e.g., 'What is Malaria?'), provide a detailed, evidence-based answer.\n\n"
#     "CONVERSATION GUIDELINES:\n"
#     "- Maintain a professional, empathetic, and safe tone.\n"
#     "- Structure long answers with sections: Overview, Causes, Symptoms, and Action Plan.\n"
#     "- Use bullet points for readability.\n"
#     "- CRITICAL: Always respond in the user's language.\n"
#     "- SAFETY: Always include a disclaimer that you are an AI, not a doctor."
# )

# def ask_llm(prompt, temperature=0.7, max_tokens=1024, language='en', history=None):
#     api_key = os.getenv('GROQ_API_KEY')
#     if not api_key:
#         return "[GROQ_API_KEY not set in .env]"

#     client = Groq(api_key=api_key)
    
#     language_names = {
#         'en': 'English', 'hi': 'Hindi', 'es': 'Spanish', 'fr': 'French',
#         'de': 'German', 'zh': 'Chinese', 'ja': 'Japanese', 'ar': 'Arabic'
#     }
#     target_lang = language_names.get(language, 'English')

#     # Prepare chat contents
#     messages = []
    
#     # Add System Prompt instructions
#     system_msg = f"{MEDICAL_SYSTEM_PROMPT}\n\nIMPORTANT: Respond entirely in {target_lang}."
#     messages.append({"role": "system", "content": system_msg})
    
#     # Add History if available
#     if history:
#         for msg in history:
#             role = "user" if msg['role'] == 'user' else "assistant"
#             messages.append({"role": role, "content": msg['content']})
            
#     # Add current prompt
#     messages.append({"role": "user", "content": prompt})

#     try:
#         completion = client.chat.completions.create(
#             model="llama-3.3-70b-versatile",
#             messages=messages,
#             temperature=temperature,
#             max_tokens=max_tokens,
#             top_p=1,
#             stream=False, # Keeping sync for now to match current backend flow
#             stop=None
#         )
#         return completion.choices[0].message.content.strip()
#     except Exception as e:
#         print(f"[DEBUG] Groq API error: {e}")
#         return f"[Groq API service encountered an error: {e}]"
# ===============================================================================================================================================================================
# import os
# from dotenv import load_dotenv
# from openai import OpenAI
# from groq import Groq

# # Fix tokenizer warning
# os.environ["TOKENIZERS_PARALLELISM"] = "false"

# # Load environment variables
# load_dotenv()

# # Initialize NVIDIA client (OpenAI-compatible)
# nvidia_client = OpenAI(
#     base_url="https://integrate.api.nvidia.com/v1",
#     api_key=os.getenv("NVIDIA_API_KEY")
# )

# MEDICAL_SYSTEM_PROMPT = (
#     "You are MediBot AI, a high-performance Medical Assistant. "
#     "Your goal is to assist users with health concerns through two modes:\n"
#     "1. TRIAGE MODE: When a user reports symptoms, ask clarifying questions (one at a time) about duration, severity, and specific details. "
#     "Do not give a final diagnosis immediately unless you have sufficient information. "
#     "2. QA MODE: When a user asks a general health question (e.g., 'What is Malaria?'), provide a detailed, evidence-based answer.\n\n"
#     "CONVERSATION GUIDELINES:\n"
#     "- Maintain a professional, empathetic, and safe tone.\n"
#     "- Structure long answers with sections: Overview, Causes, Symptoms, and Action Plan.\n"
#     "- Use bullet points for readability.\n"
#     "- CRITICAL: Always respond in the user's language.\n"
#     "- SAFETY: Always include a disclaimer that you are an AI, not a doctor."
# )

# def ask_llm(prompt, temperature=0.7, max_tokens=1024, language='en', history=None):

#     # Language mapping
#     language_names = {
#         'en': 'English', 'hi': 'Hindi', 'es': 'Spanish', 'fr': 'French',
#         'de': 'German', 'zh': 'Chinese', 'ja': 'Japanese', 'ar': 'Arabic'
#     }
#     target_lang = language_names.get(language, 'English')

#     # Prepare messages
#     messages = []
#     system_msg = f"{MEDICAL_SYSTEM_PROMPT}\n\nIMPORTANT: Respond entirely in {target_lang}."
#     messages.append({"role": "system", "content": system_msg})

#     if history:
#         for msg in history:
#             role = "user" if msg['role'] == 'user' else "assistant"
#             messages.append({"role": role, "content": msg['content']})

#     messages.append({"role": "user", "content": prompt})

#     # =========================
#     # PRIMARY: NVIDIA NEMOTRON
#     # =========================
#     try:
#         if os.getenv("NVIDIA_API_KEY"):
#             completion = nvidia_client.chat.completions.create(
#                 model="nvidia/nemotron-3-super-120b-a12b",
#                 messages=messages,
#                 temperature=temperature,
#                 top_p=0.95,
#                 max_tokens=max_tokens,
#                 stream=False,  # keep sync (important for your backend)
#                 extra_body={
#                     "chat_template_kwargs": {"enable_thinking": True},
#                     "reasoning_budget": max_tokens
#                 }
#             )

#             return completion.choices[0].message.content.strip()

#     except Exception as e:
#         print(f"[DEBUG] NVIDIA Nemotron failed: {e}")

#     # =========================
#     # FALLBACK: GROQ
#     # =========================
#     try:
#         groq_api_key = os.getenv('GROQ_API_KEY')
#         if not groq_api_key:
#             return "[ERROR: No LLM API keys configured]"

#         client = Groq(api_key=groq_api_key)

#         completion = client.chat.completions.create(
#             model="llama-3.3-70b-versatile",
#             messages=messages,
#             temperature=temperature,
#             max_tokens=max_tokens,
#             top_p=1,
#             stream=False
#         )

#         return completion.choices[0].message.content.strip()

#     except Exception as e:
#         print(f"[DEBUG] Groq API error: {e}")
#         return f"[ERROR: All LLM services failed → {e}]"
# ===============================================================================================================================================================================

import os
import requests
from dotenv import load_dotenv
from openai import OpenAI
from groq import Groq

load_dotenv()
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# =========================
# CLIENTS
# =========================

nvidia_client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=os.getenv("NVIDIA_API_KEY")
)

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# =========================
# SYSTEM PROMPT
# =========================

# MEDICAL_SYSTEM_PROMPT = (
#     "You are MediBot AI, a medical assistant. "
#     "Ask follow-up questions before diagnosis. "
#     "Give structured answers. "
#     "Always respond in user's language and include disclaimer."
# )

MEDICAL_SYSTEM_PROMPT = (
    "You are MediBot AI, a high-performance Medical Assistant. "
    "Your goal is to assist users with health concerns through two modes:\n"
    "1. TRIAGE MODE: When a user reports symptoms, ask clarifying questions (one at a time) about duration, severity, and specific details. "
    "Do not give a final diagnosis immediately unless you have sufficient information. "
    "2. QA MODE: When a user asks a general health question (e.g., 'What is Malaria?'), provide a detailed, evidence-based answer.\n\n"
    "CONVERSATION GUIDELINES:\n"
    "- Maintain a professional, empathetic, and safe tone.\n"
    "- Structure long answers with sections: Overview, Causes, Symptoms, and Action Plan.\n"
    "- Use bullet points for readability.\n"
    "- CRITICAL: Always respond in the user's language.\n"
    "- SAFETY: Always include a disclaimer that you are an AI, not a doctor."
)

# =========================
# ROUTER
# =========================

def is_complex_query(prompt: str) -> bool:
    keywords = [
        "diagnose", "disease", "treatment", "severe",
        "chronic", "multiple symptoms", "analysis",
        "what could this be", "medical condition"
    ]
    return any(k in prompt.lower() for k in keywords)

# =========================
# OLLAMA (FIXED)
# =========================

def ask_ollama(messages):
    try:
        # Use CHAT endpoint (important)
        response = requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": "llama3.1:8b",
                "messages": messages,
                "stream": False
            },
            timeout=15   # increased timeout
        )

        data = response.json()

        if "message" in data and "content" in data["message"]:
            return data["message"]["content"].strip()

        elif "error" in data:
            print("[DEBUG] Ollama error:", data["error"])
            return None

        else:
            print("[DEBUG] Unknown Ollama response:", data)
            return None

    except Exception as e:
        print("[DEBUG] Ollama failed:", e)
        return None

# =========================
# NEMOTRON
# =========================

def ask_nemotron(messages, temperature, max_tokens):
    try:
        completion = nvidia_client.chat.completions.create(
            model="nvidia/nemotron-3-super-120b-a12b",
            messages=messages,
            temperature=temperature,
            top_p=0.95,
            max_tokens=max_tokens,
            stream=False,
            extra_body={
                "chat_template_kwargs": {"enable_thinking": True},
                "reasoning_budget": max_tokens
            }
        )
        return completion.choices[0].message.content.strip()

    except Exception as e:
        print("[DEBUG] Nemotron failed:", e)
        return None

# =========================
# GROQ
# =========================

def ask_groq(messages, temperature, max_tokens):
    try:
        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        return completion.choices[0].message.content.strip()

    except Exception as e:
        print("[DEBUG] Groq failed:", e)
        return f"[ERROR: All LLMs failed → {e}]"

# =========================
# MAIN FUNCTION
# =========================

def ask_llm(prompt, temperature=0.7, max_tokens=1024, language='en', history=None):

    language_names = {
        'en': 'English', 'hi': 'Hindi', 'es': 'Spanish', 'fr': 'French',
        'de': 'German', 'zh': 'Chinese', 'ja': 'Japanese', 'ar': 'Arabic'
    }
    target_lang = language_names.get(language, 'English')

    messages = []

    #  Keep system prompt shorter for Ollama speed
    system_msg = f"{MEDICAL_SYSTEM_PROMPT} Respond in {target_lang}."
    messages.append({"role": "system", "content": system_msg})

    #  Limit history (important for speed)
    if history:
        for msg in history[-4:]:   # last 4 messages only
            role = "user" if msg['role'] == 'user' else "assistant"
            messages.append({"role": role, "content": msg['content']})

    messages.append({"role": "user", "content": prompt})

    # =========================
    # TRY OLLAMA FIRST
    # =========================

    if not is_complex_query(prompt):
        print("⚡ Using groq (fast)")
        result = ask_groq(messages, temperature, max_tokens)
        if result:
            return result

    # =========================
    # NEMOTRON
    # =========================

    print("🧠 Using Nemotron (smart)")
    result = ask_nemotron(messages, temperature, max_tokens)
    if result:
        return result

    # =========================
    # GROQ FALLBACK
    # =========================

    print("🛟 Falling back to ollama")
    return ask_ollama(messages)
