import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "demo.db"
SCHEMA_PATH = BASE_DIR / "schema.sql"


SEED_SQL = """
INSERT INTO departments VALUES
(1, 'Engineering'),
(2, 'Marketing'),
(3, 'Finance');

INSERT INTO employees VALUES
(1, 'Alice', 90000, 1, '2021-03-01'),
(2, 'Bob', 75000, 1, '2022-07-15'),
(3, 'Cathy', 65000, 2, '2020-01-20'),
(4, 'David', 80000, 3, '2019-11-05'),
(5, 'Eva', 95000, 1, '2023-04-10');

INSERT INTO projects VALUES
(1, 'Search Engine', 1, 300000),
(2, 'Ad Campaign', 2, 120000),
(3, 'Risk Analysis', 3, 200000),
(4, 'Database Optimization', 1, 180000);
"""


def main():
    DATA_DIR.mkdir(exist_ok=True)

    conn = sqlite3.connect(DB_PATH)

    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())

    conn.executescript(SEED_SQL)
    conn.commit()
    conn.close()

    print(f"Database created at: {DB_PATH}")


if __name__ == "__main__":
    main()