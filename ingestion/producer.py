"""
Kafka producer — streams logs for a given scenario to the 'logs' topic.

Usage:
    python ingestion/producer.py --scenario S001 --rate 17
"""

import argparse
import json
import sys
import time
from pathlib import Path

import yaml
from confluent_kafka import Producer

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from generator.log_generator import generate_logs


def load_config(path: str = "configs/settings.yaml") -> dict:
    with open(ROOT / path) as f:
        return yaml.safe_load(f)


def load_scenarios(path: str = "scenarios/scenarios.json") -> dict:
    with open(ROOT / path) as f:
        records = json.load(f)
    return {r["scenario_id"]: r for r in records}


def stream_scenario(scenario_id: str, logs_per_second: int = 17):
    config = load_config()
    scenarios = load_scenarios()

    if scenario_id not in scenarios:
        print(f"ERROR: Scenario '{scenario_id}' not found. Available: {list(scenarios.keys())}")
        sys.exit(1)

    scenario = scenarios[scenario_id]
    kafka_cfg = config["kafka"]

    producer = Producer({"bootstrap.servers": kafka_cfg["bootstrap_servers"]})

    logs = generate_logs(scenario)
    topic = kafka_cfg["topic"]

    print(f"Streaming {len(logs)} logs for {scenario_id} -> topic '{topic}' at {logs_per_second} logs/sec")

    start = time.time()
    for i, log in enumerate(logs):
        producer.produce(topic, value=json.dumps(log).encode("utf-8"))
        producer.poll(0)  # serve delivery callbacks without blocking

        if logs_per_second > 0:
            target_elapsed = (i + 1) / logs_per_second
            actual_elapsed = time.time() - start
            if actual_elapsed < target_elapsed:
                time.sleep(target_elapsed - actual_elapsed)

    producer.flush()
    elapsed = time.time() - start
    actual_rate = len(logs) / elapsed if elapsed > 0 else 0
    print(f"Done. {len(logs)} logs sent in {elapsed:.1f}s ({actual_rate:.0f} logs/sec)")

    return {"logs_generated": len(logs), "duration_seconds": elapsed}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Kafka log producer")
    parser.add_argument("--scenario", required=True, help="Scenario ID (e.g. S001)")
    parser.add_argument("--rate", type=int, default=17, help="Logs per second (default: 17 = ~1000/min)")
    args = parser.parse_args()
    stream_scenario(args.scenario, args.rate)
