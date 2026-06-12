import sqlite3
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "demo.db"


def normalize_value(value: Any) -> str:
    if value is None:
        return "NULL"

    if isinstance(value, float):
        return f"{value:.6f}"

    return str(value)


def normalize_result(rows):
    """
    Convert SQLite result rows into a comparable format.

    We sort rows to avoid false negatives caused by different row orders.
    This is okay for the current basic evaluator.
    Later, we can make ORDER BY-sensitive evaluation stricter.
    """
    normalized = []

    for row in rows:
        normalized.append(tuple(normalize_value(x) for x in row))

    return sorted(normalized)


def run_sql(sql: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute(sql)
        rows = cursor.fetchall()

        return {
            "success": True,
            "result": normalize_result(rows),
            "error": None,
        }

    except Exception as e:
        return {
            "success": False,
            "result": None,
            "error": str(e),
        }

    finally:
        conn.close()