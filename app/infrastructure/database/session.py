import os
from app.config import database_pool
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


engine = create_engine(
    os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://labseat:localonly@localhost:5432/labseat"
    ),
    pool_size=max(1, database_pool() - 1),
    max_overflow=0,
    pool_pre_ping=True,
    connect_args={
        "connect_timeout": 5,
        "options": "-c timezone=UTC -c lock_timeout=15000 -c statement_timeout=20000",
    },
)
Session = sessionmaker(engine, expire_on_commit=False)


# One connection from the API process budget is reserved for durable counters.
# This prevents requests holding all business connections while waiting to count.
# Background processes with pool1 never create the counter engine.
from functools import lru_cache


@lru_cache(maxsize=1)
def counter_sessions():
    if database_pool() < 2:
        raise RuntimeError("HTTP authentication requires DB_POOL_SIZE>=2")
    counter_engine = create_engine(
        engine.url,
        pool_size=1,
        max_overflow=0,
        pool_timeout=5,
        pool_pre_ping=True,
        connect_args={
            "connect_timeout": 5,
            "options": "-c timezone=UTC -c lock_timeout=5000 -c statement_timeout=5000",
        },
    )
    return sessionmaker(counter_engine, expire_on_commit=False)


from sqlalchemy import event
from app.infrastructure.observability.metrics import emit


@event.listens_for(engine, "checkout")
def pool_checkout(connection, record, proxy):
    emit("PoolCheckedOut", engine.pool.checkedout())


@event.listens_for(engine, "checkin")
def pool_checkin(connection, record):
    emit("PoolCheckedOut", max(0, engine.pool.checkedout() - 1))


@event.listens_for(engine, "handle_error")
def query_error(context):
    emit("DBQueryError")


from time import monotonic
from sqlalchemy.orm import Session as SQLSession


@event.listens_for(SQLSession, "after_transaction_create")
def transaction_started(session, transaction):
    if transaction.parent is None:
        session.info["metric_transaction_started"] = monotonic()


@event.listens_for(SQLSession, "after_transaction_end")
def transaction_finished(session, transaction):
    if transaction.parent is None:
        started = session.info.pop("metric_transaction_started", None)
        if started is not None:
            emit("DBTransactionMs", (monotonic() - started) * 1000)
