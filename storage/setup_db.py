"""
One-time setup: creates the 'observability' database and tables.

Run once before starting the consumer:
    python storage/setup_db.py
"""

import sys
from pathlib import Path

import psycopg2
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))


def load_config(path: str = "configs/settings.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def setup(config_path: str = "configs/settings.yaml"):
    config = load_config(config_path)
    pg = config["postgres"]
    db_name = pg["database"]

    # Connect to the default 'postgres' database to create our database
    conn = psycopg2.connect(
        host=pg["host"],
        port=pg["port"],
        database="postgres",
        user=pg["user"],
        password=pg["password"],
    )
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
    exists = cur.fetchone()
    if not exists:
        cur.execute(f'CREATE DATABASE "{db_name}"')
        print(f"Database '{db_name}' created.")
    else:
        print(f"Database '{db_name}' already exists.")

    cur.close()
    conn.close()

    # Now create tables inside the observability database
    from storage.postgres import create_tables
    create_tables(config_path)
    print("Setup complete.")


if __name__ == "__main__":
    setup()
