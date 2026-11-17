"""Shared admission policy and Redis adapter. Disabled mode never constructs a Redis client."""
import json
import logging
import time
from app.infrastructure.observability.metrics import emit
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import event, select, text
from sqlalchemy.orm import Session as SQLSession
from app.config import integer
from app.errors import Problem
from app.models import QueueSettings, Reservation

logger = logging.getLogger('labseat.queue')
POLICY_LOCK = 481192040
SCRIPT = (Path(__file__).resolve().parents[2] / 'queue_scripts/admission.lua').read_text()


@dataclass(frozen=True)
class Policy:
    enabled: bool
    recovery_pending: bool
    policy_version: int
    epoch: UUID
    capacity: int
    selection_seconds: int
    heartbeat_seconds: int
    waiting_grace_seconds: int

    def public(self):
        return {key: getattr(self, key) for key in ('enabled', 'capacity', 'selection_seconds',
            'heartbeat_seconds', 'waiting_grace_seconds', 'policy_version')}


def policy(db, shared_lock=False):
    if shared_lock:
        # Operator transitions use the exclusive counterpart and wait for in-flight guards to commit.
        db.execute(text('SELECT pg_advisory_xact_lock_shared(:key)'), {'key': POLICY_LOCK})
    row = db.get(QueueSettings, 1, populate_existing=True)
    if row is None:
        raise Problem(503, 'queue_configuration', 'Cần chạy migration cấu hình phòng chờ')
    return Policy(**{name: getattr(row, name) for name in Policy.__dataclass_fields__})


def unavailable():
    return Problem(503, 'queue_unavailable', 'Phòng chờ đang gián đoạn. Đăng kí và lượt giữ hiện có vẫn được bảo toàn.')


@lru_cache(maxsize=2)
def client(operator=False):
    # Import and connect lazily; queue-off operation does not need Redis running or configured.
    from redis import BlockingConnectionPool, Redis
    from redis.backoff import NoBackoff
    from redis.retry import Retry
    url = os.getenv('REDIS_URL', '')
    parts = urlsplit(url)
    production = os.getenv('APP_ENV', 'local') == 'production'
    if not url or parts.scheme not in ('redis', 'rediss') or parts.username or parts.password or parts.query:
        raise unavailable()
    if production and (parts.scheme != 'rediss' or not (os.getenv('REDIS_CA_PATH') or os.getenv('REDIS_CA_CERT'))):
        raise unavailable()
    prefix = 'REDIS_OPERATOR_' if operator else 'REDIS_'
    username = os.getenv(prefix + 'USERNAME')
    password = os.getenv(prefix + 'PASSWORD')
    if production and (not username or not password):
        raise unavailable()
    kwargs = dict(username=username, password=password, decode_responses=True, protocol=2,
        socket_connect_timeout=integer('REDIS_CONNECT_TIMEOUT_MS', 300, maximum=5000)/1000,
        socket_timeout=integer('REDIS_COMMAND_TIMEOUT_MS', 500, maximum=5000)/1000,
        max_connections=integer('REDIS_MAX_CONNECTIONS', 4, maximum=4),
        retry=Retry(NoBackoff(), 0), retry_on_timeout=False)
    if parts.scheme == 'rediss':
        kwargs.update(ssl_ca_certs=os.getenv('REDIS_CA_PATH'), ssl_ca_data=os.getenv('REDIS_CA_CERT') or None, ssl_cert_reqs='required', ssl_check_hostname=True)
    pool = BlockingConnectionPool.from_url(url, timeout=0.3, **kwargs)
    return Redis(connection_pool=pool)


