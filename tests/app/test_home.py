"""Public HTML entry point; no database required."""
from fastapi.testclient import TestClient
from app.main import app


def test_root_serves_app_and_initializes_csrf_without_redirect():
    with TestClient(app) as client:
        response = client.get('/', follow_redirects=False)
        assert response.status_code == 200
        assert 'text/html' in response.headers['content-type']
        assert 'id="login"' in response.text and 'id="qr-dialog"' in response.text
        token = client.cookies['labseat_pre_csrf']
        assert token
        assert client.get('/').status_code == 200
        assert client.cookies['labseat_pre_csrf'] == token

