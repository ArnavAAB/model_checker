from flask import Flask, request, jsonify
import math
import re

app = Flask(__name__)

# Training corpus to build word probability distributions
TRAINING_CORPUS = {
    "Legitimate": [
        "thanks for the quick response this resolved my issue",
        "can we schedule a meeting next tuesday to review the proposal",
        "hello please help me with my account settings",
        "great work on the new feature release",
        "thank you very much for your assistance"
    ],
    "Spam": [
        "congrats you won a 1000 gift card click bit ly claim now",
        "buy cheap followers and crypto pump signals at fastgrowth io",
        "viagra and cialis for cheap visit our shop today",
        "follow back please check bio for promo",
        "make money fast working from home sign up today"
    ],
    "Toxic/Flagged": [
        "you are completely incompetent and i hope your company burns down",
        "i will hunt down your entire support staff",
        "terrible service you all deserve to be fired immediately",
        "i hate you and your garbage platform"
    ]
}

def tokenize(text: str):
    """Splits text into lowercase words."""
    return re.findall(r'\b\w+\b', text.lower())

class NaiveBayesClassifier:
    def __init__(self, corpus):
        self.class_word_counts = {}
        self.class_totals = {}
        self.vocab = set()
        self.classes = list(corpus.keys())
        
        # Train model on corpus
        for category, documents in corpus.items():
            self.class_word_counts[category] = {}
            total = 0
            for doc in documents:
                for word in tokenize(doc):
                    self.class_word_counts[category][word] = self.class_word_counts[category].get(word, 0) + 1
                    self.vocab.add(word)
                    total += 1
            self.class_totals[category] = total

    def predict(self, text: str) -> str:
        tokens = tokenize(text)
        if not tokens:
            return "Unknown"

        scores = {}
        vocab_size = len(self.vocab)

        # Calculate log-likelihood with Laplace smoothing
        for category in self.classes:
            score = 0.0
            total_words = self.class_totals[category]
            for token in tokens:
                count = self.class_word_counts[category].get(token, 0)
                # P(word | category) with +1 smoothing
                prob = (count + 1) / (total_words + vocab_size)
                score += math.log(prob)
            scores[category] = score

        return max(scores, key=scores.get)

# Initialize the model
classifier = NaiveBayesClassifier(TRAINING_CORPUS)

@app.route("/predict", methods=["POST"])
def predict():
    data = request.get_json(silent=True) or {}
    raw_text = data.get("text", "")

    # Empty or whitespace handling
    if not raw_text or not raw_text.strip() or raw_text.strip() == "...":
        return jsonify({"category": "Unknown", "model": "BayesClassifier-v2"})

    prediction = classifier.predict(raw_text)
    return jsonify({"category": prediction, "model": "BayesClassifier-v2"})

if __name__ == "__main__":
    print("🚀 Model 2 (BayesClassifier-v2) running at http://127.0.0.1:5002/predict")
    app.run(port=5002, debug=False)