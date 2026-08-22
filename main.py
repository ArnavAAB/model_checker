import sys
import subprocess
import os

# Direct imports from your existing modules
import benchmark_db
from gauntlet import run_gauntlet
from compare import run_comparison

def show_menu():
    print("\n" + "=" * 50)
    print("      VERIFYLOGIC - MASTER CONTROL PANEL")
    print("=" * 50)
    print("  [1] 🧪 Test / Benchmark a Model (Gauntlet)")
    print("  [2] ⚖️  Compare Models (Buyer Sandbox)")
    print("  [3] 🔄 Reset & Re-Seed Benchmark Database")
    print("  [4] 🤖 Launch Local Test Models (Port 5001 & 5002)")
    print("  [5] 🌐 Start Backend REST API Server (Port 5000)")
    print("  [0] 🚪 Exit")
    print("=" * 50)

def launch_background_models():
    """Spawns model1.py and model2.py in the background if present."""
    m1_path = os.path.join("test_models", "model1.py")
    m2_path = os.path.join("test_models", "model2.py")
    
    if os.path.exists(m1_path) and os.path.exists(m2_path):
        subprocess.Popen([sys.executable, m1_path])
        subprocess.Popen([sys.executable, m2_path])
        print("✅ Spawned Model 1 (:5001) and Model 2 (:5002) in background processes.")
    else:
        print("❌ Could not locate test_models/model1.py or test_models/model2.py.")

def start_server():
    """Starts server.py directly."""
    if os.path.exists("server.py"):
        print("🚀 Starting central server on http://127.0.0.1:5000 ...")
        subprocess.run([sys.executable, "server.py"])
    else:
        print("❌ server.py not found.")

def main():
    while True:
        show_menu()
        choice = input("Select an action (0-5): ").strip()

        if choice == "1":
            run_gauntlet()
        elif choice == "2":
            run_comparison()
        elif choice == "3":
            print("\nRebuilding SQLite database tables and seeding test suites...")
            benchmark_db.init_db()
            benchmark_db.seed_db()
        elif choice == "4":
            launch_background_models()
        elif choice == "5":
            start_server()
        elif choice == "0":
            print("\nExiting VerifyLogic Hub. Goodbye!")
            break
        else:
            print("\n⚠️ Invalid selection. Please enter a number between 0 and 5.")

if __name__ == "__main__":
    main()