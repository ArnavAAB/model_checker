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
        return jsonify({"category": "Unknown", "model": "RuleGuard-v1"})

    normalized = normalize_text(raw_text)

    # 2. Priority Check: Toxic / Threat Patterns
    toxic_patterns = [
        r"burn down", r"hunt down", r"incompetent", r"kill", 
        r"destroy", r"attack", r"threat"
    ]
    for pattern in toxic_patterns:
        if re.search(pattern, normalized):
            return jsonify({"category": "Toxic/Flagged", "model": "RuleGuard-v1"})

    # 3. Secondary Check: Spam / Promotion / Link Patterns
    spam_patterns = [
        r"gift card", r"bit\.ly", r"claim-now", r"cheap followers",
        r"crypto pump", r"fastgrowth", r"viagra", r"cialis",
        r"check bio", r"promo", r"won a \$", r"congrats"
    ]
    for pattern in spam_patterns:
        if re.search(pattern, normalized):
            return jsonify({"category": "Spam", "model": "RuleGuard-v1"})

    # 4. Default: Legitimate
    return jsonify({"category": "Legitimate", "model": "RuleGuard-v1"})

if __name__ == "__main__":
    print("🚀 Model 1 (RuleGuard-v1) running at http://127.0.0.1:5001/predict")
    app.run(port=5001, debug=False)