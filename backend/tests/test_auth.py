"""Account contracts, persisted sessions, and cross-user isolation."""
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import hashlib
from http.cookies import SimpleCookie
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from threading import Barrier

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select, update

from app import auth as auth_module
from app.auth import COOKIE_NAME, SESSION_SECONDS, verify_password
from app.config import Settings
from app.main import create_app
from app.models import AuthSessionRecord, UserRecord
from app.repository import DecisionRepository
from app.schemas import DecisionCreate, RetrospectiveCreate
from tests.test_calibration import retrospective_payload
from tests.test_finals_scenarios import general_payload


PASSWORD = '正确的密码-123'


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path / 'auth.db', settings=Settings(
        app_mode='demo', session_cookie_secure=False, registration_invite_code=None,
    ))
    with TestClient(app) as client:
        yield client


def register(client, username='Alice', password=PASSWORD, **extra):
    return client.post('/api/auth/register', json=dict(username=username, password=password, **extra))


def sign_in(client, username='Alice', password=PASSWORD):
    return client.post('/api/auth/login', json=dict(username=username, password=password))


def test_registration_sets_cookie_and_returns_only_public_user_fields(client):
    response = register(client, '  Alice  ')
    assert response.status_code == 201
    assert set(response.json()) == {'user'}
    user = response.json()['user']
    assert set(user) == {'id', 'username', 'created_at'}
    assert isinstance(user['id'], int) and user['username'] == 'Alice'
    assert datetime.fromisoformat(user['created_at']).utcoffset() == timedelta(0)
    cookie = SimpleCookie(response.headers['set-cookie'])[COOKIE_NAME]
    assert cookie['httponly'] and cookie['samesite'].lower() == 'lax'
    assert cookie['path'] == '/' and int(cookie['max-age']) == SESSION_SECONDS
    assert not cookie['secure']
    assert client.get('/api/auth/me').json() == response.json()


@pytest.mark.parametrize('username', ['Alice', 'alice', ' ALICE '])
def test_duplicate_username_is_case_insensitive(client, username):
    assert register(client).status_code == 201
    response = register(client, username)
    assert response.status_code == 409 and response.json() == {'detail': '用户名已存在'}


@pytest.mark.parametrize('username', ['ab', 'a' * 33, 'alice smith', 'abc@', 'ab🙂', 'abc\ndef', 'éabc', 'Ａlice'])
def test_invalid_usernames_are_rejected(client, username):
    response = register(client, username)
    assert response.status_code == 422 and isinstance(response.json()['detail'], str)


@pytest.mark.parametrize('password', ['短' * 7, 'a' * 129])
def test_invalid_password_lengths_are_rejected(client, password):
    assert register(client, password=password).status_code == 422


@pytest.mark.parametrize('username,password', [('用户一', '密' * 8), ('A_-.09', 'x' * 128), ('a' * 32, ' ' * 8)])
def test_allowed_characters_and_length_boundaries(client, username, password):
    assert register(client, username, password).status_code == 201
    client.post('/api/auth/logout')
    assert sign_in(client, username, password).status_code == 200


@pytest.mark.parametrize('endpoint,payload', [
    ('register', {}), ('register', {'username': 123, 'password': PASSWORD}),
    ('register', {'username': 'Alice', 'password': PASSWORD, 'invite_code': 123}),
    ('login', {}), ('login', {'username': 'Alice', 'password': None}),
])
def test_invalid_auth_bodies_have_chinese_detail_strings(client, endpoint, payload):
    response = client.post('/api/auth/' + endpoint, json=payload)
    assert response.status_code == 422
    assert isinstance(response.json()['detail'], str) and '请求参数' in response.json()['detail']


def test_login_errors_are_indistinguishable_and_success_preserves_username(client):
    user = register(client).json()
    client.post('/api/auth/logout')
    wrong = sign_in(client, password='wrong-password')
    missing = sign_in(client, username='Missing')
    assert wrong.status_code == missing.status_code == 401
    assert wrong.json() == missing.json() == {'detail': '用户名或密码错误'}
    response = sign_in(client, username='  ALICE  ')
    assert response.status_code == 200 and response.json() == user
    assert COOKIE_NAME in response.headers['set-cookie']


