import sqlite3
import time
import json
import urllib.request
import urllib.error
from pathlib import Path

DB_NAME = str(Path(__file__).resolve().parent / "verifylogic_benchmarks.db")

DOMAINS = {
    "1": ("customer_support", "Customer Support Triage"),
    "2": ("spam_moderation", "Spam & Moderation Filters"),
    "3": ("financial_transactions", "Transaction Categorization"),
    "4": ("resume_screening", "Resume & Lead Screening")
}

def query_model_api(endpoint_url, text_input, timeout_seconds=5.0):
    """
    Sends a POST request to the model's REST API endpoint.
    Expects a JSON payload: {"text": "..."}
    Handles responses formatted as:
      - {"category": "..."} or {"prediction": "..."} or {"label": "..."}
      - or a plain string
    """
    payload = json.dumps({"text": text_input}).encode("utf-8")
    req = urllib.request.Request(
        endpoint_url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "VeritasAI-Gauntlet/1.0"}
    )
    
    start_time = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            response_data = response.read().decode("utf-8")
            
            # Parse response
            try:
                parsed_json = json.loads(response_data)
                if isinstance(parsed_json, dict):
                    prediction = (
                        parsed_json.get("category") or 
                        parsed_json.get("prediction") or 
                        parsed_json.get("label") or 
                        parsed_json.get("result") or 
                        str(parsed_json)
                    )
                else:
                    prediction = str(parsed_json)
            except json.JSONDecodeError:
                prediction = response_data.strip()
                
            return str(prediction).strip(), latency_ms, None
            
    except urllib.error.HTTPError as e:
        latency_ms = (time.perf_counter() - start_time) * 1000.0
        return None, latency_ms, f"HTTP Error {e.code}"
    except urllib.error.URLError as e:
        latency_ms = (time.perf_counter() - start_time) * 1000.0
        return None, latency_ms, f"Connection Failed: {e.reason}"
    except Exception as e:
        latency_ms = (time.perf_counter() - start_time) * 1000.0
        return None, latency_ms, str(e)


