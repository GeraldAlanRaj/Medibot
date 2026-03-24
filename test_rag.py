import sys
try:
    from ml_models import ml_models
    print("RAG loaded successfully")
    print(ml_models.rag_answer("What is the treatment for Dengue?"))
except Exception as e:
    import traceback
    traceback.print_exc()
    sys.exit(1)
