import os
import json
import pickle
import re
import requests # pyre-ignore[21]
import numpy as np # pyre-ignore[21]
import pandas as pd # pyre-ignore[21]
import spacy # pyre-ignore[21]
from sklearn.ensemble import RandomForestClassifier # pyre-ignore[21]
from langchain_community.vectorstores import FAISS # pyre-ignore[21]
from langchain_huggingface import HuggingFaceEmbeddings # pyre-ignore[21]
from langchain_core.documents import Document # pyre-ignore[21]
from transformers import pipeline # pyre-ignore[21]
from llm_api import ask_llm

class MLModels:
    def __init__(self):
        self.data_path = os.path.join(os.path.dirname(__file__), "data", "Training.csv")
        self.model_path = "rf_model_real.pkl"
        self.models_cache = os.path.join(os.getcwd(), "models")
        
        if not os.path.exists(self.models_cache):
            os.makedirs(self.models_cache)
            
        # Load symptoms from CSV header
        df_cols = pd.read_csv(self.data_path, nrows=0).columns.tolist()
        self.symptoms_list = [c for c in df_cols if c != 'prognosis' and not c.startswith('Unnamed')]
        self.training_df = self._load_training_df()
        
        self.red_flag_symptoms = ["chest pain", "chest_pain", "shortness of breath", "breathlessness", "severe bleeding", "loss of consciousness"]
        self.red_flag_symptoms.extend([
            "vomiting blood", "blood in stool", "severe dehydration", "stroke", "seizure"
        ])
        
        # Mapping for common Hindi/other keywords to English symptom names
        self.cross_lang_map = {
            "सिरदर्द": "headache",
            "बुखार": "high_fever",
            "जुकाम": "continuous_sneezing",
            "छींक": "continuous_sneezing",
            "cold": "continuous_sneezing",
            "itching": "itching",
            "khujli": "itching",
            "खांसी": "cough",
            "दर्द": "muscle_pain",
            "जोड़ों में दर्द": "joint_pain",
            "थकान": "fatigue",
            "उल्टी": "vomiting",
            "जी मिचलाना": "nausea",
            "दस्त": "diarrhoea",
            "सांस लेने में तकलीफ": "breathlessness",
            "सीने में दर्द": "chest_pain",
            "खुजली": "itching",
            "चक्कर": "dizziness",
            "fever": "high_fever",
            "fiebre": "high_fever",
            "dolor de cabeza": "headache",
            "tos": "cough",
            "fatiga": "fatigue",
            "fièvre": "high_fever",
            "maux de tête": "headache",
            "schwindel": "dizziness",
            "müdigkeit": "fatigue"
        }

        # Never ask these in routine follow-ups unless user context clearly indicates sexual-risk triage.
        self.sensitive_followup_symptoms = {
            "extra_marital_contacts",
            "patches_in_throat",
            "muscle_wasting"
        }

        self.safe_generic_followups = [
            "chills",
            "cough",
            "nausea",
            "vomiting",
            "fatigue",
            "loss_of_appetite",
            "joint_pain",
            "stomach_pain",
            "mild_fever"
        ]

        self.non_clinical_followup_symptoms = {
            "family_history"
        }

        self.use_ollama = os.getenv('USE_OLLAMA', '1').lower() in ('1', 'true', 'yes')
        self.ollama_url = os.getenv('OLLAMA_URL', 'http://127.0.0.1:11434')
        self.ollama_model = os.getenv('OLLAMA_MODEL', 'llama3.1:8b')
        
        # Load Spacy
        self.nlp = self._setup_spacy()
            
        # RAG Setup
        print("Loading embeddings model...")
        self.embeddings = HuggingFaceEmbeddings(
            model_name="all-MiniLM-L6-v2",
            cache_folder=os.path.join(self.models_cache, "embeddings")
        )
        self.vector_store = self._init_rag()
        
        # T5 for QA Setup
        print("Loading T5 model for QA...")
        try:
            self.qa_pipeline = pipeline(
                "text2text-generation", 
                model="t5-small",
                model_kwargs={"cache_dir": os.path.join(self.models_cache, "transformers")}
            )
        except (KeyError, ValueError):
            print("Warning: Explicit 'text2text-generation' task failed. Attempting task inference...")
            self.qa_pipeline = pipeline(
                model="t5-small",
                model_kwargs={"cache_dir": os.path.join(self.models_cache, "transformers")}
            )
        
        # Diagnosis Model Setup
        self.rf_model = self._init_rf_model()

    def _setup_spacy(self):
        try:
            return spacy.load("en_core_web_sm")
        except Exception:
            import subprocess
            import sys
            print("Downloading SpaCy model 'en_core_web_sm'...")
            subprocess.run([sys.executable, "-m", "spacy", "download", "en_core_web_sm"])
            return spacy.load("en_core_web_sm")

    def _load_training_df(self):
        df = pd.read_csv(self.data_path)
        if 'Unnamed: 133' in df.columns:
            df = df.drop('Unnamed: 133', axis=1)
        return df

    def _init_rag(self):
        faiss_index_path = os.path.join(self.models_cache, "faiss_index")
        
        if os.path.exists(faiss_index_path):
            print("Loading existing FAISS Vector Database...")
            try:
                return FAISS.load_local(
                    faiss_index_path, 
                    self.embeddings, 
                    allow_dangerous_deserialization=False
                )
            except Exception as e:
                print(f"Failed to load existing FAISS index: {e}. Rebuilding...")
                
        print("Building new FAISS Vector Database from documents...")
        doc_path = os.path.join(os.path.dirname(__file__), "data", "documents")
        
        if not os.path.exists(doc_path):
            os.makedirs(doc_path)
            
        from langchain_community.document_loaders import DirectoryLoader, TextLoader # pyre-ignore[21]
        from langchain_text_splitters import RecursiveCharacterTextSplitter # pyre-ignore[21]
        
        loader = DirectoryLoader(doc_path, glob="**/*.txt", loader_cls=TextLoader)
        documents = loader.load()
        
        if not documents:
            print("No documents found to build RAG database. Using fallback.")
            documents = [Document(page_content="Fever is treated with rest and acetaminophen.")]
            
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
        chunks = text_splitter.split_documents(documents)
        
        vector_store = FAISS.from_documents(chunks, self.embeddings)
        try:
            vector_store.save_local(faiss_index_path)
            print("Successfully saved FAISS Vector Database.")
        except Exception as e:
            print(f"Warning: Failed to save FAISS index: {e}")
            
        return vector_store

    def _init_rf_model(self):
        if os.path.exists(self.model_path):
            with open(self.model_path, 'rb') as f:
                return pickle.load(f)
        else:
            print("Training Random Forest model on real dataset...")
            # Ensure training data exactly matches the symptoms_list feature set
            X = self.training_df[self.symptoms_list]
            y = self.training_df['prognosis']
            
            clf = RandomForestClassifier(n_estimators=100, random_state=42)
            clf.fit(X, y)
            
            with open(self.model_path, 'wb') as f:
                pickle.dump(clf, f)
            return clf

    def extract_symptoms_llm(self, text, language='en'):
        """
        Uses Gemini to extract symptoms from natural language and map them 
        to the internal English symptom keys.
        """
        prompt = (
            f"Extract medical symptoms from the following text: \"{text}\"\n"
            f"Map them to the most relevant symptoms from this list: {', '.join(self.symptoms_list)}\n"
            f"Return ONLY a comma-separated list of the relevant English keys. If none match, return 'none'."
        )
        
        try:
            result = ask_llm(prompt, language=language)
            if not result or result.lower() == 'none' or result.startswith('['):
                return []
            
            # Parse comma-separated keys
            extracted = [s.strip().lower() for s in result.split(',')]
            # Validate against symptoms_list
            valid = [s for s in extracted if s in self.symptoms_list]
            return valid
        except Exception as e:
            print(f"[DEBUG] LLM Extraction error: {e}")
            return []

    def extract_symptoms(self, text, language='en'):
        # Fallback to LLM extraction for non-English or complex sentences
        if language != 'en' or len(text.split()) > 3:
            llm_symptoms = self.extract_symptoms_llm(text, language=language)
            if llm_symptoms:
                return llm_symptoms

        text_lower = text.lower().replace("_", " ")
        extracted = []
        
        # 0. Quick common typo/shorthand mapping
        phrase_map = {
            "chest pain": "chest_pain",
            "shortness of breath": "breathlessness",
            "loose motion": "diarrhoea",
            "loose stools": "diarrhoea",
            "sore throat": "throat_irritation",
            "joint pain": "joint_pain",
            "muscle pain": "muscle_pain",
            "body ache": "joint_pain",
            "body pain": "joint_pain",
            "back pain": "back_pain",
            "stomach pain": "stomach_pain",
            "mild fever": "mild_fever",
            "high fever": "high_fever",
        }
        for phrase, correct in phrase_map.items():
            if str(phrase) in str(text_lower):
                text_lower = str(text_lower).replace(str(phrase), str(correct))
        
        word_map = {
            "vomating": "vomiting",
            "vommit": "vomiting",
            "vomat": "vomiting",
            "sneezing": "continuous_sneezing",
            "sneeze": "continuous_sneezing",
            "cold": "continuous_sneezing",
            "headach": "headache",
            "fever": "high_fever",
        }
        for typo, correct in word_map.items():
            if typo == "fever" and ("mild_fever" in str(text_lower) or "high_fever" in str(text_lower)):
                continue
            if str(typo) in str(text_lower) and str(correct) not in str(text_lower):
                text_lower = str(text_lower).replace(str(typo), str(correct))

        normalized_text = re.sub(r"\s+", " ", text_lower.replace("_", " ")).strip()

        def is_negated(surface_form):
            if re.search(rf"\b(?:but|however)\s+{re.escape(surface_form)}\b", normalized_text):
                return False
            neg_patterns = [
                rf"\b(?:no|not|without|denies|deny|never)\b(?:\W+\w+){{0,3}}\W+{re.escape(surface_form)}\b",
                rf"\b{re.escape(surface_form)}\b(?:\W+\w+){{0,3}}\W+\b(?:absent|none)\b",
            ]
            return any(re.search(pattern, normalized_text) for pattern in neg_patterns)

        for symptom in self.symptoms_list:
            symptom_space = str(symptom).replace("_", " ")
            symptom_pattern = rf"\b{re.escape(symptom_space)}\b"
            if re.search(symptom_pattern, normalized_text):
                if is_negated(symptom_space):
                    continue
                extracted.append(symptom)
                
        for key, val in self.cross_lang_map.items():
            if str(key) in str(normalized_text):
                extracted.append(val)
                
        return list(set(extracted))

    def check_red_flags(self, symptoms):
        for s in symptoms:
            s_space = s.replace("_", " ")
            if any(rf in s_space or rf in s for rf in self.red_flag_symptoms):
                return True
        return False

    def predict_disease(self, current_symptoms):
        features = np.zeros(len(self.symptoms_list))
        for i, s in enumerate(self.symptoms_list):
            if s in current_symptoms:
                features[i] = 1
                
        features_df = pd.DataFrame([features], columns=self.symptoms_list)
        probs = self.rf_model.predict_proba(features_df)[0]
        max_prob_idx = np.argmax(probs)
        disease = self.rf_model.classes_[max_prob_idx]
        confidence = probs[max_prob_idx]
        
        return disease, confidence

    def get_relevant_followups(self, current_symptoms, user_message="", excluded_symptoms=None):
        excluded = set(excluded_symptoms or [])

        if not current_symptoms:
            return [
                s for s in self.safe_generic_followups
                if s in self.symptoms_list and s not in excluded
            ][:3]

        features = np.zeros(len(self.symptoms_list))
        for i, s in enumerate(self.symptoms_list):
            if s in current_symptoms:
                features[i] = 1
        features_df = pd.DataFrame([features], columns=self.symptoms_list)

        probs = self.rf_model.predict_proba(features_df)[0]
        top_idx = np.argsort(probs)[::-1][:5]

        df = self.training_df

        symptom_scores = {
            s: 0.0
            for s in self.symptoms_list
            if s not in current_symptoms and s not in excluded and s not in self.non_clinical_followup_symptoms
        }
        for idx in top_idx:
            disease = self.rf_model.classes_[idx]
            weight = float(probs[idx])
            disease_data = df[df['prognosis'] == disease]
            if disease_data.empty:
                continue
            symptom_frequencies = disease_data[self.symptoms_list].mean()
            for symptom in symptom_scores:
                symptom_scores[symptom] += float(symptom_frequencies[symptom]) * weight

        ranked = [
            s for s, score in sorted(symptom_scores.items(), key=lambda kv: kv[1], reverse=True)
            if score > 0
        ]

        risk_text = (user_message or '').lower()
        allow_sensitive = any(
            token in risk_text
            for token in ['hiv', 'aids', 'std', 'sti', 'sex', 'sexual', 'unprotected']
        )

        sanitized = []
        ranked_generic_first = [
            s for s in ranked
            if s in self.safe_generic_followups and s not in current_symptoms and s not in excluded and s not in self.non_clinical_followup_symptoms
        ]

        for symptom in ranked_generic_first:
            if (symptom in self.sensitive_followup_symptoms) and not allow_sensitive:
                continue
            sanitized.append(symptom)
            if len(sanitized) >= 3:
                break

        for symptom in self.safe_generic_followups:
            if symptom in current_symptoms:
                continue
            if symptom in excluded:
                continue
            if symptom in self.non_clinical_followup_symptoms:
                continue
            if symptom not in self.symptoms_list:
                continue
            if symptom in sanitized:
                continue
            sanitized.append(symptom)
            if len(sanitized) >= 3:
                break

        for symptom in ranked:
            if len(sanitized) >= 3:
                break
            if symptom in sanitized:
                continue
            if symptom in current_symptoms:
                continue
            if symptom in excluded:
                continue
            if symptom in self.non_clinical_followup_symptoms:
                continue
            if (symptom in self.sensitive_followup_symptoms) and not allow_sensitive:
                continue
            sanitized.append(symptom)

        return sanitized[:3]

    def rag_answer(self, query, language='en'):
        lang = (language or 'en').lower()
        language_names = {
            'en': 'English', 'hi': 'Hindi', 'es': 'Spanish', 'fr': 'French',
            'de': 'German', 'zh': 'Chinese', 'ja': 'Japanese', 'ar': 'Arabic'
        }
        localized = {
            'en': {
                'prefix': 'Based on medical knowledge:',
                'sources': 'Sources',
                'fallback': 'I could not derive enough detail. Please ask with more context.'
            },
            'hi': {
                'prefix': 'उपलब्ध चिकित्सीय जानकारी के आधार पर:',
                'sources': 'स्रोत',
                'fallback': 'मैं पर्याप्त विवरण नहीं निकाल सका। कृपया अधिक संदर्भ के साथ पूछें।'
            }
        }
        locale = localized.get(lang, localized['en'])
        answer_language = language_names.get(lang, 'English')

        docs_with_scores = self.vector_store.similarity_search_with_score(query, k=5)
        docs = [d for d, _score in docs_with_scores]
        context = "\n\n".join([d.page_content for d in docs[:4]])
        citations = []
        for d, _score in docs_with_scores[:3]:
            source = d.metadata.get('source') if d.metadata else None
            if source:
                citations.append(os.path.basename(source))
        citations = list(dict.fromkeys(citations))

        if self.use_ollama:
            try:
                prompt = (
                    "You are a safe medical assistant. Provide a clear and practical answer. "
                    "Use short sections: Overview, What to do now, Warning signs, When to see doctor. "
                    f"Respond in {answer_language}.\n\n"
                    f"Question: {query}\n"
                    f"Context: {context}\n"
                )
                res = requests.post(
                    f"{self.ollama_url}/api/generate",
                    json={"model": self.ollama_model, "prompt": prompt, "stream": False},
                    timeout=20
                )
                if res.ok:
                    text = (res.json().get('response') or '').strip()
                    if text:
                        if citations:
                            return f"{locale['prefix']}\n{text}\n\n{locale['sources']}: {', '.join(citations)}"
                        return f"{locale['prefix']}\n{text}"
            except Exception:
                pass

        input_text = (
            f"answer in {answer_language} with practical steps and warning signs. "
            f"question: {query} context: {context}"
        )
        res = self.qa_pipeline(input_text, max_length=220)
        answer = (res[0].get('generated_text') or '').strip()
        if len(answer) < 20:
            answer = locale['fallback']
        if citations:
            return f"{locale['prefix']} {answer}\n\n{locale['sources']}: {', '.join(citations)}"
        return f"{locale['prefix']} {answer}"

    def ask_ollama_direct(self, query, language='en'):
        if not self.use_ollama:
            return None
        language_names = {'en': 'English', 'hi': 'Hindi', 'es': 'Spanish', 'fr': 'French'}
        answer_language = language_names.get((language or 'en').lower(), 'English')
        prompt = f"You are a safe medical assistant. Respond in {answer_language}.\n\nQuestion: {query}"
        try:
            res = requests.post(f"{self.ollama_url}/api/generate",
                                 json={"model": self.ollama_model, "prompt": prompt, "stream": False},
                                 timeout=20)
            if res.ok:
                return (res.json().get('response') or '').strip()
        except:
            pass
        return None

    def diagnosis_explanation(self, disease, confidence_pct, symptoms, language='en'):
        if not self.use_ollama:
            return ""
        language_names = {'en': 'English', 'hi': 'Hindi', 'es': 'Spanish', 'fr': 'French'}
        answer_language = language_names.get((language or 'en').lower(), 'English')
        symptom_text = ', '.join(symptoms or [])
        prompt = (
            f"Explain why {symptom_text} might indicate {disease} ({confidence_pct}% confidence). "
            f"Max 80 words. Respond in {answer_language}."
        )
        try:
            res = requests.post(f"{self.ollama_url}/api/generate",
                                 json={"model": self.ollama_model, "prompt": prompt, "stream": False},
                                 timeout=15)
            if res.ok:
                return (res.json().get('response') or '').strip()
        except:
            pass
        return ""

# Singleton instance
ml_models = MLModels()
