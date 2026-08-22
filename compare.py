import sqlite3

DB_NAME = "verifylogic_benchmarks.db"

DOMAIN_LABELS = {
    "customer_support": "Customer Support Triage",
    "spam_moderation": "Spam & Moderation Filters",
    "financial_transactions": "Transaction Categorization",
    "resume_screening": "Resume & Lead Screening"
}


def calculate_grade(score):
    """Converts a numerical Trust Score into a letter grade."""
    if score >= 90.0: return "A+"
    if score >= 80.0: return "A"
    if score >= 70.0: return "B"
    if score >= 60.0: return "C"
    return "F"


def get_evaluated_models():
    """Fetches all models that have at least one completed evaluation run."""
    try:
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('''
            SELECT m.id, m.name, m.target_domain,
                   r.standard_accuracy, r.edge_accuracy,
                   r.avg_latency_ms, r.trust_score, r.evaluated_at
            FROM models m
            INNER JOIN evaluation_runs r ON r.id = (
                SELECT id FROM evaluation_runs
                WHERE model_id = m.id
                ORDER BY evaluated_at DESC LIMIT 1
            )
            ORDER BY r.trust_score DESC
        ''')
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows
    except Exception:
        return []


def get_models_by_ids(model_ids):
    """Fetches the latest evaluation data for a list of model IDs."""
    if not model_ids:
        return []
    try:
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        placeholders = ",".join(["?"] * len(model_ids))
        cursor.execute(f'''
            SELECT m.id, m.name, m.target_domain,
                   r.standard_accuracy, r.edge_accuracy,
                   r.avg_latency_ms, r.trust_score, r.evaluated_at
            FROM models m
            INNER JOIN evaluation_runs r ON r.id = (
                SELECT id FROM evaluation_runs
                WHERE model_id = m.id
                ORDER BY evaluated_at DESC LIMIT 1
            )
            WHERE m.id IN ({placeholders})
            ORDER BY r.trust_score DESC
        ''', model_ids)
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows
    except Exception:
        return []


def run_comparison():
    print("=" * 70)
    print("          VERITAS AI — MODEL COMPARISON (FROM DATABASE)")
    print("=" * 70)

    # 1. Fetch all evaluated models
    evaluated = get_evaluated_models()

    if not evaluated:
        print("\n❌ No evaluated models found in the database.")
        print("   Run a Gauntlet evaluation first (option 1 in main menu).\n")
        return

    # 2. Display evaluated models
    print("\n📋 Models with completed benchmark evaluations:\n")
    print(f"  {'#':<4} {'Model Name':<24} {'Domain':<28} {'Trust Score':<12} {'Grade'}")
    print("  " + "-" * 80)

    for idx, m in enumerate(evaluated, start=1):
        domain_label = DOMAIN_LABELS.get(m["target_domain"], m["target_domain"])
        grade = calculate_grade(m["trust_score"])
        print(f"  [{idx}]  {m['name']:<24} {domain_label:<28} {m['trust_score']:>6.1f}       {grade}")

    # 3. Let user pick models to compare
    print(f"\n  [A]  Select All Models")
    choices = input("\nSelect models to compare (e.g. 1,3 or A for all): ").strip()

    selected = []
    if choices.upper() == "A":
        selected = evaluated
    else:
        for c in choices.split(","):
            c = c.strip()
            if c.isdigit() and 1 <= int(c) <= len(evaluated):
                selected.append(evaluated[int(c) - 1])

    if len(selected) < 2:
        print("\n❌ Please select at least 2 models to compare. Aborting.\n")
        return

    # 4. Display side-by-side comparison
    print(f"\n" + "=" * 70)
    print(f"⚡ COMPARING {len(selected)} MODELS (PRE-EVALUATED SCORES)")
    print("=" * 70)

    # Sort by trust score descending
    selected.sort(key=lambda x: x["trust_score"], reverse=True)

    print(f"\n{'Rank':<5} | {'Model Name':<22} | {'Std Acc':<8} | {'Edge Acc':<9} | {'Avg Latency':<12} | {'Trust Score':<12} | {'Grade'}")
    print("-" * 90)

    for rank, m in enumerate(selected, start=1):
        domain_label = DOMAIN_LABELS.get(m["target_domain"], m["target_domain"])
        grade = calculate_grade(m["trust_score"])
        crown = " 🥇 (Best)" if rank == 1 else ""
        print(f"#{rank:<4} | {m['name']:<22} | {m['standard_accuracy']:>5.1f}%  | {m['edge_accuracy']:>6.1f}%  | {m['avg_latency_ms']:>7.2f} ms   | {m['trust_score']:>6.1f} / 100 | {grade}{crown}")

    print("-" * 90)

    # 5. Summary
    best = selected[0]
    worst = selected[-1]
    print(f"\n🏆 Best overall: {best['name']} (Trust Score: {best['trust_score']:.1f})")
    if len(selected) > 1:
        delta = best["trust_score"] - worst["trust_score"]
        print(f"📊 Score spread: {delta:.1f} points between top and bottom model")

    print("=" * 70)
    print("📋 Comparison completed using stored evaluation data.\n")


if __name__ == "__main__":
    run_comparison()