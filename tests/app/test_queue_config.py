"""Role budgets and production connection boundaries; no Redis server required."""
import pytest
from app.config import database_pool


def test_pool_size_stays_within_connection_budget(monkeypatch):
    monkeypatch.delenv('DB_POOL_SIZE',raising=False)
    monkeypatch.delenv('DB_MAX_OVERFLOW',raising=False)
    assert database_pool()==3
    monkeypatch.setenv('DB_POOL_SIZE','4')
    with pytest.raises(ValueError):database_pool()


def test_pool_overflow_cannot_expand_budget(monkeypatch):
    monkeypatch.delenv('DB_POOL_SIZE',raising=False)
    monkeypatch.setenv('DB_MAX_OVERFLOW','1')
    with pytest.raises(ValueError):database_pool()


@pytest.mark.parametrize('url',['redis://private:6379/0','rediss://user:password@private:6379/0','rediss://private:6379/0?ssl_cert_reqs=none'])
def test_production_rejects_unsafe_redis_configuration(url,monkeypatch):
    pytest.importorskip('sqlalchemy');pytest.importorskip('redis')
    from app.infrastructure.redis.admission import client
    from app.errors import Problem
    client.cache_clear();monkeypatch.setenv('APP_ENV','production');monkeypatch.setenv('REDIS_URL',url)
    with pytest.raises(Problem) as exc:client()
    assert exc.value.status==503
    client.cache_clear()


def test_status_does_not_silently_ignore_policy_updates():
    pytest.importorskip('sqlalchemy')
    from app.queue_admin import change
    from app.errors import Problem
    with pytest.raises(Problem) as exc:change('status',capacity=5)
    assert exc.value.code=='invalid_operation'


def test_ecs_inline_ca_keeps_tls_verification(monkeypatch):
    from app.infrastructure.redis.admission import client
    from redis import BlockingConnectionPool
    captured = {}
    original = BlockingConnectionPool.from_url
    def pool(url, **kwargs):
        captured.update(kwargs)
        return original(url, **kwargs)
    client.cache_clear()
    monkeypatch.setenv('APP_ENV', 'production')
    monkeypatch.setenv('REDIS_URL', 'rediss://private:6379/0')
    monkeypatch.setenv('REDIS_CA_CERT', 'public-ca-fixture')
    monkeypatch.delenv('REDIS_CA_PATH', raising=False)
    monkeypatch.setenv('REDIS_USERNAME', 'runtime')
    monkeypatch.setenv('REDIS_PASSWORD', 'fixture-only')
    monkeypatch.setattr(BlockingConnectionPool, 'from_url', pool)
    connection = client()
    assert captured['ssl_ca_data'] == 'public-ca-fixture'
    assert captured['ssl_check_hostname'] is True and captured['ssl_cert_reqs'] == 'required'
    connection.close(); connection.connection_pool.disconnect(); client.cache_clear()
