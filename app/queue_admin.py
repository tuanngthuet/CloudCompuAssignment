"""Operator-only CLI policy transitions; no public HTTP switch and no secret output."""
import json
import uuid
from dataclasses import replace
from datetime import timedelta
from sqlalchemy import text
from app.infrastructure.database.session import Session
from .models import QueueSettings, QueuePolicyEvent
import app.modules.booking.service as svc
from app.infrastructure.redis.admission import POLICY_LOCK, Policy, RedisQueue, client


def snapshot(row):
    keys = ('enabled','recovery_pending','policy_version','epoch','capacity','selection_seconds',
        'heartbeat_seconds','waiting_grace_seconds','recovery_not_before','updated_at','updated_by')
    return {k: (v.isoformat() if hasattr(v, 'isoformat') else str(v) if isinstance(v, uuid.UUID) else v)
        for k in keys for v in [getattr(row,k)]}


def change(operation, actor=None, reason=None, capacity=None, selection_seconds=None,
           heartbeat_seconds=None, waiting_grace_seconds=None):
    if operation not in ('enable','finish') and any(v is not None for v in (capacity,selection_seconds,heartbeat_seconds,waiting_grace_seconds)):
        raise svc.Problem(422,'invalid_operation','Chỉ thay thông số cùng --enable hoặc --finish sau drain')
    with Session.begin() as db:
        if operation != 'status':
            svc.require(bool(actor) and len(actor)<=100 and bool(reason) and len(reason)<=500,
                422, 'operator_required', 'Cần --actor và --reason; không ghi bí mật trong lý do')
            db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': POLICY_LOCK})
        row = db.get(QueueSettings, 1, populate_existing=True)
        svc.require(row is not None, 503, 'queue_configuration', 'Chạy migration trước')
        if operation == 'status':
            return snapshot(row)
        before = snapshot(row)
        clock = svc.now(db)
        if operation == 'begin':
            svc.require(row.enabled, 409, 'queue_disabled', 'Queue đang tắt; dùng queue-settings --enable để khởi tạo')
            svc.require(not row.recovery_pending, 409, 'recovery_pending', 'Đã ở chế độ bảo trì')
            row.recovery_pending = True
            row.recovery_not_before = clock + timedelta(seconds=row.selection_seconds)
            row.epoch = uuid.uuid4()
            row.policy_version += 1
        elif operation == 'disable':
            if row.enabled:
                svc.require(row.recovery_pending and row.recovery_not_before is not None and clock>=row.recovery_not_before,
                    409, 'drain_required', 'Chạy queue-recover --begin, chờ hết lease và drain trước khi tắt queue')
            row.enabled = False
            row.recovery_pending = False
            row.recovery_not_before = None
            row.epoch = uuid.uuid4()
            row.policy_version += 1
        elif operation in ('enable', 'finish'):
            if row.enabled:
                svc.require(operation=='finish' and row.recovery_pending and row.recovery_not_before is not None and clock>=row.recovery_not_before,
                    409, 'drain_required', 'Queue đang hoạt động hoặc chưa hết thời gian drain; dùng begin rồi finish')
            else:
                svc.require(operation=='enable', 409, 'queue_disabled', 'Dùng queue-settings --enable khi queue đang tắt')
            for name,value in [('capacity',capacity),('selection_seconds',selection_seconds),
                               ('heartbeat_seconds',heartbeat_seconds),('waiting_grace_seconds',waiting_grace_seconds)]:
                if value is not None:
                    setattr(row, name, value)
            svc.require(1<=row.capacity<=100 and 1<=row.selection_seconds<=600 and
                1<=row.heartbeat_seconds<=30 and row.heartbeat_seconds<row.waiting_grace_seconds<=600,
                422, 'invalid_policy', 'Thông số policy không hợp lệ')
            row.epoch = uuid.uuid4()
            row.policy_version += 1
            p = Policy(**{k:getattr(row,k) for k in Policy.__dataclass_fields__})
            store = RedisQueue(client(operator=True))
            store.prepare(p, clean_retired=True)
            # Verify readiness using the runtime ACL as well; the operator connection alone is insufficient.
            RedisQueue().call('ready', replace(p, recovery_pending=False))
            row.enabled = True
            row.recovery_pending = False
            row.recovery_not_before = None
        else:
            raise ValueError('Unknown queue operation')
        row.updated_at = clock
        row.updated_by = actor
        db.add(QueuePolicyEvent(actor=actor, reason=reason, before=before, after=snapshot(row)))
        return snapshot(row)


def run(args, parser):
    from .errors import Problem
    if args.command == 'queue-recover':
        operation = 'begin' if args.begin else 'finish' if args.finish else 'status'
    else:
        operation = 'enable' if args.enable else 'disable' if args.disable else 'status'
    try:
        result = change(operation, args.actor, args.reason, args.capacity, args.selection_seconds,
            args.heartbeat_seconds, args.waiting_grace_seconds)
    except Problem as exc:
        parser.exit(1, f'{exc.code}: {exc.message}\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))
