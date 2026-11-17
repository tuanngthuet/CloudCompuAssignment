"""Explicit local reset. Never called by startup or migrations."""
import argparse
import getpass
import json
import os
import shutil
from pathlib import Path
import uuid
from sqlalchemy import select, text, func
from sqlalchemy.engine import make_url
from app.infrastructure.database.session import Session
from .models import User, Room, Event, QueueSettings
from app.modules.auth.service import hasher
from app.infrastructure.storage.objects import storage, LocalStorage

TABLES = ('checkin_policy_events','notification_deliveries','outbox_events','idempotency_records','audit_events','reservations','session_seats','room_layouts','lab_sessions','seats','rooms','login_sessions','users','events','queue_policy_events')


def reset(execute=False, password=None):
    url=make_url(os.environ.get('DATABASE_URL','postgresql://localhost/labseat'))
    disposable_test = os.getenv('APP_ENV') == 'test' and url.host == 'test-db' and (url.database or '').endswith('_test')
    if os.getenv('APP_ENV','local') not in ('local','test') or (url.host not in ('localhost','127.0.0.1','db') and not disposable_test):
        raise RuntimeError('Reset chỉ chạy với database local/test trên localhost hoặc compose db')
    store=storage()
    if not isinstance(store,LocalStorage):
        raise RuntimeError('Reset này chỉ dành cho local storage; không xóa dữ liệu AWS')
    with Session.begin() as db:
        counts={table:db.scalar(text(f'SELECT count(*) FROM {table}')) for table in TABLES}
        if not execute:return counts
        if not password or len(password)<12 or not password.strip():raise ValueError('Mật khẩu admin tối thiểu 12 ký tự')
        encoded=hasher.hash(password)
        policy=db.get(QueueSettings,1,with_for_update=True)
        # Clear only this application's queue keys; never FLUSHDB.
        if os.getenv('REDIS_URL'):
            from app.infrastructure.redis.admission import client
            redis=client(operator=True)
            keys=list(redis.scan_iter(match='labseat:queue:*',count=100))
            if keys:redis.delete(*keys)
        elif policy.enabled:
            raise RuntimeError('Cấu hình REDIS_URL để xóa hàng chờ đang bật trước khi reset')
        db.execute(text('TRUNCATE '+','.join(TABLES)+' CASCADE'))
        policy.enabled=False;policy.recovery_pending=False;policy.epoch=uuid.uuid4();policy.policy_version+=1
        policy.updated_by='local-reset';policy.recovery_not_before=None
        db.add(User(username='admin',role='admin',password_hash=encoded))
    for folder in ('events','rooms','users'):
        target=store.path(folder+'/reset-marker').parent
        if target.exists():shutil.rmtree(target)
    return counts


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--admin-password-file',type=Path)
    args=parser.parse_args()
    password=None
    if args.execute:
        password=args.admin_password_file.read_text().removesuffix('\n') if args.admin_password_file else getpass.getpass('Mật khẩu admin mới: ')
    print(json.dumps(reset(args.execute,password),ensure_ascii=False,indent=2))
    if args.execute:print('Đã xóa dữ liệu cũ và tạo quản trị admin.')

if __name__=='__main__':main()