def test_login_limit_normalizes_username_and_expires_after_window(client, monkeypatch):
    register(client)
    clock = [1000.0]
    monkeypatch.setattr(auth_module, 'monotonic', lambda: clock[0])
    for attempt in range(10):
        response = sign_in(client, username='alice' if attempt % 2 else ' ALICE ', password='incorrect')
        assert response.status_code == (401 if attempt < 9 else 429)
    assert sign_in(client).status_code == 429
    assert sign_in(client, username='Another').status_code == 401
    clock[0] += 899
    assert sign_in(client).status_code == 429
    clock[0] += 1
    assert sign_in(client).status_code == 200


def test_successful_login_clears_failures(client):
    register(client)
    for _ in range(9):
        assert sign_in(client, password='incorrect').status_code == 401
    assert sign_in(client).status_code == 200
    for _ in range(9):
        assert sign_in(client, password='incorrect').status_code == 401


def test_nonexistent_user_is_also_rate_limited(client):
    for _ in range(10):
        response = sign_in(client, username='Nobody')
    assert response.status_code == 429


def test_logout_revokes_only_current_session_and_is_idempotent(client):
    register(client)
    token = client.cookies.get(COOKIE_NAME)
    with TestClient(client.app) as other:
        assert sign_in(other).status_code == 200
        response = client.post('/api/auth/logout')
        assert response.status_code == 204 and response.content == b''
        cookie = SimpleCookie(response.headers['set-cookie'])[COOKIE_NAME]
        assert cookie['max-age'] == '0' and cookie['path'] == '/'
        assert client.get('/api/auth/me').status_code == 401
        client.cookies.set(COOKIE_NAME, token)
        assert client.get('/api/auth/me').status_code == 401
        assert other.get('/api/auth/me').status_code == 200
        assert client.post('/api/auth/logout').status_code == 204
    assert client.post('/api/auth/logout').status_code == 204


@pytest.mark.parametrize('invite', [None, '', '邀请码-secret'])
def test_invite_configuration_is_public_but_secret_is_not(tmp_path, invite):
    app = create_app(tmp_path / 'invite.db', settings=Settings(registration_invite_code=invite))
    with TestClient(app) as client:
        health = client.get('/api/health')
        assert health.status_code == 200
        assert health.json()['registration_requires_invite'] is bool(invite)
        if invite:
            assert invite not in health.text
            assert register(client).status_code == 403
            assert register(client, invite_code='wrong').status_code == 403
            assert register(client, invite_code=invite).status_code == 201
        else:
            assert register(client).status_code == 201


def test_secure_cookie_setting_applies_to_issue_and_clear(tmp_path):
    app = create_app(tmp_path / 'secure.db', settings=Settings(session_cookie_secure=True))
    with TestClient(app, base_url='https://testserver') as client:
        response = register(client)
        assert SimpleCookie(response.headers['set-cookie'])[COOKIE_NAME]['secure']
        assert client.get('/api/auth/me').status_code == 200
        assert SimpleCookie(client.post('/api/auth/logout').headers['set-cookie'])[COOKIE_NAME]['secure']


def test_every_protected_route_requires_login_even_before_body_validation(client):
    routes = {path: operations for path, operations in client.app.openapi()['paths'].items()
              if path.startswith('/api/') and path != '/api/health' and not path.startswith('/api/auth/')}
    assert routes
    for path, operations in routes.items():
        for method in operations:
            response = client.request(method, path.replace('{decision_id}', 'missing'))
            assert response.status_code == 401, (method, path, response.text)
            assert response.json() == {'detail': '请先登录'}
    assert client.get('/api/health').status_code == 200


def test_passwords_are_salted_and_only_token_hashes_are_persisted(client):
    register(client)
    token = client.cookies.get(COOKIE_NAME)
    with client.app.state.repository._sessions() as session:
        user = session.scalar(select(UserRecord))
        auth_session = session.scalar(select(AuthSessionRecord))
        assert PASSWORD not in user.password_hash and verify_password(PASSWORD, user.password_hash)
        assert not verify_password('incorrect', user.password_hash)
        parts = user.password_hash.split('$')
        assert parts[:4] == ['scrypt', '16384', '8', '1']
        assert len(base64.b64decode(parts[4])) == 16 and len(base64.b64decode(parts[5])) == 64
        assert auth_session.token_hash == hashlib.sha256(token.encode()).hexdigest() != token
        assert auth_session.user_id == user.id
        assert auth_session.expires_at - auth_session.created_at == timedelta(days=30)
        first_hash = user.password_hash
    register(client, 'Bobby')
    with client.app.state.repository._sessions() as session:
        second = session.scalar(select(UserRecord).where(UserRecord.username == 'Bobby'))
        assert second.password_hash != first_hash


