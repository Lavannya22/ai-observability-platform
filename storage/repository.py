import json
from datetime import datetime

from storage.postgres import get_connection


# ── Logs ──────────────────────────────────────────────────────────────────────

def insert_log(log: dict, incident_id: str | None = None) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO logs (timestamp, service, level, message, scenario_id, incident_id)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            log["timestamp"],
            log["service"],
            log["level"],
            log["message"],
            log.get("scenario_id"),
            incident_id,
        ),
    )
    row_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return row_id


def get_logs_for_incident(incident_id: str) -> list[dict]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT timestamp, service, level, message, scenario_id
        FROM logs
        WHERE incident_id = %s
        ORDER BY timestamp
        """,
        (incident_id,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [
        {
            "timestamp": str(row[0]),
            "service": row[1],
            "level": row[2],
            "message": row[3],
            "scenario_id": row[4],
        }
        for row in rows
    ]


def count_logs_for_scenario(scenario_id: str) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM logs WHERE scenario_id = %s", (scenario_id,))
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    return count


def search_logs(query: str, limit: int = 50) -> list[dict]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT timestamp, service, level, message, scenario_id, incident_id
        FROM logs
        WHERE message ILIKE %s
        ORDER BY timestamp DESC
        LIMIT %s
        """,
        (f"%{query}%", limit),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [
        {
            "timestamp": str(row[0]),
            "service": row[1],
            "level": row[2],
            "message": row[3],
            "scenario_id": row[4],
            "incident_id": row[5],
        }
        for row in rows
    ]


def get_recent_logs(limit: int = 200) -> list[dict]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT timestamp, service, level, message, scenario_id, incident_id
        FROM logs
        ORDER BY timestamp DESC
        LIMIT %s
        """,
        (limit,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [
        {
            "timestamp": str(row[0]),
            "service": row[1],
            "level": row[2],
            "message": row[3],
            "scenario_id": row[4],
            "incident_id": row[5],
        }
        for row in rows
    ]


# ── Incidents ─────────────────────────────────────────────────────────────────

def create_incident(incident_id: str, service: str) -> dict:
    conn = get_connection()
    cur = conn.cursor()
    now = datetime.utcnow()
    cur.execute(
        """
        INSERT INTO incidents (incident_id, status, affected_services, created_at, last_log_at)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (incident_id, "OPEN", json.dumps([service]), now, now),
    )
    conn.commit()
    cur.close()
    conn.close()
    return {
        "incident_id": incident_id,
        "status": "OPEN",
        "affected_services": [service],
        "created_at": now,
        "last_log_at": now,
    }


def get_active_incidents() -> list[dict]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT incident_id, status, affected_services, root_cause, created_at, last_log_at
        FROM incidents
        WHERE status IN ('OPEN', 'DETECTING', 'ACTIVE')
        """
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [
        {
            "incident_id": row[0],
            "status": row[1],
            "affected_services": json.loads(row[2]) if row[2] else [],
            "root_cause": row[3],
            "created_at": row[4],
            "last_log_at": row[5],
        }
        for row in rows
    ]


def get_all_incidents(limit: int = 100) -> list[dict]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT incident_id, status, affected_services, root_cause, created_at, resolved_at, explanation
        FROM incidents
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (limit,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [
        {
            "incident_id": row[0],
            "status": row[1],
            "affected_services": json.loads(row[2]) if row[2] else [],
            "root_cause": row[3],
            "created_at": str(row[4]),
            "resolved_at": str(row[5]) if row[5] else None,
            "explanation": row[6],
        }
        for row in rows
    ]


def update_incident(incident_id: str, **kwargs):
    if not kwargs:
        return
    conn = get_connection()
    cur = conn.cursor()

    if "affected_services" in kwargs and isinstance(kwargs["affected_services"], list):
        kwargs["affected_services"] = json.dumps(kwargs["affected_services"])

    set_clause = ", ".join(f"{k} = %s" for k in kwargs)
    values = list(kwargs.values()) + [incident_id]
    cur.execute(
        f"UPDATE incidents SET {set_clause} WHERE incident_id = %s",
        values,
    )
    conn.commit()
    cur.close()
    conn.close()
