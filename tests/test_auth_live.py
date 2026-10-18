from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
from backend.api import create_app
from backend.auth import COOKIE, OperatorSessions, hash_password
from backend.live_demo import frames, current_readings
from backend.storage import Store, load_config


def test_browser_sessions(tmp_path):
    store = Store(tmp_path / 'auth.db')
    users = {'operator': {'tenant': 'nimbus', 'password_hash': hash_password('correct')}}
    with TestClient(create_app(store, {}, users)) as client:
        headers = {'X-Coldline-Request': 'browser'}
        body = {'username': 'operator', 'password': 'correct'}
        assert client.post('/api/v1/session', json=body).status_code == 403
        assert client.post('/api/v1/session', headers=headers, json={**body, 'password': 'wrong'}).status_code == 401
        response = client.post('/api/v1/session', headers=headers, json=body)
        assert response.status_code == 200
        assert 'HttpOnly' in response.headers['set-cookie']
        assert 'SameSite=strict' in response.headers['set-cookie']
        token = client.cookies.get(COOKIE)
        assert client.get('/api/v1/trucks').json()['tenant'] == 'nimbus'
        assert client.post('/api/v1/readings', json={'readings': [{}]}).status_code == 403
        assert client.delete('/api/v1/session', headers=headers).status_code == 200
        assert client.get('/api/v1/trucks', headers={'Cookie': f'{COOKIE}={token}'}).status_code == 401
    store.engine.dispose()


def test_session_expiry_and_throttle(monkeypatch):
    sessions = OperatorSessions({'op': {'tenant': 'nimbus', 'password_hash': hash_password('pw')}})
    token, _ = sessions.login('op', 'pw', 'client')
    monkeypatch.setattr('backend.auth.time.monotonic', lambda: 10**12)
    assert sessions.resolve(token) is None
    for _ in range(10):
        with pytest.raises(Exception) as error:
            sessions.login('missing', 'pw', 'other')
        assert error.value.status_code == 401
    with pytest.raises(Exception) as error:
        sessions.login('op', 'pw', 'other')
    assert error.value.status_code == 429


def test_live_sequence_opens_and_recovers(tmp_path):
    config = load_config('config/live-demo.json')
    store = Store(tmp_path / 'live.db')
    store.provision(config)
    customer = config['tenants'][0]
    start = datetime.now(timezone.utc) - timedelta(minutes=3)
    opened = set()
    for tick, frame in enumerate(frames('starter_kit/data/sensor_readings.json', customer)):
        now = start + timedelta(seconds=tick * 10)
        for row in current_readings(frame, now, 'test-run', tick):
            assert store.ingest('nimbus', row)['status'] == 'accepted'
        opened.update(i['truck_id'] for i in store.list_incidents('nimbus') if i['lifecycle'] == 'open')
    assert opened == {'T-01', 'T-05'}
    incidents = store.list_incidents('nimbus')
    assert len(incidents) == 2
    assert all(i['lifecycle'] == 'recovered' for i in incidents)
    fleet = store.fleet('nimbus', now)
    assert fleet['demo_mode'] == 'live_simulation'
    assert all(t['freshness'] == 'fresh' for t in fleet['trucks'])
    store.engine.dispose()
