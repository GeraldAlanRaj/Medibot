import os
import json
import pickle
import numpy as np # pyre-ignore[21]
import pandas as pd # pyre-ignore[21]
import spacy # pyre-ignore[21]
from sklearn.ensemble import RandomForestClassifier # pyre-ignore[21]
from langchain_community.vectorstores import FAISS # pyre-ignore[21]
from langchain_huggingface import HuggingFaceEmbeddings # pyre-ignore[21]
from langchain_core.documents import Document # pyre-ignore[21]
from transformers import pipeline # pyre-ignore[21]

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
        
        self.red_flag_symptoms = ["chest pain", "chest_pain", "shortness of breath", "breathlessness", "severe bleeding", "loss of consciousness"]
        
        # Mapping for common Hindi/other keywords to English symptom names
        self.cross_lang_map = {
            "सिरदर्द": "headache",
            "बुखार": "high_fever",
            "cold": "continuous_sneezing",
            "itching": "itching",
            "khujli": "itching",
            "खांसी": "cough",
            "दर्द": "muscle_pain"
        }
        
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

    def _init_rag(self):
        faiss_index_path = os.path.join(self.models_cache, "faiss_index")
        
        if os.path.exists(faiss_index_path):
            print("Loading existing FAISS Vector Database...")
            try:
                return FAISS.load_local(
                    faiss_index_path, 
                    self.embeddings, 
                    allow_dangerous_deserialization=True
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
            df = pd.read_csv(self.data_path)
            # Handle potential unnamed columns from CSV export
            if 'Unnamed: 133' in df.columns:
                df = df.drop('Unnamed: 133', axis=1)
            
            # Ensure training data exactly matches the symptoms_list feature set
            X = df[self.symptoms_list]
            y = df['prognosis']
            
            clf = RandomForestClassifier(n_estimators=100, random_state=42)
            clf.fit(X, y)
            
            with open(self.model_path, 'wb') as f:
                pickle.dump(clf, f)
            return clf

    def extract_symptoms(self, text):
        text_lower = text.lower().replace("_", " ")
        extracted = []
        
        # 0. Quick common typo/shorthand mapping
        # Order matters: check longer phrases first, then single words
        phrase_map = {
            "chest pain": "chest_pain",
            "shortness of breath": "breathlessness",
            "loose motion": "diarrhoea",
            "loose stools": "diarrhoea",
            "joint pain": "joint_pain",
            "muscle pain": "muscle_pain",
            "back pain": "back_pain",
            "stomach pain": "stomach_pain",
            "high fever": "high_fever",
        }
        # Apply phrase mappings first (longer matches)
        for phrase, correct in phrase_map.items():
            if str(phrase) in str(text_lower):
                text_lower = str(text_lower).replace(str(phrase), str(correct))
        
        # Single-word typo corrections (applied AFTER phrase mapping)
        word_map = {
            "vomating": "vomiting",
            "vommit": "vomiting",
            "vomat": "vomiting",
            "cold": "continuous_sneezing",
            "headach": "headache",
            "fever": "high_fever",
        }
        for typo, correct in word_map.items():
            # Only replace if the typo hasn't already been handled by phrase_map
            if str(typo) in str(text_lower) and str(correct) not in str(text_lower):
                text_lower = str(text_lower).replace(str(typo), str(correct))

        # 1. Check English symptoms list
        for symptom in self.symptoms_list:
            # Match both underscore and space version
            symptom_space = str(symptom).replace("_", " ")
            if str(symptom_space) in str(text_lower) or str(symptom) in str(text_lower):
                extracted.append(symptom)
                
        # 2. Check Cross-language map
        for key, val in self.cross_lang_map.items():
            if str(key) in str(text_lower):
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
                
        # Convert to DataFrame to avoid UserWarning about feature names
        features_df = pd.DataFrame([features], columns=self.symptoms_list)
        probs = self.rf_model.predict_proba(features_df)[0]
        max_prob_idx = np.argmax(probs)
        disease = self.rf_model.classes_[max_prob_idx]
        confidence = probs[max_prob_idx]
        
        return disease, confidence

    def get_relevant_followups(self, current_symptoms):
        """
        Suggests relevant follow-up symptoms based on the most likely disease
        predicted from current symptoms.
        """
        if not current_symptoms:
            return [s.replace("_", " ") for s in self.symptoms_list[:3]]
            
        # Get the most likely disease
        disease, _ = self.predict_disease(current_symptoms)
        
        # Find all symptoms associated with this disease in the training data
        df = pd.read_csv(self.data_path)
        disease_data = df[df['prognosis'] == disease]
        
        # Calculate frequency of each symptom for this disease
        symptom_frequencies = disease_data[self.symptoms_list].mean()
        
        # Filter out symptoms already mentioned and sort by frequency
        potential_followups = [
            s for s in self.symptoms_list 
            if s not in current_symptoms and symptom_frequencies[s] > 0
        ]
        
        # Sort by frequency descending
        potential_followups.sort(key=lambda s: symptom_frequencies[s], reverse=True)
        
        # Return top 3 relevant follow-up symptoms in readable format
        return [s for i, s in enumerate(potential_followups) if i < 3]

    def rag_answer(self, query):
        docs = self.vector_store.similarity_search(query, k=3)
        context = " ".join([d.page_content for d in docs])
        
        input_text = f"question: {query} context: {context}"
        res = self.qa_pipeline(input_text, max_length=128)
        
        return f"Based on medical knowledge: {res[0]['generated_text']}"

# Singleton instance
ml_models = MLModels()

