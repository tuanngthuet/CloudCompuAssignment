"""Cache only published, version-matched public images; private responses stay uncached."""
from types import SimpleNamespace
from uuid import uuid4
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Event, RoomLayout
from app.shared.http import db_session


@pytest.fixture
def images(monkeypatch):
    event_id, room_id = uuid4(), uuid4()
    poster_key = f'events/{event_id}/poster/current.jpg'
    map_key = f'rooms/{room_id}/maps/current.png'

    class Database:
        def scalar(self, statement):
            return None

        def get(self, model, identity):
            if model is Event and identity == event_id:
                return SimpleNamespace(poster_key=poster_key)
            if model is RoomLayout and identity == room_id:
                return SimpleNamespace(layout={'image_key': map_key})
            return None

    class Storage:
        failing = False

        def get(self, key):
            if self.failing:
                raise OSError('Storage unavailable')
            return b'public image bytes'

    backend = Storage()
    monkeypatch.setattr('app.modules.auth.service.now', lambda db: datetime.now(timezone.utc))
    monkeypatch.setattr('app.modules.admin.router.storage', lambda: backend)
    monkeypatch.setattr('app.modules.rooms.router.storage', lambda: backend)
    app.dependency_overrides[db_session] = lambda: Database()
    try:
        with TestClient(app) as client:
            yield client, str(event_id), str(room_id), map_key, backend
    finally:
        app.dependency_overrides.pop(db_session, None)


@pytest.mark.parametrize('kind', ['poster', 'map'])
def test_only_current_version_of_public_image_is_cacheable(images, kind):
    client, event_id, room_id, _, _ = images
    path = f'/events/{event_id}/images/poster' if kind == 'poster' else f'/rooms/{room_id}/seat-map/image'
    version = 'current.jpg' if kind == 'poster' else 'current.png'
    response = client.get(path, params={'v': version})
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'public, max-age=86400'
    assert 'set-cookie' not in response.headers
    for params in ({}, {'v': 'old-version'}, {'v': ''}):
        response = client.get(path, params=params)
        assert response.status_code == 200
        assert response.headers['cache-control'] == 'no-store'


def test_map_key_previews_never_get_public_cache_headers(images, monkeypatch):
    client, _, room_id, key, _ = images
    path = f'/rooms/{room_id}/seat-map/image'
    response = client.get(path, params={'key': f'rooms/{room_id}/maps/draft.png', 'v': 'draft.png'})
    assert response.status_code == 401
    assert response.headers['cache-control'] == 'no-store'
    monkeypatch.setattr('app.modules.rooms.router.auth.authenticate', lambda *a, **kw: None)
    for candidate in (key, f'rooms/{room_id}/maps/draft.png'):
        response = client.get(path, params={'key': candidate, 'v': candidate.rsplit('/', 1)[-1]})
        assert response.status_code == 200
        assert response.headers['cache-control'] == 'no-store'


def test_errors_and_sensitive_responses_remain_uncached(images):
    client, event_id, room_id, _, storage = images
    storage.failing = True
    for path in (f'/events/{event_id}/images/poster?v=current.jpg',
                 f'/rooms/{room_id}/seat-map/image?v=current.png'):
        response = client.get(path)
        assert response.status_code == 503
        assert response.headers['cache-control'] == 'no-store'
    for path in (f'/events/{uuid4()}/images/poster?v=current.jpg',
                 f'/rooms/{uuid4()}/seat-map/image?v=current.png', '/me', '/healthz', '/'):
        assert client.get(path).headers['cache-control'] == 'no-store'
