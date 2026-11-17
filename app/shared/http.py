"""Request transaction owner and server-side authorization dependencies."""

import time
from fastapi import Depends
from app.infrastructure.observability.metrics import emit
from app.infrastructure.database.session import Session
import app.modules.auth.service as auth


def db_session():
    with Session() as db:
        with db.begin():
            started = time.monotonic()
            db.connection()
            emit("PoolAcquireMs", (time.monotonic() - started) * 1000)
            yield db
        uid = db.info.pop("active_user_id", None)
    # The business transaction and its locks have ended before activity is touched.
    if uid:
        from sqlalchemy import update, func
        from app.models import User

        with Session.begin() as activity:
            activity.execute(
                update(User)
                .where(User.id == uid, User.status == "ACTIVE")
                .values(
                    last_activity_at=func.clock_timestamp(),
                    anonymization_notice_at=None,
                    anonymization_notice_delivered_at=None,
                )
            )


DB = Depends(db_session)


def admin(db, request):
    return auth.authenticate(db, request, write=True, admin=True)[0]
