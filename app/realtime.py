"""Advisory SSE invalidations. Database snapshots remain authoritative."""

import asyncio
import json
import os
import time
from uuid import UUID
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from app.infrastructure.database.session import Session
from app.models import LabSession
from app.modules.booking.service import require

router = APIRouter()


def settings():
    production = os.getenv("APP_ENV", "local") == "production"
    url = os.getenv("REDIS_EVENTS_URL") or (
        None if production else os.getenv("REDIS_URL", "redis://redis:6379/0")
    )
    require(bool(url), 503, "realtime_unavailable", "Realtime chưa sẵn sàng.")
    from urllib.parse import urlsplit

    parsed = urlsplit(url)
    require(
        parsed.scheme in ("redis", "rediss")
        and not parsed.username
        and not parsed.password
        and not parsed.query,
        503,
        "realtime_unavailable",
        "Cấu hình realtime không hợp lệ.",
    )
    args = {
        "decode_responses": True,
        "socket_connect_timeout": 0.5,
        "socket_timeout": 1,
        "username": os.getenv("REDIS_EVENTS_USERNAME") or None,
        "password": os.getenv("REDIS_EVENTS_PASSWORD") or None,
    }
    if production:
        require(
            parsed.scheme == "rediss" and bool(args["username"] and args["password"]),
            503,
            "realtime_unavailable",
            "Realtime yêu cầu TLS/ACL.",
        )
    if parsed.scheme == "rediss":
        require(
            bool(os.getenv("REDIS_CA_CERT") or os.getenv("REDIS_CA_PATH")),
            503,
            "realtime_unavailable",
            "Cần CA tin cậy.",
        )
        args.update(
            ssl_ca_data=os.getenv("REDIS_CA_CERT") or None,
            ssl_ca_certs=os.getenv("REDIS_CA_PATH") or None,
            ssl_cert_reqs="required",
            ssl_check_hostname=True,
        )
    return url, args


def publish(session_id):
    from redis import Redis

    url, args = settings()
    with Redis.from_url(url, **args) as redis:
        redis.publish("labseat:events:" + str(session_id), str(session_id))


@router.get("/lab-sessions/{session_id}/stream")
async def stream(session_id: UUID, request: Request):
    with Session() as db:
        require(
            db.get(LabSession, session_id) is not None, 404, "not_found", "Không có ca."
        )
    url, args = settings()
    from redis.asyncio import Redis

    async def events():
        redis = Redis.from_url(url, **args)
        pubsub = redis.pubsub()
        try:
            await pubsub.subscribe("labseat:events:" + str(session_id))
            yield (
                "event: changed\ndata: "
                + json.dumps({"session_id": str(session_id)})
                + "\n\n"
            )
            heartbeat = time.monotonic()
            while not await request.is_disconnected():
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=1
                )
                if message:
                    yield (
                        "event: changed\ndata: "
                        + json.dumps({"session_id": str(session_id)})
                        + "\n\n"
                    )
                if time.monotonic() - heartbeat >= 15:
                    heartbeat = time.monotonic()
                    yield ": heartbeat\n\n"
                await asyncio.sleep(0.05)
        except Exception:
            yield "event: degraded\ndata: {}\n\n"
        finally:
            await pubsub.aclose()
            await redis.aclose()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
