"""Atomic PostgreSQL response persistence; a retry never renews a hold."""
import hashlib
import json
import re
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from app.errors import Problem
from app.models import User, IdempotencyRecord


def execute(db, user_id, key, operation, payload, mutation):
    if key is None:
        return mutation()
    if not re.fullmatch(r'[A-Za-z0-9._:-]{8,128}', key):
        raise Problem(422, 'invalid_idempotency_key', 'Idempotency-Key không hợp lệ')
    # Same lock order as the booking engine, including requests using different keys.
    db.scalar(select(User).where(User.id == user_id).with_for_update())
    hashed = hashlib.sha256(key.encode()).hexdigest()
    fingerprint = hashlib.sha256(json.dumps({'operation': operation, 'payload': payload},
        sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    previous = db.get(IdempotencyRecord, (user_id, hashed))
    if previous:
        if previous.fingerprint != fingerprint:
            raise Problem(409, 'idempotency_key_reused', 'Idempotency-Key đã dùng cho yêu cầu khác')
        return previous.response
    response = jsonable_encoder(mutation())
    db.add(IdempotencyRecord(user_id=user_id, key_hash=hashed,
                            fingerprint=fingerprint, response=response))
    db.flush()
    return response
