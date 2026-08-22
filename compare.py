import sqlite3
import time
import json
import urllib.request
import urllib.error

DB_NAME = "verifylogic_benchmarks.db"

DOMAIN_LABELS = {
    "customer_support": "Customer Support Triage",
    "spam_moderation": "Spam & Moderation Filters",
    "financial_transactions": "Transaction Categorization",
    "resume_screening": "Resume & Lead Screening"
}

def query_model(endpoint_url, text_input, timeout_seconds=5.0):
    """Sends a POST request to a model endpoint and returns prediction and latency."""
    endpoint_url = endpoint_url.replace("localhost", "127.0.0.1")
    payload = json.dumps({"text": text_input}).encode("utf-8")
    req = urllib.request.Request(
        endpoint_url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "VeritasAI-Sandbox/1.0"}
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
        return "ERROR", latency_ms, str(e)


def get_registered_models():
    """Fetches all models stored in SQLite."""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, target_domain, endpoint_url FROM models WHERE endpoint_url IS NOT NULL")
        models = cursor.fetchall()
        conn.close()
        return models
    except Exception:
        return []


def get_available_domains():
    """Fetches distinct domains available in test_cases table."""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT domain FROM test_cases")
        rows = cursor.fetchall()
        conn.close()
        return [r[0] for r in rows]
    except Exception:
        return []


