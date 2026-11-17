import importlib.util
import pytest

@pytest.mark.skipif(any(importlib.util.find_spec(name) is None for name in ['sqlalchemy','psycopg','argon2','multipart']),reason='Full app dependencies unavailable')
def test_process_health_survives_db_failure():
    import subprocess
    import os
    import sys
    script='''
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as client:
    assert client.get('/healthz').status_code == 200
    response=client.get('/readyz')
    assert response.status_code == 503
    assert set(response.json()) == {'code','message','request_id'}
'''
    env=os.environ|{'DATABASE_URL':'postgresql+psycopg://fake:fake@127.0.0.1:1/unavailable','APP_ENV':'test'}
    subprocess.run([sys.executable,'-c',script],env=env,check=True,timeout=20)
