from alembic import context
from sqlalchemy import text
from app.infrastructure.database.session import Base, engine
from app import models


def online(conn):
    context.configure(connection=conn,target_metadata=Base.metadata,compare_type=True)
    with context.begin_transaction():
        conn.execute(text('SELECT pg_advisory_xact_lock(48390371)'))
        context.run_migrations()


def run():
    if context.is_offline_mode():
        context.configure(url=str(engine.url),target_metadata=Base.metadata,literal_binds=True,dialect_opts={'paramstyle':'named'})
        with context.begin_transaction():
            context.run_migrations()
    elif context.config.attributes.get('connection') is not None:
        online(context.config.attributes['connection'])
    else:
        with engine.connect() as conn:
            online(conn)
run()
