import os
import sqlite3
import json
from pathlib import Path
from google import genai
from google.genai import types

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = str(BASE_DIR / "verifylogic_benchmarks.db")

def get_database_context():
    """Fetches registered models and their latest benchmark scores from SQLite."""
    if not os.path.exists(DB_PATH):
        return "No database found. Run benchmarks first."

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Query all models with their latest evaluation metrics
    cursor.execute('''
        SELECT m.id, m.name, m.target_domain, m.endpoint_url,
               r.run_type, r.standard_accuracy, r.edge_accuracy, r.avg_latency_ms, r.trust_score, r.evaluated_at
        FROM models m
        LEFT JOIN evaluation_runs r ON r.id = (
            SELECT id FROM evaluation_runs 
            WHERE model_id = m.id 
            ORDER BY evaluated_at DESC LIMIT 1
        )
    ''')
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return "No models or evaluation runs recorded in the database yet."

    data = [dict(r) for r in rows]
    return json.dumps(data, indent=2)


def build_system_instruction():
    """Build the copilot instructions from the latest local benchmark data."""
    return f"""
    You are the 'VerifyLogic AI Copilot', an expert benchmark analyst and marketplace advisor.

    Here is the live benchmark data from the user's database:
    {get_database_context()}

    Your role:
    1. Explain technical metrics (Standard Accuracy, Edge-Case Resilience, Latency, Trust/Match Score) in simple, plain English.
    2. Analyze where specific models are failing (for example edge cases, latency timeouts, or low accuracy).
    3. Help non-technical buyers compare models and make informed buying decisions.
    4. Keep answers concise, actionable, and conversational.
    """


def create_chat(api_key, history=None):
    """Create a Gemini chat using the current benchmark snapshot."""
    client = genai.Client(api_key=api_key)
    formatted_history = []
    for item in history or []:
        role = item.get("role")
        text = item.get("text", "").strip()
        if role in ("user", "model") and text:
            formatted_history.append(
                types.Content(role=role, parts=[types.Part(text=text)])
            )

    return client.chats.create(
        model=os.environ.get("GEMINI_MODEL", "gemini-2.0-flash"),
        config=types.GenerateContentConfig(
            system_instruction=build_system_instruction(),
            temperature=0.7
        ),
        history=formatted_history
    )


def answer_message(message, history=None):
    """Answer one web request, raising a useful error when Gemini is unavailable."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured on the server.")

    chat = create_chat(api_key, history)
    response = chat.send_message(message.strip())
    return response.text.strip()

def run_chatbot():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("\n❌ Error: GEMINI_API_KEY environment variable is missing.")
        print("Set it using: export GEMINI_API_KEY='your-key'")
        return

    chat = create_chat(api_key)

    print("\n" + "=" * 65)
    print("       🤖 VERIFYLOGIC AI BENCHMARK ADVISOR (POWERED BY GEMINI)")
    print("=" * 65)
    print("Ask any question about your models, scores, or failure points.")
    print("Type 'summary' for an executive recap, or 'exit' / 'quit' to return.\n")

    while True:
        try:
            user_input = input("💬 You: ").strip()
            if not user_input:
                continue

            if user_input.lower() in ["exit", "quit", "q"]:
                print("\n👋 Exiting AI Chatbot. Returning to Master Control Panel...\n")
                break

            if user_input.lower() == "summary":
                user_input = "Provide a high-level executive summary of all models currently tested in the database, ranking them and highlighting key strengths and weaknesses."

            print("\n🤖 AI Copilot is thinking...")
            response = chat.send_message(user_input)
            print(f"\n{response.text}\n")
            print("-" * 65)

        except KeyboardInterrupt:
            print("\n\nExiting chatbot...")
            break
        except Exception as e:
            print(f"\n❌ Error communicating with Gemini: {e}\n")

if __name__ == "__main__":
    run_chatbot()