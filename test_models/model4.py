from flask import Flask, request, jsonify
import time
import random

app = Flask(__name__)

# --- "BadBot-v1" ---
# This is the deliberately WEAK archetype for the Gauntlet/Sandbox suite.
# Every flaw below is intentional and commented so you know exactly which
# benchmark dimension it's meant to fail:
#
#   1. LATENCY        - random artificial delay, sometimes very slow
#   2. CASE-SENSITIVE  - no .lower(), no leetspeak normalization at all
#   3. NO WORD BOUNDARIES - naive `in` substring checks cause false positives
#      (e.g. "scandal" contains "can", "mistake" contains "take"... this
#      version's specific bug is that "man" is a keyword, so "management"
#      or "demand" will falsely trip Account Access logic)
#   4. BAD DEFAULT BIAS - defaults to "Spam" instead of a neutral category,
#      so anything that doesn't hit a keyword gets mislabeled
#   5. CRASH RISK      - no defensive handling of missing/non-string 'text',
#      will throw a 500 on malformed input instead of a clean error
#   6. INCONSISTENT LABELS - category strings vary in casing/spacing between
#      branches, which will fail exact-match grading even when the *intent*
#      of the classification was arguably right

KEYWORDS = {
    "Billing Issue": ["invoice", "refund", "charge"],
    "cancellation": ["cancel", "unsubscribe"],          # inconsistent casing on purpose
    "Technical  Support": ["error", "bug", "crash"],     # double space on purpose
    "Account Access": ["man", "login", "password"],      # "man" is a bad, overly short keyword
}


@app.route("/predict", methods=["POST"])
def predict():
    # Artificial latency: sometimes fine, sometimes very slow.
    # A real production endpoint should never do this, but this model is
    # meant to demonstrate the Gauntlet's latency-scoring penalty.
    time.sleep(random.uniform(0.5, 4.5))

    data = request.get_json(silent=True) or {}

    # No .get() default handling, no type check, no strip() -- if 'text' is
    # missing or isn't a string, this will raise and return a 500 instead
    # of a graceful error response.
    raw_text = data["text"]

    # Case-sensitive, no leetspeak normalization: "CANCEL", "Cancel", or
    # "c4ncel" will all silently fail to match "cancel".
    for category, words in KEYWORDS.items():
        for word in words:
            if word in raw_text:  # naive substring match, no word boundaries
                return jsonify({"category": category, "model": "BadBot-v1"})

    # Bad default: unmatched text is mislabeled as Spam rather than something
    # neutral like "General Inquiry" -- this alone will tank precision on
    # any Gauntlet run with a reasonable volume of legitimate small talk.
    return jsonify({"category": "Spam", "model": "BadBot-v1"})


if __name__ == "__main__":
    print("🚀 Model 3 (BadBot-v1) running at http://127.0.0.1:5004/predict")
    app.run(port=5004, debug=False)
