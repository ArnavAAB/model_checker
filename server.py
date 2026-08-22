from flask import Flask, request, jsonify, send_from_directory, redirect, url_for
from pathlib import Path
import sqlite3
import time
import json
import urllib.request
import urllib.error

from auth import init_auth, register_auth_routes, login_required, get_current_user
from chatbot import answer_message

app = Flask(__name__)
BASE_DIR = Path(__file__).resolve().parent
DB_NAME = str(BASE_DIR / "verifylogic_benchmarks.db")


def ensure_database():
    """Create and seed the local benchmark database when the app is first started."""
    from benchmark_db import init_db, seed_db

    init_db()
    with sqlite3.connect(DB_NAME) as conn:
        has_cases = conn.execute("SELECT 1 FROM test_cases LIMIT 1").fetchone()
    if not has_cases:
        seed_db()

# Enable CORS for frontend integration
@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return response

# ==========================================
# HELPER FUNCTIONS
# ==========================================

def get_db():
    """Returns a SQLite connection with dict-like row access."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

# Wire up "Sign in with Google" (see auth.py for setup / required env vars).
init_auth(app)
register_auth_routes(app, get_db)
require_login = login_required(get_db)

def calculate_grade(score: float) -> str:
    """Converts a numerical Trust/Match Score into a letter grade."""
    if score >= 90.0: return "A+"
    if score >= 80.0: return "A"
    if score >= 70.0: return "B"
    if score >= 60.0: return "C"
    return "F"

def query_model_api(endpoint_url: str, text_input: str, timeout_seconds=5.0):
    """Sends a POST request to a model REST API endpoint."""
    payload = json.dumps({"text": text_input}).encode("utf-8")
    req = urllib.request.Request(
        endpoint_url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "VeritasAI-Server/1.0"}
    )
    
    start_time = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            response_data = response.read().decode("utf-8")
            
            try:
                parsed = json.loads(response_data)
                if isinstance(parsed, dict):
                    prediction = (
                        parsed.get("category") or 
                        parsed.get("prediction") or 
                        parsed.get("label") or 
                        parsed.get("result") or 
                        str(parsed)
                    )
                else:
                    prediction = str(parsed)
            except json.JSONDecodeError:
                prediction = response_data.strip()
                
            return str(prediction).strip(), latency_ms, None
            
    except Exception as e:
        latency_ms = (time.perf_counter() - start_time) * 1000.0
        return None, latency_ms, str(e)


# ==========================================
# REST API ENDPOINTS
# ==========================================

@app.route("/", methods=["GET"])
@app.route("/verifylogic.html", methods=["GET"])
def frontend():
    """Serve the dashboard only to authenticated users."""
    # The dashboard itself is private. Unauthenticated visitors are sent
    # directly into the Google OAuth flow before any site content is served.
    if not get_current_user(get_db):
        return redirect(url_for("login_google"))
    return send_from_directory(BASE_DIR, "verifylogic.html")

@app.route("/api/health", methods=["GET"])
def health_check():
    """Basic health check endpoint."""
    return jsonify({"status": "active", "service": "Veritas AI API Engine"})


@app.route("/api/chat", methods=["POST"])
@require_login
def chat_with_copilot():
    """Answer a benchmark question using the live database context."""
    data = request.get_json(silent=True) or {}
    message = data.get("message", "")
    history = data.get("history", [])

    if not isinstance(message, str) or not message.strip():
        return jsonify({"success": False, "error": "Message cannot be empty."}), 400
    if len(message) > 4000:
        return jsonify({"success": False, "error": "Message is too long (4,000 characters maximum)."}), 400
    if not isinstance(history, list):
        return jsonify({"success": False, "error": "Chat history must be an array."}), 400

    try:
        reply = answer_message(message, history[-20:])
    except RuntimeError as error:
        return jsonify({"success": False, "error": str(error)}), 503
    except Exception:
        app.logger.exception("Chatbot request failed")
        return jsonify({"success": False, "error": "The copilot could not answer right now."}), 502

    return jsonify({"success": True, "reply": reply})


@app.route("/api/domains", methods=["GET"])
def get_domains():
    """Lists all available benchmark domains and test case counts."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT domain, 
               COUNT(*) as total_cases,
               SUM(CASE WHEN is_edge_case = 0 THEN 1 ELSE 0 END) as standard_cases,
               SUM(CASE WHEN is_edge_case = 1 THEN 1 ELSE 0 END) as edge_cases
        FROM test_cases
        GROUP BY domain
    ''')
    domains = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({"success": True, "domains": domains})


@app.route("/api/models", methods=["GET"])
def get_marketplace_models():
    """
    Marketplace Leaderboard:
    Returns all registered models with their latest public Trust Scores and grades.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    # Query latest public evaluation per model
    cursor.execute('''
        SELECT m.id, m.name, m.target_domain, m.endpoint_url, m.created_at,
               r.standard_accuracy, r.edge_accuracy, r.avg_latency_ms, r.trust_score, r.evaluated_at
        FROM models m
        LEFT JOIN evaluation_runs r ON r.id = (
            SELECT id FROM evaluation_runs 
            WHERE model_id = m.id AND run_type = 'public' 
            ORDER BY evaluated_at DESC LIMIT 1
        )
        ORDER BY r.trust_score DESC NULLS LAST
    ''')
    
    models = []
    for row in cursor.fetchall():
        item = dict(row)
        score = item["trust_score"]
        item["grade"] = calculate_grade(score) if score is not None else "Unranked"
        models.append(item)
        
    conn.close()
    return jsonify({"success": True, "models": models})



@app.route("/api/models/<int:model_id>", methods=["GET"])
def get_model_details(model_id):
    """Returns detailed history and scorecard for a specific model."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM models WHERE id = ?", (model_id,))
    model = cursor.fetchone()
    if not model:
        conn.close()
        return jsonify({"success": False, "error": "Model not found"}), 404
        
    cursor.execute('''
        SELECT id, domain, run_type, standard_accuracy, edge_accuracy, avg_latency_ms, trust_score, evaluated_at 
        FROM evaluation_runs 
        WHERE model_id = ? 
        ORDER BY evaluated_at DESC
    ''', (model_id,))
    runs = [dict(r) for r in cursor.fetchall()]
    conn.close()
    
    return jsonify({
        "success": True,
        "model": dict(model),
        "evaluation_history": runs
    })


@app.route("/api/models/register", methods=["POST"])
@require_login
def register_and_evaluate_model():
    """
    Creator Submission Flow:
    Accepts model registration, immediately runs the public Gauntlet benchmark,
    stores the results in SQLite, and returns the comprehensive scorecard.
    Requires the caller to be signed in with Google; the submitted model is
    attributed to their account.
    """
    owner_user_id = request.current_user["id"]
    data = request.get_json(silent=True) or {}
    model_name = data.get("name", "").strip()
    target_domain = data.get("target_domain", "").strip()
    endpoint_url = data.get("endpoint_url", "").strip()

    if not model_name or not target_domain or not endpoint_url:
        return jsonify({"success": False, "error": "Missing required fields: 'name', 'target_domain', 'endpoint_url'"}), 400

    conn = get_db()
    cursor = conn.cursor()

    # Fetch test suite from DB
    cursor.execute('''
        SELECT input_text, expected_category, is_edge_case, edge_case_type 
        FROM test_cases 
        WHERE domain = ?
    ''', (target_domain,))
    test_cases = cursor.fetchall()

    if not test_cases:
        conn.close()
        return jsonify({"success": False, "error": f"No test suite found for domain '{target_domain}'"}), 400

    # 1. Run Gauntlet Loop
    total_latency_ms = 0.0
    correct_std, total_std = 0, 0
    correct_edge, total_edge = 0, 0
    logs = []

    for item in test_cases:
        text_in, expected_cat, is_edge, edge_type = item["input_text"], item["expected_category"], item["is_edge_case"], item["edge_case_type"]
        pred, latency_ms, err = query_model_api(endpoint_url, text_in)
        total_latency_ms += latency_ms

        is_correct = (pred.lower() == expected_cat.lower()) if (pred and not err) else False
        
        if is_edge:
            total_edge += 1
            if is_correct: correct_edge += 1
        else:
            total_std += 1
            if is_correct: correct_std += 1

        logs.append({
            "input": text_in,
            "expected": expected_cat,
            "predicted": pred if not err else None,
            "error": err,
            "is_edge_case": bool(is_edge),
            "edge_case_type": edge_type,
            "latency_ms": round(latency_ms, 2),
            "passed": is_correct
        })

    # 2. Score Calculations
    num_tests = len(test_cases)
    avg_latency = total_latency_ms / num_tests if num_tests > 0 else 0.0
    std_acc = (correct_std / total_std * 100.0) if total_std > 0 else 0.0
    edge_acc = (correct_edge / total_edge * 100.0) if total_edge > 0 else 0.0
    
    speed_score = max(0.0, min(100.0, 100.0 - max(0.0, avg_latency - 50.0) * 0.5))
    trust_score = (0.50 * std_acc) + (0.30 * speed_score) + (0.20 * edge_acc)

    # 3. Commit to SQLite
    cursor.execute('''
        INSERT INTO models (name, target_domain, endpoint_url, owner_user_id)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET 
            target_domain=excluded.target_domain,
            endpoint_url=excluded.endpoint_url,
            owner_user_id=excluded.owner_user_id
    ''', (model_name, target_domain, endpoint_url, owner_user_id))

    cursor.execute("SELECT id FROM models WHERE name = ?", (model_name,))
    model_id = cursor.fetchone()["id"]

    cursor.execute('''
        INSERT INTO evaluation_runs 
        (model_id, domain, run_type, standard_accuracy, edge_accuracy, avg_latency_ms, trust_score)
        VALUES (?, ?, 'public', ?, ?, ?, ?)
    ''', (model_id, target_domain, std_acc, edge_acc, avg_latency, trust_score))

    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "model_id": model_id,
        "name": model_name,
        "domain": target_domain,
        "trust_score": round(trust_score, 1),
        "grade": calculate_grade(trust_score),
        "metrics": {
            "standard_accuracy": round(std_acc, 1),
            "edge_accuracy": round(edge_acc, 1),
            "avg_latency_ms": round(avg_latency, 2),
            "speed_score": round(speed_score, 1)
        },
        "logs": logs
    })


if __name__ == "__main__":
    ensure_database()
    print("🚀 Veritas AI Central Backend running at http://127.0.0.1:5000")
    app.run(port=5000, debug=True)