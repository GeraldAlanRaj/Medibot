import os
import tempfile
import csv

from ml_models import MLModels


class FakeRFModel:
    def __init__(self):
        self.classes_ = ["AIDS", "Flu"]

    def predict_proba(self, _features_df):
        # Strongly bias toward AIDS so the test can verify suppression behavior.
        return [[0.9, 0.1]]


def build_test_model():
    model = MLModels.__new__(MLModels)

    model.symptoms_list = [
        "high_fever",
        "headache",
        "extra_marital_contacts",
        "muscle_wasting",
        "patches_in_throat",
        "cough",
        "chills",
        "nausea",
        "vomiting",
        "fatigue",
        "loss_of_appetite",
        "joint_pain",
        "stomach_pain",
        "mild_fever",
        "skin_rash",
        "blister",
    ]

    model.cross_lang_map = {}
    model.red_flag_symptoms = []
    model.sensitive_followup_symptoms = {
        "extra_marital_contacts",
        "patches_in_throat",
        "muscle_wasting",
    }
    model.safe_generic_followups = [
        "chills",
        "cough",
        "nausea",
        "vomiting",
        "fatigue",
        "loss_of_appetite",
        "joint_pain",
        "stomach_pain",
        "mild_fever",
    ]
    model.rf_model = FakeRFModel()

    # Build a tiny synthetic training set that includes sensitive markers for AIDS.
    rows = [
        {
            "high_fever": 1,
            "headache": 0,
            "extra_marital_contacts": 1,
            "muscle_wasting": 1,
            "patches_in_throat": 1,
            "cough": 0,
            "chills": 0,
            "nausea": 0,
            "vomiting": 0,
            "fatigue": 1,
            "loss_of_appetite": 1,
            "joint_pain": 0,
            "stomach_pain": 0,
            "mild_fever": 0,
            "skin_rash": 1,
            "blister": 1,
            "prognosis": "AIDS",
        },
        {
            "high_fever": 1,
            "headache": 1,
            "extra_marital_contacts": 0,
            "muscle_wasting": 0,
            "patches_in_throat": 0,
            "cough": 1,
            "chills": 1,
            "nausea": 1,
            "vomiting": 1,
            "fatigue": 1,
            "loss_of_appetite": 1,
            "joint_pain": 1,
            "stomach_pain": 1,
            "mild_fever": 1,
            "skin_rash": 0,
            "blister": 0,
            "prognosis": "Flu",
        },
    ]

    fd, temp_csv = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    with open(temp_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    model.data_path = temp_csv

    return model, temp_csv


def test_sensitive_followups_blocked_without_risk_context():
    model, temp_csv = build_test_model()
    try:
        result = model.get_relevant_followups(["high_fever", "headache"], user_message="since 4 days")
        assert result, "Expected follow-up suggestions"
        assert not any(s in model.sensitive_followup_symptoms for s in result), (
            f"Sensitive follow-up leaked without risk context: {result}"
        )
    finally:
        os.remove(temp_csv)


def test_sensitive_followups_allowed_with_explicit_risk_context():
    model, temp_csv = build_test_model()
    try:
        # Fill all generic follow-up slots so broader ranking is used.
        current = ["high_fever", "headache"] + list(model.safe_generic_followups)
        result = model.get_relevant_followups(current, user_message="had unprotected sex recently")
        assert any(s in model.sensitive_followup_symptoms for s in result), (
            f"Expected at least one sensitive follow-up when explicit risk context exists: {result}"
        )
    finally:
        os.remove(temp_csv)


def test_body_ache_maps_to_joint_pain():
    model, temp_csv = build_test_model()
    try:
        extracted = model.extract_symptoms("I have fever and body ache")
        assert "joint_pain" in extracted, f"Expected 'joint_pain' mapping for body ache, got: {extracted}"
    finally:
        os.remove(temp_csv)


def test_excluded_followups_are_not_repeated():
    model, temp_csv = build_test_model()
    try:
        result = model.get_relevant_followups(
            ["high_fever", "headache"],
            user_message="no",
            excluded_symptoms=["skin_rash", "blister", "fatigue", "loss_of_appetite"]
        )
        excluded = {"skin_rash", "blister", "fatigue", "loss_of_appetite"}
        assert not any(s in excluded for s in result), (
            f"Excluded follow-ups were repeated: {result}"
        )
    finally:
        os.remove(temp_csv)


def test_mild_fever_is_extracted_correctly():
    model, temp_csv = build_test_model()
    try:
        extracted = model.extract_symptoms("I have mild fever")
        assert "mild_fever" in extracted, f"Expected 'mild_fever' extraction, got: {extracted}"
    finally:
        os.remove(temp_csv)


if __name__ == "__main__":
    test_sensitive_followups_blocked_without_risk_context()
    test_sensitive_followups_allowed_with_explicit_risk_context()
    test_body_ache_maps_to_joint_pain()
    test_excluded_followups_are_not_repeated()
    test_mild_fever_is_extracted_correctly()
    print("All follow-up guardrail tests passed.")
