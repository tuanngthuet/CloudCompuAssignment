"""Explicit reset clears local application data and creates a fresh admin."""
import os
from pathlib import Path
import pytest
if not os.getenv('TEST_DATABASE_URL'):pytest.skip('Disposable DB required',allow_module_level=True)
if os.getenv('APP_ENV')!='test' or not os.environ['TEST_DATABASE_URL'].endswith('_test'):raise RuntimeError('Disposable test DB only')
from test_event_management import client,payload,create
from app.reset import reset
from app.infrastructure.database.session import Session
from app.models import User,Event,QueueSettings
from sqlalchemy import select,func
from app.modules.auth.service import hasher


def test_local_reset_preview_execute_and_old_session_invalid(client,tmp_path,monkeypatch):
    monkeypatch.setenv('DATABASE_URL',os.environ['TEST_DATABASE_URL'])
    monkeypatch.setenv('LOCAL_STORAGE_PATH',str(tmp_path));monkeypatch.setenv('STORAGE_BACKEND','local');monkeypatch.delenv('REDIS_URL',raising=False)
    assert create(client,payload()).status_code==201
    (tmp_path/'rooms').mkdir(exist_ok=True);(tmp_path/'rooms/orphan.png').write_bytes(b'old')
    counts=reset();assert counts['users']>0 and counts['events']>0
    assert client.get('/me').status_code==200
    password='reset-only-test-password'
    reset(True,password)
    assert client.get('/me').status_code==401
    assert not (tmp_path/'events').exists() and not (tmp_path/'rooms').exists()
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(User))==1
        admin=db.scalar(select(User));assert admin.username=='admin' and admin.role=='admin'
        assert hasher.verify(admin.password_hash,password)
        assert db.scalar(select(func.count()).select_from(Event))==0
        assert not db.get(QueueSettings,1).enabled


def test_reset_rejects_production(monkeypatch):
    monkeypatch.setenv('APP_ENV','production')
    with pytest.raises(RuntimeError):reset(True,'reset-only-test-password')
