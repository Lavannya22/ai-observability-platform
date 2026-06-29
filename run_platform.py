"""
Platform runner — starts the Kafka consumer and FastAPI RAG API together.

Usage:
    python run_platform.py                        # consumer + API
    python run_platform.py --scenario S001        # also streams a scenario

Dashboard must be started separately:
    streamlit run dashboard/app.py
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
import threading
from pathlib import Path

ROOT = Path(__file__).parent


def start_consumer() -> subprocess.Popen:
    proc = subprocess.Popen(
        [sys.executable, "ingestion/consumer.py"],
        cwd=ROOT,
    )
    print(f"[PLATFORM] Consumer started (pid={proc.pid})")
    return proc


def start_api() -> subprocess.Popen:
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "rag.rag_api:app",
         "--host", "0.0.0.0", "--port", "8001", "--log-level", "warning"],
        cwd=ROOT,
    )
    print(f"[PLATFORM] RAG API started on http://localhost:8001 (pid={proc.pid})")
    return proc


def stream_scenario(scenario_id: str) -> None:
    time.sleep(3)  # let consumer initialise first
    print(f"[PLATFORM] Streaming scenario {scenario_id} ...")
    subprocess.run(
        [sys.executable, "ingestion/producer.py", "--scenario", scenario_id],
        cwd=ROOT,
    )


def main():
    parser = argparse.ArgumentParser(description="AI Observability Platform runner")
    parser.add_argument("--scenario", help="Scenario ID to stream after startup (e.g. S001)")
    parser.add_argument("--no-api", action="store_true", help="Skip starting the RAG API")
    args = parser.parse_args()

    procs = []

    try:
        consumer = start_consumer()
        procs.append(consumer)

        if not args.no_api:
            time.sleep(1)
            api = start_api()
            procs.append(api)

        if args.scenario:
            t = threading.Thread(target=stream_scenario, args=(args.scenario,), daemon=True)
            t.start()

        print("[PLATFORM] Running. Press Ctrl+C to stop.")
        print("[PLATFORM] Dashboard: streamlit run dashboard/app.py")
        print("[PLATFORM] Health:    http://localhost:8001/health")

        # Wait for any process to exit
        while True:
            for proc in procs:
                ret = proc.poll()
                if ret is not None:
                    print(f"[PLATFORM] Process {proc.pid} exited with code {ret}")
            time.sleep(2)

    except KeyboardInterrupt:
        print("\n[PLATFORM] Shutting down...")
    finally:
        for proc in procs:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        print("[PLATFORM] All processes stopped.")


if __name__ == "__main__":
    main()
