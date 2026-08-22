from flask import Flask, request, jsonify
import re

app = Flask(__name__)

# Character map to de-obfuscate leetspeak evasion attempts
LEET_MAP = {
    '@': 'a', '4': 'a', '!': 'i', '1': 'i', '|': 'i',
    '0': 'o', '$': 's', '5': 's', '3': 'e', '7': 't'
}

def normalize_text(text: str) -> str:
    """Converts leetspeak and special characters into standard letters."""
    text_lower = text.lower()
    for char, replacement in LEET_MAP.items():
        text_lower = text_lower.replace(char, replacement)
    return text_lower

@app.route("/predict", methods=["POST"])
def predict():
    data = request.get_json(silent=True) or {}
    raw_text = data.get("text", "")

    # 1. Edge Case: Empty or Whitespace-only input
    if not raw_text or not raw_text.strip() or raw_text.strip() == "...":
        return jsonify({"category": "Unknown", "model": "SupportGuard-v1"})

    normalized = normalize_text(raw_text)

    # 2. Priority Check: Complaint / Escalation Patterns
    # Checked first because an angry customer with a billing word in their
    # message ("unacceptable overcharge") should route to a human, not a bot flow.
    escalation_patterns = [
        r"unacceptable", r"furious", r"escalate", r"speak to a manager",
        r"terrible service", r"never again", r"lawsuit", r"sue you",
        r"worst experience"
    ]
    for pattern in escalation_patterns:
        if re.search(pattern, normalized):
            return jsonify({"category": "Complaint/Escalation", "model": "SupportGuard-v1"})

    # 3. Priority Check: Account Access Patterns
    access_patterns = [
        r"locked out", r"reset password", r"can'?t log ?in",
        r"2fa", r"verification code", r"forgot my password"
    ]
    for pattern in access_patterns:
        if re.search(pattern, normalized):
            return jsonify({"category": "Account Access", "model": "SupportGuard-v1"})

    # 4. Secondary Check: Billing Patterns
    billing_patterns = [
        r"invoice", r"overcharged", r"refund", r"billing",
        r"payment failed", r"charged twice", r"double charge"
    ]
    for pattern in billing_patterns:
        if re.search(pattern, normalized):
            return jsonify({"category": "Billing Issue", "model": "SupportGuard-v1"})

    # 5. Secondary Check: Cancellation Patterns
    cancellation_patterns = [
        r"cancel", r"unsubscribe", r"close my account", r"terminate"
    ]
    for pattern in cancellation_patterns:
        if re.search(pattern, normalized):
            return jsonify({"category": "Cancellation Request", "model": "SupportGuard-v1"})

    # 6. Secondary Check: Technical Support Patterns
    technical_patterns = [
        r"error", r"bug", r"crash(ed|ing)?", r"not working",
        r"won'?t load", r"broken", r"keeps freezing"
    ]
    for pattern in technical_patterns:
        if re.search(pattern, normalized):
            return jsonify({"category": "Technical Bug", "model": "SupportGuard-v1"})

    # 7. Default: General Inquiry
    return jsonify({"category": "General Inquiry", "model": "SupportGuard-v1"})

if __name__ == "__main__":
    print("🚀 Model 1 (SupportGuard-v1) running at http://127.0.0.1:5003/predict")
    app.run(port=5003, debug=False)