def fetch_pre_existing_cases(selected_domains, filter_type="all"):
    """Fetches test cases from SQLite for specific domains and test filters."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    placeholders = ",".join(["?"] * len(selected_domains))
    query = f"SELECT input_text, expected_category, is_edge_case, edge_case_type FROM test_cases WHERE domain IN ({placeholders})"
    
    params = list(selected_domains)
    if filter_type == "standard":
        query += " AND is_edge_case = 0"
    elif filter_type == "edge":
        query += " AND is_edge_case = 1"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    return [(r[0], r[1]) for r in rows]


def save_sandbox_run(model_id, domain, accuracy, latency_ms, match_score):
    """Saves sandbox comparison runs into the database."""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO evaluation_runs 
            (model_id, domain, run_type, standard_accuracy, edge_accuracy, avg_latency_ms, trust_score)
            VALUES (?, ?, 'sandbox', ?, ?, ?, ?)
        ''', (model_id, domain, accuracy, accuracy, latency_ms, match_score))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠️ Warning: Could not log to DB: {e}")


def collect_models_to_test():
    """Lets user select registered models or manually enter new endpoints."""
    selected_models = []
    registered = get_registered_models()

    print("\n--- 1. SELECT MODELS TO COMPARE ---")
    if registered:
        print("Registered models from previous runs:")
        for idx, (m_id, name, domain, url) in enumerate(registered, start=1):
            domain_title = DOMAIN_LABELS.get(domain, domain)
            print(f"  [{idx}] {name} ({domain_title}) -> {url}")
        
        choices = input("\nEnter model numbers separated by comma (or press ENTER to enter custom URLs): ").strip()
        if choices:
            for c in choices.split(","):
                c = c.strip()
                if c.isdigit() and 1 <= int(c) <= len(registered):
                    m_id, name, domain, url = registered[int(c) - 1]
                    selected_models.append({"id": m_id, "name": name, "domain": domain, "url": url})

    if not selected_models:
        print("\nEnter custom model endpoints to compare (minimum 2 recommended):")
        count = 1
        while True:
            name = input(f"Model #{count} Name (or press ENTER to finish): ").strip()
            if not name and len(selected_models) >= 1:
                break
            if not name:
                continue
            url = input(f"Model #{count} Endpoint URL (e.g. http://127.0.0.1:5001/predict): ").strip()
            selected_models.append({"id": None, "name": name, "domain": "custom_sandbox", "url": url})
            count += 1
            if len(selected_models) >= 2:
                more = input("Add another model? (y/n): ").strip().lower()
                if more != "y":
                    break

    return selected_models


def collect_custom_test_cases():
    """Allows domain selection from database, custom interactive input, or JSON import."""
    print("\n--- 2. DEFINE TEST DATASET ---")
    print("  [1] Select From Pre-Existing Database Suites")
    print("  [2] Enter Custom Test Cases Interactively")
    print("  [3] Paste Raw JSON Array of Test Cases")

    choice = input("Select an option (1-3): ").strip()
    test_cases = []

    if choice == "1":
        available = get_available_domains()
        if not available:
            print("❌ No benchmark domains found in database. Please run benchmark_db.py first.")
            return []

        print("\nAvailable Pre-Existing Domains:")
        for idx, dom_key in enumerate(available, start=1):
            label = DOMAIN_LABELS.get(dom_key, dom_key)
            print(f"  [{idx}] {label} ({dom_key})")
        print(f"  [A] Run All Domains Combined")

        domain_choice = input(f"\nSelect domain(s) (e.g. 1 or 1,2 or A): ").strip()
        selected_domains = []

        if domain_choice.upper() == "A":
            selected_domains = available
        else:
            for item in domain_choice.split(","):
                item = item.strip()
                if item.isdigit() and 1 <= int(item) <= len(available):
                    selected_domains.append(available[int(item) - 1])

        if not selected_domains:
            print("Invalid selection. Defaulting to first domain.")
            selected_domains = [available[0]]

        # Sub-filter: standard vs edge vs all
        print("\nTest Case Scope:")
        print("  [1] Full Suite (Standard + Edge Cases)")
        print("  [2] Standard Cases Only")
        print("  [3] Adversarial Edge Cases Only")
        scope_choice = input("Select scope (1-3, default 1): ").strip()
        
        filter_type = "all"
        if scope_choice == "2":
            filter_type = "standard"
        elif scope_choice == "3":
            filter_type = "edge"

        test_cases = fetch_pre_existing_cases(selected_domains, filter_type)
        print(f"✅ Loaded {len(test_cases)} test cases from domain(s): {', '.join(selected_domains)}")

    elif choice == "2":
        print("\nEnter test cases (Input text + Expected Category). Type 'done' when finished:")
        while True:
            text = input("\nQuery / Text snippet (or 'done'): ").strip()
            if text.lower() == "done":
                if len(test_cases) == 0:
                    print("Please add at least 1 test case.")
                    continue
                break
            category = input(f"Expected Category for '{text[:30]}...': ").strip()
            test_cases.append((text, category))

    elif choice == "3":
        print('\nPaste JSON array format: [{"text": "...", "expected": "..."}]')
        raw_json = input("Paste JSON: ").strip()
        try:
            parsed = json.loads(raw_json)
            for item in parsed:
                test_cases.append((item["text"], item["expected"]))
            print(f"✅ Successfully loaded {len(test_cases)} test cases from JSON.")
        except Exception as e:
            print(f"❌ Failed to parse JSON: {e}.")
            return []

    return test_cases


def run_comparison():
    print("=" * 70)
    print("              VERITAS AI BUYER SANDBOX COMPARATOR")
    print("=" * 70)

    models = collect_models_to_test()
    if not models:
        print("❌ No models selected. Aborting.")
        return

    test_cases = collect_custom_test_cases()
    if not test_cases:
        print("❌ No test cases provided. Aborting.")
        return

    print(f"\n" + "=" * 70)
    print(f"⚡ RUNNING LIVE COMPARISON ON {len(models)} MODELS ({len(test_cases)} QUERIES)")
    print("=" * 70)

    # Performance tracker per model
    stats = {
        m["name"]: {
            "id": m["id"],
            "url": m["url"],
            "domain": m["domain"],
            "correct": 0,
            "total": len(test_cases),
            "total_latency": 0.0,
            "predictions": []
        }
        for m in models
    }

    # Run queries across all models
    for idx, (text_input, expected_cat) in enumerate(test_cases, start=1):
        display_text = text_input if text_input else "<EMPTY_STRING>"
        print(f"\n🔹 Query #{idx:02d}: \"{display_text[:50]}{'...' if len(display_text) > 50 else ''}\"")
        print(f"   Expected: [{expected_cat}]")

        for m in models:
            m_name = m["name"]
            pred, latency_ms, err = query_model(m["url"], text_input)
            stats[m_name]["total_latency"] += latency_ms

            is_correct = (pred.lower() == expected_cat.lower()) if not err else False
            if is_correct:
                stats[m_name]["correct"] += 1

            icon = "✅" if is_correct else "❌"
            print(f"   -> {m_name:<20} | Got: [{pred:<18}] | {latency_ms:>6.1f} ms | {icon}")
            
            stats[m_name]["predictions"].append({
                "query": text_input,
                "expected": expected_cat,
                "got": pred,
                "is_correct": is_correct,
                "latency_ms": latency_ms
            })

    # Calculate final sandbox scores
    print("\n" + "=" * 70)
    print("                   BUYER SANDBOX MATCH LEADERBOARD")
    print("=" * 70)
    print(f"{'Rank':<5} | {'Model Name':<22} | {'Match Acc':<10} | {'Avg Latency':<12} | {'MATCH SCORE':<12}")
    print("-" * 70)

    results = []
    for m_name, data in stats.items():
        acc = (data["correct"] / data["total"]) * 100.0 if data["total"] > 0 else 0.0
        avg_lat = data["total_latency"] / data["total"] if data["total"] > 0 else 0.0
        
        # Match Score formula for custom buyer data (70% Accuracy, 30% Speed)
        speed_score = max(0.0, min(100.0, 100.0 - max(0.0, avg_lat - 50.0) * 0.5))
        match_score = (0.70 * acc) + (0.30 * speed_score)

        results.append({
            "name": m_name,
            "id": data["id"],
            "domain": data["domain"],
            "accuracy": acc,
            "avg_latency": avg_lat,
            "match_score": match_score
        })

    # Sort leaderboard by Match Score descending
    results.sort(key=lambda x: x["match_score"], reverse=True)

    for rank, res in enumerate(results, start=1):
        crown = " 🥇 (Best Fit)" if rank == 1 else ""
        print(f"#{rank:<4} | {res['name']:<22} | {res['accuracy']:>6.1f}%    | {res['avg_latency']:>7.2f} ms   | {res['match_score']:>6.1f} / 100{crown}")

        # Save to database if registered model
        if res["id"]:
            save_sandbox_run(res["id"], res["domain"], res["accuracy"], res["avg_latency"], res["match_score"])

    print("=" * 70)
    print("💾 Sandbox comparison run completed and recorded.\n")


if __name__ == "__main__":
    run_comparison()