#!/usr/bin/env python3
"""Check DAB's PostgreSQL and MongoDB loaders using small official fixtures.

The test refuses to replace existing databases and removes only the databases
it creates. Set PG_CLIENT to the server's psql wrapper before running it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dab-root", required=True, type=Path)
    args = parser.parse_args()

    dab_root = args.dab_root.resolve()
    sys.path.insert(0, str(dab_root))

    from pymongo import MongoClient

    from common_scaffold.tools.db_utils import db_config, mongo_utils, postgres_utils

    pg_name = "dab_smoke_books"
    pg_dump = dab_root / "query_bookreview/query_dataset/books_info.sql"
    if postgres_utils.check_db_exists(pg_name):
        raise RuntimeError(f"Refusing to replace existing PostgreSQL database {pg_name}")
    try:
        postgres_utils.load_db(str(pg_dump), pg_name)
        tables = postgres_utils.PostgresListDBTool.exec(
            pg_name,
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'",
        )
        print(f"postgres_ok database={pg_name} tables={tables}")
    finally:
        postgres_utils.clean_up(pg_name)

    mongo_name = "civic_db"
    mongo_dump = dab_root / "query_civic_unstructured/query_dataset/civic_docs_dump"
    with MongoClient(db_config.MONGO_URI) as client:
        if mongo_name in client.list_database_names():
            raise RuntimeError(f"Refusing to replace existing MongoDB database {mongo_name}")
    try:
        mongo_utils.load_db(str(mongo_dump), mongo_name)
        with MongoClient(db_config.MONGO_URI) as client:
            collections = client[mongo_name].list_collection_names()
            counts = {name: client[mongo_name][name].count_documents({}) for name in collections}
        if not counts or not any(counts.values()):
            raise RuntimeError("MongoDB restore completed without documents")
        print(f"mongo_ok database={mongo_name} counts={counts}")
    finally:
        mongo_utils.clean_up(mongo_name)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