class RedisQueue:
    def __init__(self, connection=None):
        try:
            self.connection = connection if connection is not None else client()
        except Exception:
            raise unavailable() from None
        self.script = self.connection.register_script(SCRIPT)

    @staticmethod
    def keys(p, session_id):
        base = f'labseat:queue:{{{p.epoch}:{session_id}}}:'
        return ['labseat:queue:ready'] + [base + suffix for suffix in ('seq', 'waiting', 'admitted', 'entries', 'seen')]

    def call(self, action, p, session_id='', user_id='', close_at=None, end_at=None, generation=''):
        if p.recovery_pending:
            raise unavailable()
        started = time.monotonic()
        try:
            result = json.loads(self.script(keys=self.keys(p, session_id), args=[action, str(user_id),
                generation, int(close_at.timestamp()*1000) if close_at else 0,
                int((end_at.timestamp()+3600)*1000) if end_at else 0,
                p.capacity, p.selection_seconds*1000, p.waiting_grace_seconds*1000,
                str(p.epoch), p.policy_version]))
        except Exception:
            # Never log connection strings, credentials, entry IDs, or client exception text.
            emit('RedisFailure')
            emit('RedisAvailable', 0)
            logger.warning('queue_store_operation_failed action=%s', action)
            raise unavailable() from None
        emit('RedisLatencyMs', (time.monotonic() - started) * 1000)
        if result.get('error'):
            emit('RedisAvailable', 0)
            code = result['error']
            raise Problem(503, code, 'Phòng chờ chưa sẵn sàng, vui lòng thử lại sau')
        emit('RedisAvailable', 1)
        for wait_ms in result.get('granted_wait_ms', []):
            emit('AdmissionGrant')
            emit('QueueWaitMs', int(wait_ms))
            logger.info('queue_grant wait_ms=%d', int(wait_ms))
        return result

    def prepare(self, p, clean_retired=False):
        try:
            info = self.connection.info('server')
            major = int(info['redis_version'].split('.')[0])
            if major < 7:
                raise ValueError('Redis 7 or newer required')
            if clean_retired:
                # Only an operator after the DB drain may discard this dedicated queue namespace.
                batch=[]
                for key in self.connection.scan_iter(match='labseat:queue:{*',count=100):
                    batch.append(key)
                    if len(batch)==100:
                        self.connection.unlink(*batch);batch=[]
                if batch:self.connection.unlink(*batch)
            self.connection.set('labseat:queue:ready', json.dumps({
                'epoch': str(p.epoch), 'version': p.policy_version, 'run_id': info['run_id']}))
        except Exception:
            raise unavailable() from None


def response(p, session_id, result):
    return dict(session_id=session_id, status=result['status'], number_ahead=result.get('number_ahead'),
        admission_expires_at=datetime.fromtimestamp(result['expires_ms']/1000, timezone.utc) if result['status']=='ADMITTED' and result.get('expires_ms') else None,
        server_time=datetime.fromtimestamp(result['server_ms']/1000, timezone.utc),
        heartbeat_after_seconds=p.heartbeat_seconds, epoch=p.epoch, policy_version=p.policy_version)


def action(db, actor, lab, operation, clock):
    if operation=='join':
        from app.modules.profiles.service import require_for_exam
        require_for_exam(db,actor,lab)
    p = policy(db, shared_lock=True)
    if not p.enabled:
        return response(p, lab.id, {'status': 'DISABLED', 'server_ms': clock.timestamp()*1000})
    if operation == 'join':
        if not lab.open_at <= clock < lab.close_at:
            raise Problem(409, 'registration_closed', 'Ca chưa mở hoặc đã đóng đăng ký')
        active = db.scalar(select(Reservation.id).where(Reservation.user_id==actor,
            Reservation.session_id==lab.id, (Reservation.status.in_(('CONFIRMED','CHECKED_IN'))) |
            ((Reservation.status=='HELD') & (Reservation.hold_expires_at>clock))).limit(1))
        if active:
            raise Problem(409, 'active_registration', 'Bạn đã có đăng kí trong ca này. Hãy mở Ca đã đăng kí.')
    result = RedisQueue().call(operation, p, lab.id, actor, lab.close_at, lab.end_at, secrets.token_hex(16))
    return response(p, lab.id, result)


def guard(db, actor, lab):
    p = policy(db, shared_lock=True)
    if not p.enabled:
        return
    result = RedisQueue().call('guard', p, lab.id, actor, lab.close_at, lab.end_at)
    if result['status'] != 'ADMITTED':
        code = 'queue_waiting' if result['status'] in ('WAITING','NONE') else 'queue_expired'
        raise Problem(409, code, 'Bạn cần vào phòng chờ và có lượt chọn ghế còn hạn')
    db.info.setdefault('queue_releases', []).append((p, lab.id, actor, lab.close_at, lab.end_at, result['generation']))


@event.listens_for(SQLSession, 'after_commit')
def release_after_commit(db):
    for p, session_id, actor, close_at, end_at, generation in db.info.pop('queue_releases', []):
        try:
            RedisQueue().call('consume', p, session_id, actor, close_at, end_at, generation)
        except Exception:
            logger.warning('queue_release_failed_after_commit')


@event.listens_for(SQLSession, 'after_rollback')
def discard_after_rollback(db):
    db.info.pop('queue_releases', None)
