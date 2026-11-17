"""Apply LABSEAT migrations; adopt an already-matching schema without recreating data."""

from pathlib import Path
import re
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import UniqueConstraint, inspect, text
from app.infrastructure.database.session import engine

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "0001_labseat"
HEAD = "0002_platform"
MATCHING_SCHEMA_REVISION = "0009_current_event_fields"


def _sql(value):
    # PostgreSQL may move varchar/text array casts onto each array element
    # when equivalent DDL is replayed. Keep literals and grouping intact.
    parts = re.split(r"('(?:''|[^'])*')", str(value))
    for index in range(0, len(parts), 2):
        parts[index] = re.sub(
            r"::(?:character varying|text)(?:\[\])?", "", parts[index]
        )
        parts[index] = re.sub(r"\s+", "", parts[index])
    return "".join(parts)


def verify_baseline(conn, baseline):
    """Fail before the revision update if any application schema definition differs."""
    expected = baseline.schema()
    context = MigrationContext.configure(
        conn, opts={"compare_type": True, "compare_server_default": True}
    )
    mismatch = bool(compare_metadata(context, expected))
    inspector = inspect(conn)
    for name, table in expected.tables.items():
        if name not in inspector.get_table_names():
            mismatch = True
            continue
        # Alembic autogenerate does not fully compare CHECK/PK/partial predicates.
        actual_checks = {
            item["name"]: _sql(item["sqltext"])
            for item in inspector.get_check_constraints(name)
        }
        expected_checks = {
            key: _sql(value)
            for key, value in baseline.CHECK_EXPRESSIONS.get(name, {}).items()
        }
        mismatch |= actual_checks != expected_checks
        mismatch |= inspector.get_pk_constraint(name)["constrained_columns"] != [
            column.name for column in table.primary_key.columns
        ]
        actual_unique = {
            tuple(item["column_names"])
            for item in inspector.get_unique_constraints(name)
        }
        expected_unique = {
            tuple(column.name for column in item.columns)
            for item in table.constraints
            if isinstance(item, UniqueConstraint)
        }
        mismatch |= actual_unique != expected_unique
        actual_indexes = {item["name"]: item for item in inspector.get_indexes(name)}
        for index in table.indexes:
            actual = actual_indexes.get(index.name)
            expected_where = baseline.INDEX_PREDICATES.get(index.name)
            actual_where = (
                actual.get("dialect_options", {}).get("postgresql_where")
                if actual
                else None
            )
            mismatch |= actual is None or _sql(actual_where) != _sql(expected_where)
    if mismatch:
        raise RuntimeError(
            "Database schema differs from the consolidated baseline; revision was not changed"
        )
    if conn.scalar(text("SELECT count(*) FROM booking_queue_settings WHERE id=1")) != 1:
        raise RuntimeError("Queue policy is missing; revision was not changed")


def upgrade():
    config = Config(str(ROOT / "migrations/alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    scripts = ScriptDirectory.from_config(config)
    revisions = {revision.revision for revision in scripts.walk_revisions()}
    if scripts.get_current_head() != HEAD:
        raise RuntimeError("Migration HEAD does not match the source")
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(48390371)"))
        current = MigrationContext.configure(conn).get_current_heads()
        if current == (MATCHING_SCHEMA_REVISION,):
            verify_baseline(conn, scripts.get_revision(BASELINE).module)
            # The schema is identical. Only its revision marker changes, atomically.
            conn.execute(
                text(
                    "UPDATE alembic_version SET version_num=:new WHERE version_num=:old"
                ),
                {"new": BASELINE, "old": MATCHING_SCHEMA_REVISION},
            )
        elif len(current) > 1 or any(revision not in revisions for revision in current):
            raise RuntimeError("Unknown migration revision; database was not changed")
        config.attributes["connection"] = conn
        command.upgrade(config, "head")


if __name__ == "__main__":
    upgrade()
    print("LABSEAT database is at " + HEAD)