def save_results(model_name, endpoint_url, domain_key, std_acc, edge_acc, avg_latency_ms, trust_score):
    """Persists the evaluated model and score run to SQLite."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Insert or fetch model
    cursor.execute('''
        INSERT OR IGNORE INTO models (name, target_domain, endpoint_url)
        VALUES (?, ?, ?)
    ''', (model_name, domain_key, endpoint_url))
    
    # Update endpoint if model already exists
    cursor.execute('UPDATE models SET endpoint_url = ? WHERE name = ?', (endpoint_url, model_name))
    cursor.execute('SELECT id FROM models WHERE name = ?', (model_name,))
    model_id = cursor.fetchone()[0]

    # Insert evaluation record
    cursor.execute('''
        INSERT INTO evaluation_runs 
        (model_id, domain, run_type, standard_accuracy, edge_accuracy, avg_latency_ms, trust_score)
        VALUES (?, ?, 'public', ?, ?, ?, ?)
    ''', (model_id, domain_key, std_acc, edge_acc, avg_latency_ms, trust_score))

    conn.commit()
    conn.close()


def run_gauntlet():
    print("=" * 60)
    print("      VERITAS AI ALGORITHMIC GAUNTLET ENGINE")
    print("=" * 60)

    # 1. Interactive CLI Prompts
    model_name = input("Enter Model Name: ").strip()
    while not model_name:
        model_name = input("Model name cannot be empty. Enter Model Name: ").strip()

    print("\nSelect the Model Domain:")
    for key, (domain_code, display_name) in DOMAINS.items():
        print(f"  [{key}] {display_name} ({domain_code})")
    
    choice = input("Enter domain choice (1-4): ").strip()
    while choice not in DOMAINS:
        choice = input("Invalid choice. Enter domain choice (1-4): ").strip()
    
    domain_key, domain_name = DOMAINS[choice]

    endpoint_url = input("\nEnter REST API Endpoint URL (e.g. http://localhost:5000/predict): ").strip()
    while not (endpoint_url.startswith("http://") or endpoint_url.startswith("https://")):
        endpoint_url = input("URL must start with http:// or https://: ").strip()
    endpoint_url = endpoint_url.replace("localhost", "127.0.0.1")

    # 2. Fetch test cases from Database
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT input_text, expected_category, is_edge_case, edge_case_type 
        FROM test_cases 
        WHERE domain = ?
    ''', (domain_key,))
    test_cases = cursor.fetchall()
    conn.close()

    if not test_cases:
        print(f"\nError: No test cases found in database for domain '{domain_key}'.")
        print("Please ensure you ran 'python benchmark_db.py' first.")
        return

    print(f"\n" + "-" * 60)
    print(f" Starting Gauntlet for [{model_name}] on [{domain_name}]")
    print(f" Target Endpoint: {endpoint_url}")
    print(f"Running {len(test_cases)} automated test vectors...")
    print("-" * 60)

    total_latency_ms = 0.0
    correct_std = 0
    total_std = 0
    correct_edge = 0
    total_edge = 0

    # 3. Execution Loop
    for idx, (input_text, expected_cat, is_edge, edge_type) in enumerate(test_cases, start=1):
        prediction, latency_ms, err = query_model_api(endpoint_url, input_text)
        total_latency_ms += latency_ms

        test_tag = f"[EDGE: {edge_type}]" if is_edge else "[STANDARD]"

        if err:
            status = f" ERROR ({err})"
            is_correct = False
        else:
            # Case-insensitive comparison
            is_correct = (prediction.lower() == expected_cat.lower())
            status = " PASS" if is_correct else f" FAIL (Got: '{prediction}', Expected: '{expected_cat}')"

        if is_edge:
            total_edge += 1
            if is_correct: correct_edge += 1
        else:
            total_std += 1
            if is_correct: correct_std += 1

        print(f"#{idx:02d} {test_tag:<24} | Latency: {latency_ms:>6.1f} ms | {status}")

    # 4. Score Calculations
    total_tests = len(test_cases)
    avg_latency_ms = total_latency_ms / total_tests if total_tests > 0 else 0.0
    std_acc = (correct_std / total_std * 100.0) if total_std > 0 else 0.0
    edge_acc = (correct_edge / total_edge * 100.0) if total_edge > 0 else 0.0

    # Speed Score formula: Perfect 100 if <= 50ms, scaled down if slower
    speed_score = max(0.0, min(100.0, 100.0 - max(0.0, avg_latency_ms - 50.0) * 0.5))

    # Unified Trust Score: 50% Standard Accuracy, 30% Speed Score, 20% Edge Resilience
    trust_score = (0.50 * std_acc) + (0.30 * speed_score) + (0.20 * edge_acc)

    # 5. Persist to Database
    save_results(model_name, endpoint_url, domain_key, std_acc, edge_acc, avg_latency_ms, trust_score)

    # 6. Terminal Scorecard
    print("\n" + "=" * 60)
    print("                      EVALUATION SCORECARD")
    print("=" * 60)
    print(f" Model Name:             {model_name}")
    print(f" Target Domain:          {domain_name}")
    print(f" Standard Accuracy:      {std_acc:.1f}% ({correct_std}/{total_std})")
    print(f" Edge-Case Resilience:   {edge_acc:.1f}% ({correct_edge}/{total_edge})")
    print(f" Average Latency:        {avg_latency_ms:.2f} ms (Speed Grade: {speed_score:.1f}/100)")
    print("-" * 60)
    print(f"  FINAL TRUST SCORE:   {trust_score:.1f} / 100")
    print("=" * 60)
    print(f" Results saved to database 'evaluation_runs' table.\n")

if __name__ == "__main__":
    run_gauntlet()