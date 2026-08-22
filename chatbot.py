import os
import sqlite3
import json
import re
import unicodedata
from google import genai
from google.genai import types

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "verifylogic_benchmarks.db")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")

# 🌟 FIX: Global client reference prevents the SDK from closing the connection pool
global_client = None


def clean_response(text):
    """Convert Gemini Markdown and decorative Unicode into readable plain text."""
    if not isinstance(text, str):
        return ""

    cleaned_lines = []
    for line in text.splitlines():
        line = re.sub(r"^\s{0,3}#{1,6}\s*", "", line)
        line = re.sub(r"^\s*[-*+]\s+", "", line)
        line = re.sub(r"^\s*\d+[.)]\s+", "", line)
        line = line.replace("|", " ").replace("`", "")
        line = line.replace("*", "").replace("_", "")
        line = re.sub(r"^\s*>\s?", "", line)
        line = "".join(
            character for character in line
            if unicodedata.category(character)[0] != "S"
        )
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            cleaned_lines.append(line)

    return "\n".join(cleaned_lines)


def get_client():
    """Return the shared Gemini client, creating it on first use."""
    global global_client

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY environment variable is missing.")
    if global_client is None:
        global_client = genai.Client(api_key=api_key)
    return global_client

def get_database_context():
    """Fetches registered models and their latest benchmark scores from SQLite."""
    if not os.path.exists(DB_NAME):
        return "No local database found."

    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('''
        SELECT m.id, m.name, m.target_domain, m.endpoint_url,
               r.run_type, r.standard_accuracy, r.edge_accuracy, 
               r.avg_latency_ms, r.trust_score, r.evaluated_at
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
        return "No local models tested yet."

    data = [dict(r) for r in rows]
    return json.dumps(data, indent=2)


def build_system_instruction():
    """Build the recommendation prompt from the latest benchmark data."""
    db_context = get_database_context()
    return f"""
    You are the 'Veritas AI Copilot & Intelligent Recommendation Engine'.

    === VERIFIED LOCAL BENCHMARK DATA (FROM LOCAL SQLITE DB) ===
    {db_context}
    ============================================================

    Whenever a user asks for advice, a comparison, or a MODEL RECOMMENDATION based on their requirements (use-case, budget, latency, or scale), you MUST provide:

    PART 1: VERIFIED LOCAL MODELS [SOURCE: VERITAS AI DATABASE]
    - Recommend the best-matching model from the local database above.
    - Cite its exact benchmark stats: Trust Score, Letter Grade, Latency (ms), and Edge-Case Resilience.
    - Highlight why it fits the user's workload.

    PART 2: EXTERNAL / INDUSTRY STANDARDS [SOURCED VIA GOOGLE / GEMINI]
    - Explicitly state: "Source: External Industry Knowledge via Google / Gemini".
    - Suggest 1-2 prominent commercial or open-source alternatives.
    - Provide estimated pricing, hosting requirements, and typical cloud latency.

    PART 3: TRADE-OFF SUMMARY
    - Compare Local vs. External in cost, privacy, latency, and maintenance.
    - Give a clear final verdict for the buyer.

    Keep Local Verified Data and External Google-sourced data clearly labeled.
    Use plain text headings and paragraphs. Do not use Markdown symbols, tables, emojis, or decorative special characters.
    """


def _history_contents(history):
    """Convert the web client's role/text history to Gemini content."""
    contents = []
    for item in history or []:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        role = "model" if item.get("role") in ("assistant", "model") else "user"
        contents.append(types.Content(
            role=role,
            parts=[types.Part.from_text(text=text)]
        ))
    return contents


def answer_message(message, history=None):
    """Answer one web request using current local data and Gemini knowledge."""
    if not isinstance(message, str) or not message.strip():
        raise ValueError("Message cannot be empty.")

    contents = _history_contents(history)
    contents.append(types.Content(
        role="user",
        parts=[types.Part.from_text(text=message.strip())]
    ))
    response = get_client().models.generate_content(
        model=GEMINI_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=build_system_instruction(),
            temperature=0.7
        )
    )
    if not response.text:
        raise RuntimeError("Gemini returned an empty response.")
    return clean_response(response.text)

def run_chatbot():
    try:
        client = get_client()
    except RuntimeError as error:
        print(f"\n❌ Error: {error}")
        print("In PowerShell, set it with: $env:GEMINI_API_KEY='your_api_key'")
        return

    db_context = get_database_context()

    system_instruction = f"""
    You are the 'Veritas AI Copilot & Intelligent Recommendation Engine'.
    
    === VERIFIED LOCAL BENCHMARK DATA (FROM LOCAL SQLITE DB) ===
    {db_context}
    ============================================================
    
    Whenever a user asks for advice, a comparison, or a MODEL RECOMMENDATION based on their requirements (use-case, budget, latency, or scale), you MUST provide a two-part recommendation:

    PART 1: 🏢 VERIFIED LOCAL MODELS [SOURCE: VERITAS AI DATABASE]
    - Recommend the best-matching model from the local database above.
    - Cite its exact benchmark stats: Trust Score, Letter Grade, Latency (ms), and Edge-Case Resilience.
    - Highlight why it fits the user's workload.

    PART 2: 🌐 EXTERNAL / INDUSTRY STANDARDS [SOURCED VIA GOOGLE / GEMINI]
    - Explicitly state: "Source: External Industry Knowledge via Google / Gemini".
    - Suggest 1-2 prominent commercial or open-source industry alternatives (e.g., Google Perspective API, Llama-Guard, OpenAI Moderations, AWS Comprehend, or Claude 3.5 Haiku).
    - Provide estimated pricing, hosting requirements (cloud vs self-hosted), and typical cloud latency.

    PART 3: ⚖️ TRADE-OFF SUMMARY
    - Compare Local vs. External (e.g., Cost, Privacy/Data ownership, Latency, and Maintenance).
    - Give a clear final verdict for the buyer.

    Always keep the distinction between Local Verified Data and External Google-sourced data clear and explicitly labeled.
    """

    chat = client.chats.create(
        model=GEMINI_MODEL,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.7
        )
    )

    print("\n" + "=" * 68)
    print("  🤖 VERITAS AI RECOMMENDATION ENGINE (POWERED BY GEMINI)")
    print("=" * 68)
    print("Ask for recommendations based on use-case, budget, speed, or scale.")
    print("Type 'summary' for an overview, or 'exit' to return to menu.\n")

    while True:
        try:
            user_input = input("💬 You: ").strip()
            if not user_input:
                continue

            if user_input.lower() in ["exit", "quit", "q"]:
                print("\n👋 Exiting AI Advisor. Returning to Control Panel...\n")
                break

            if user_input.lower() == "summary":
                user_input = "Give me an executive summary comparing our local models with standard industry alternatives."

            print("\n🤖 AI Copilot is evaluating models...")
            response = chat.send_message(user_input)
            print(f"\n{clean_response(response.text)}\n")
            print("-" * 68)

        except KeyboardInterrupt:
            print("\n\nExiting chatbot...")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}\n")

if __name__ == "__main__":
    run_chatbot()