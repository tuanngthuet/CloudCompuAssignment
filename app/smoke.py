"""One-off task with the release image and API configuration; no HTTP balancing."""
from sqlalchemy import text
from app.infrastructure.database.session import engine


def main():
    with engine.connect() as conn:
        if not conn.scalar(text('SELECT version_num FROM alembic_version')):
            raise RuntimeError('Release schema is not ready')
        # Check the schema this binary needs, allowing future additive migrations
        # so image rollback does not require a database downgrade.
        from app.infrastructure.database.session import Base
        from app import models  # Registers every table required by this binary.
        from sqlalchemy import select
        for table in Base.metadata.sorted_tables:
            conn.execute(select(table).limit(0))
    print('Release database smoke passed')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('Release database smoke failed; inspect configuration securely')
        raise SystemExit(1) from None