def test_expired_and_unknown_sessions_are_unauthenticated(client):
    register(client)
    token = client.cookies.get(COOKIE_NAME)
    digest = hashlib.sha256(token.encode()).hexdigest()
    with client.app.state.repository._sessions.begin() as session:
        session.execute(update(AuthSessionRecord).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    assert client.get('/api/auth/me').status_code == 401
    assert client.get('/api/decisions').status_code == 401
    with client.app.state.repository._sessions() as session:
        assert session.get(AuthSessionRecord, digest) is None
    client.cookies.clear()
    client.cookies.set(COOKIE_NAME, 'unknown-token')
    assert client.get('/api/auth/me').status_code == 401


def test_session_survives_restart_and_database_digest_is_not_a_bearer_token(tmp_path):
    path = tmp_path / 'persistent.db'
    with TestClient(create_app(path)) as first:
        expected = register(first).json()
        token = first.cookies.get(COOKIE_NAME)
    with TestClient(create_app(path)) as restarted:
        restarted.cookies.set(COOKIE_NAME, token)
        assert restarted.get('/api/auth/me').json() == expected
        restarted.cookies.set(COOKIE_NAME, hashlib.sha256(token.encode()).hexdigest())
        assert restarted.get('/api/auth/me').status_code == 401


@pytest.mark.parametrize('method,suffix,payload', [
    ('GET', '', None), ('GET', '/export.md', None), ('POST', '/run', None),
    ('POST', '/retry', None), ('POST', '/confirm', None),
    ('POST', '/review', {'action': 'accepted'}),
    ('POST', '/objection-labels', {'labels': {'O1': 'adopted'}}),
    ('POST', '/outcomes', {'checkpoint': 'custom', 'actuals': [{'assumption_id': 'A1', 'actual_value': 10}]}),
])
def test_cross_user_and_missing_decisions_are_indistinguishable(client, method, suffix, payload):
    alice = register(client).json()['user']
    response = client.post('/api/decisions', json=general_payload())
    assert response.status_code == 201
    decision = response.json()
    assert 'owner_id' not in decision and 'owner' not in decision
    assert client.app.state.repository.owner_of(decision['id']) == alice['id']
    with TestClient(client.app) as bob:
        register(bob, 'Bobby')
        assert bob.get('/api/decisions').json() == []
        denied = bob.request(method, '/api/decisions/' + decision['id'] + suffix, json=payload)
        missing = bob.request(method, '/api/decisions/missing' + suffix, json=payload)
        assert denied.status_code == missing.status_code == 404
        assert denied.json() == missing.json() == {'detail': '决策不存在'}
    assert client.get('/api/decisions/' + decision['id']).json() == decision


def test_retrospectives_and_calibration_only_use_owned_decisions(client):
    alice = register(client).json()['user']
    own = client.post('/api/retrospectives', json=retrospective_payload()).json()
    repository = client.app.state.repository
    legacy = repository.create_retrospective(RetrospectiveCreate(**retrospective_payload()))
    assert repository.owner_of(own['id']) == alice['id']
    assert repository.owner_of(legacy.id) is None
    assert {item['id'] for item in client.get('/api/decisions').json()} == {own['id']}
    assert {sample['decision_id'] for sample in client.get('/api/calibration').json()['samples']} == {own['id']}
    assert client.get('/api/decisions/' + legacy.id).status_code == 404
    with TestClient(client.app) as bob:
        register(bob, 'Bobby')
        assert bob.get('/api/calibration').json()['samples'] == []
        assert bob.get('/api/decisions').json() == []
        assert bob.get('/api/decisions/' + legacy.id).status_code == 404
        other = bob.post('/api/retrospectives', json=retrospective_payload(actual=80)).json()
        assert {s['decision_id'] for s in bob.get('/api/calibration').json()['samples']} == {other['id']}
    assert {s['decision_id'] for s in client.get('/api/calibration').json()['samples']} == {own['id']}


def test_workflow_calibration_and_demo_seeds_do_not_cross_users(client):
    register(client)
    for _ in range(2):
        assert client.post('/api/retrospectives', json=retrospective_payload(actual=200)).status_code == 201
    alice_ids = {row['id'] for row in client.get('/api/decisions').json()}
    with TestClient(client.app) as bob:
        bob_user = register(bob, 'Bobby').json()['user']
        decision = bob.post('/api/decisions', json=general_payload()).json()
        url = '/api/decisions/' + decision['id']
        assert bob.post(url + '/run').status_code == 202
        assert bob.post(url + '/confirm').status_code == 200
        assert bob.post(url + '/run').status_code == 202
        result = bob.get(url).json()
        assert result['status'] == 'awaiting_review'
        warnings = result['outputs']['challenging']['calibration_warnings']
        assert warnings[0]['bias_pct'] == -40  # Bob's synthetic history, not Alice's +100%.
        seeds = [row for row in bob.get('/api/decisions').json() if row['is_retrospective']]
        assert len(seeds) == 2
        assert all(client.app.state.repository.owner_of(row['id']) == bob_user['id'] for row in seeds)
        assert not alice_ids & {s['decision_id'] for s in bob.get('/api/calibration').json()['samples']}
    assert {row['id'] for row in client.get('/api/decisions').json()} == alice_ids


def test_ownership_check_precedes_live_availability(tmp_path):
    path = tmp_path / 'locked.db'
    with TestClient(create_app(path)) as demo:
        register(demo)
        decision = demo.post('/api/decisions', json=general_payload()).json()
    with TestClient(create_app(path, settings=Settings(app_mode='live'))) as locked:
        register(locked, 'Bobby')
        assert locked.post('/api/decisions/' + decision['id'] + '/run').status_code == 404
        sign_in(locked)
        assert locked.post('/api/decisions/' + decision['id'] + '/run').status_code == 503


def test_legacy_schema_migrates_without_assigning_old_data(tmp_path):
    path = tmp_path / 'legacy.db'
    with sqlite3.connect(path) as connection:
        connection.execute('''CREATE TABLE decisions (
            id VARCHAR(36) PRIMARY KEY, question TEXT NOT NULL, time_window VARCHAR(80) NOT NULL,
            budget_limit INTEGER NOT NULL, primary_goal VARCHAR(200) NOT NULL, status VARCHAR(32) NOT NULL,
            review_note TEXT, output_json TEXT NOT NULL, created_at DATETIME NOT NULL)''')
        connection.execute("INSERT INTO decisions VALUES ('legacy', '原始问题', '14 days', 8000, '原始目标', 'draft', NULL, '{}', '2026-09-01')")
    with TestClient(create_app(path)) as client:
        register(client)
        assert client.get('/api/decisions').json() == []
        assert client.get('/api/decisions/legacy').status_code == 404
        assert client.app.state.repository.owner_of('legacy') is None
        assert client.app.state.repository.get('legacy').question == '原始问题'
    # Reopening an already-migrated database is safe.
    repository = DecisionRepository(path)
    assert repository.owner_of('legacy') is None
    repository._engine.dispose()


def test_claim_legacy_cli_assigns_only_null_owners_and_reads_database_setting(client, tmp_path):
    alice = register(client).json()['user']
    repository = client.app.state.repository
    legacy = repository.create(DecisionCreate(**general_payload()))
    retrospective = repository.create_retrospective(RetrospectiveCreate(**retrospective_payload()))
    with TestClient(client.app) as bob:
        bob_user = register(bob, 'Bobby').json()['user']
        owned = bob.post('/api/decisions', json=general_payload()).json()
    environment = os.environ | {'DATABASE_URL': f'sqlite:///{tmp_path / "auth.db"}'}
    command = [sys.executable, '-m', 'app.manage', 'claim-legacy', ' aLiCe ']
    result = subprocess.run(command, cwd=Path(__file__).resolve().parents[1], env=environment, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == '已归属 2 条决策'
    assert repository.owner_of(legacy.id) == repository.owner_of(retrospective.id) == alice['id']
    assert repository.owner_of(owned['id']) == bob_user['id']
    assert {row['id'] for row in client.get('/api/decisions').json()} == {legacy.id, retrospective.id}
    again = subprocess.run(command, cwd=Path(__file__).resolve().parents[1], env=environment, capture_output=True, text=True)
    assert again.returncode == 0 and again.stdout.strip() == '已归属 0 条决策'
    missing = subprocess.run(command[:-1] + ['Missing'], cwd=Path(__file__).resolve().parents[1], env=environment, capture_output=True, text=True)
    assert missing.returncode != 0 and '用户不存在' in missing.stderr


def test_concurrent_case_variant_registrations_create_one_user(client):
    barrier = Barrier(2)

    def attempt(username):
        with TestClient(client.app) as concurrent:
            barrier.wait(timeout=5)
            return register(concurrent, username).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt, ['Alice', 'ALICE'])) == [201, 409]
    with client.app.state.repository._sessions() as session:
        assert len(session.scalars(select(UserRecord)).all()) == 1
