import yaml
import psycopg2
from pathlib import Path

_DEFAULT_CONFIG = str(Path(__file__).parent.parent / "configs" / "settings.yaml")


def get_config(config_path: str = _DEFAULT_CONFIG) -> dict:
    with open(config_path) as f:
        return yaml.safe_load(f)


def get_connection(config_path: str = _DEFAULT_CONFIG):
    pg = get_config(config_path)["postgres"]
    return psycopg2.connect(
        host=pg["host"],
        port=pg["port"],
        database=pg["database"],
        user=pg["user"],
        password=pg["password"],
    )


def create_tables(config_path: str = _DEFAULT_CONFIG):
    conn = get_connection(config_path)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id            SERIAL PRIMARY KEY,
            timestamp     TIMESTAMP,
            service       VARCHAR(100),
            level         VARCHAR(20),
            message       TEXT,
            scenario_id   VARCHAR(20),
            incident_id   VARCHAR(50)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS incidents (
            incident_id       VARCHAR(50) PRIMARY KEY,
            status            VARCHAR(20)  DEFAULT 'OPEN',
            affected_services TEXT,
            root_cause        VARCHAR(100),
            created_at        TIMESTAMP    DEFAULT NOW(),
            resolved_at       TIMESTAMP,
            explanation       TEXT,
            last_log_at       TIMESTAMP,
            evidence          TEXT,
            propagation_path  TEXT,
            confidence_scores TEXT
        )
    """)

    # Migrate existing databases that predate Phase 4 columns
    for col, coltype in [
        ("evidence", "TEXT"),
        ("propagation_path", "TEXT"),
        ("confidence_scores", "TEXT"),
    ]:
        cur.execute(f"""
            ALTER TABLE incidents
            ADD COLUMN IF NOT EXISTS {col} {coltype}
        """)

    conn.commit()
    cur.close()
    conn.close()
    print("Tables created (logs, incidents)")
