from __future__ import annotations

import argparse
import json
import types
from pathlib import Path
from unittest.mock import patch

import pytest

from experiments import run_dab_tool_agent as runner


class FakeQueryDBTool:
    def __init__(self, *args, check_load=True, **kwargs):
        self.check_load = check_load
        self.log_path = args[0]
        self.name = args[1]
        self.db_config_path = args[2]
        self.db_clients = {"main": {"db_type": "postgres", "db_name": "ready_db"}}

    def to_dict(self):
        # Match the upstream dict.update() return-value bug.
        return None


def test_preload_receipt_binds_config_and_reuse_skips_upstream_reload(tmp_path: Path) -> None:
    config = tmp_path / "db_config.yaml"
    config.write_text("db_clients: {}\n", encoding="utf-8")
    receipt = tmp_path / "preloaded_databases.json"
    receipt.write_text(json.dumps({
        "schema_version": "dab_preloaded_databases_v1",
        "status": "preloaded",
        "db_config_sha256": runner.database_config_digest(config),
        "databases": [{"logical_name": "main", "db_type": "postgres", "db_name": "ready_db"}],
    }), encoding="utf-8")
    db_config = types.SimpleNamespace(load_db_clients=lambda _: {
        "main": {"db_type": "postgres", "db_name": "ready_db"},
    })
    postgres = types.SimpleNamespace(check_db_exists=lambda name: name == "ready_db")
    mongo = types.SimpleNamespace(check_db_exists=lambda _: False)
    modules = {
        "common_scaffold.tools.db_utils.db_config": db_config,
        "common_scaffold.tools.db_utils.postgres_utils": postgres,
        "common_scaffold.tools.db_utils.mongo_utils": mongo,
    }
    data_agent_module = types.SimpleNamespace(QueryDBTool=FakeQueryDBTool)
    args = argparse.Namespace(reuse_preloaded_databases=True, preloaded_database_receipt=str(receipt), db_config=config)

    with patch.object(runner.importlib, "import_module", side_effect=lambda name: modules[name]):
        runner.install_preloaded_database_reuse(data_agent_module, args)

    tool = data_agent_module.QueryDBTool("log", "query_db", "config", check_load=True)
    assert tool.check_load is False
    metadata = tool.to_dict()
    assert metadata["preloaded_database_receipt"] == str(receipt)
    assert metadata["db_config_path"] == "config"


def test_reuse_fails_closed_when_the_receipt_does_not_match_config(tmp_path: Path) -> None:
    config = tmp_path / "db_config.yaml"
    config.write_text("db_clients: {}\n", encoding="utf-8")
    receipt = tmp_path / "preloaded_databases.json"
    receipt.write_text(json.dumps({
        "schema_version": "dab_preloaded_databases_v1",
        "status": "preloaded",
        "db_config_sha256": "0" * 64,
        "databases": [],
    }), encoding="utf-8")
    args = argparse.Namespace(reuse_preloaded_databases=True, preloaded_database_receipt=str(receipt), db_config=config)

    with pytest.raises(RuntimeError, match="does not match"):
        runner.install_preloaded_database_reuse(types.SimpleNamespace(QueryDBTool=FakeQueryDBTool), args)


def test_preload_records_bounded_restore_receipt(tmp_path: Path) -> None:
    config = tmp_path / "db_config.yaml"
    config.write_text("db_clients: {}\n", encoding="utf-8")
    calls: list[float] = []

    def original_run(*args, **kwargs):
        calls.append(kwargs["timeout"])
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    postgres = types.SimpleNamespace(
        subprocess=types.SimpleNamespace(run=original_run),
        load_db=lambda *_: postgres.subprocess.run(["psql"]),
        check_db_exists=lambda _: True,
    )
    mongo = types.SimpleNamespace(
        subprocess=types.SimpleNamespace(run=original_run),
        load_db=lambda *_: mongo.subprocess.run(["mongorestore"]),
        check_db_exists=lambda _: True,
    )
    db_config = types.SimpleNamespace(load_db_clients=lambda _: {
        "pg": {"db_type": "postgres", "db_name": "pg_db", "sql_file": "dump.sql"},
        "mongo": {"db_type": "mongo", "db_name": "mongo_db", "dump_folder": "dump"},
    })
    modules = {
        "common_scaffold.tools.db_utils.db_config": db_config,
        "common_scaffold.tools.db_utils.postgres_utils": postgres,
        "common_scaffold.tools.db_utils.mongo_utils": mongo,
    }
    args = argparse.Namespace(
        dab_upstream_root=tmp_path,
        db_config=config,
        database_bootstrap_timeout_sec=17.0,
    )

    with patch.object(runner, "import_upstream_data_agent"), \
            patch.object(runner.importlib, "import_module", side_effect=lambda name: modules[name]):
        receipt_path = runner.preload_databases(args, tmp_path / "receipt")

    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["status"] == "preloaded"
    assert receipt["bootstrap_timeout_sec"] == 17.0
    assert calls == [17.0, 17.0]


def test_postgres_statement_timeout_overrides_upstream_url_options() -> None:
    created_urls = []

    class FakeUrl:
        def __init__(self, options: str):
            self.query = {"options": options}

        def update_query_dict(self, updates):
            return FakeUrl(updates["options"])

    class FakeEngineModule:
        @staticmethod
        def make_url(_url):
            return FakeUrl("-c default_transaction_read_only=on")

    def create_engine(url, *_args, **_kwargs):
        created_urls.append(url)
        return object()

    postgres = types.SimpleNamespace(
        sqlalchemy=types.SimpleNamespace(create_engine=create_engine, engine=FakeEngineModule)
    )

    class QueryTool:
        @staticmethod
        def exec():
            postgres.sqlalchemy.create_engine(
                "postgresql+psycopg2://user:pass@host/db?options=-c%20default_transaction_read_only=on"
            )

    class ListTool:
        @staticmethod
        def exec():
            postgres.sqlalchemy.create_engine(
                "postgresql+psycopg2://user:pass@host/db?options=-c%20default_transaction_read_only=on"
            )

    postgres.PostgresQueryDBTool = QueryTool
    postgres.PostgresListDBTool = ListTool
    args = argparse.Namespace(postgres_statement_timeout_ms=300000)

    with patch.object(runner.importlib, "import_module", return_value=postgres):
        runner.install_postgres_statement_timeout(args)

    QueryTool.exec()
    ListTool.exec()

    assert len(created_urls) == 2
    assert all(
        url.query["options"] == "-c default_transaction_read_only=on -c statement_timeout=300000"
        for url in created_urls
    )
