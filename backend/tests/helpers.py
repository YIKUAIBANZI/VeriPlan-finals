"""Authenticate HTTP tests through the public API, retaining real cookies."""
from functools import wraps
import runpy
import sys
from unittest.mock import patch

from fastapi.testclient import TestClient


def login(client, username='test_user', password='test-password'):
    payload = {'username': username, 'password': password}
    invite = client.app.state.settings.registration_invite_code
    response = client.post('/api/auth/register', json=payload | (
        {'invite_code': invite.get_secret_value()} if invite else {}
    ))
    if response.status_code == 409:
        response = client.post('/api/auth/login', json=payload)
    assert response.status_code in (200, 201), response.text
    return response.json()['user']


class AuthenticatedTestClient(TestClient):
    """Supply accounts to legacy script tests without bypassing authentication."""

    def __enter__(self):
        super().__enter__()
        try:
            login(self)
        except BaseException:
            super().__exit__(*sys.exc_info())
            raise
        return self


def authenticated_http(operation):
    @wraps(operation)
    def run(*args, **kwargs):
        with patch('fastapi.testclient.TestClient', AuthenticatedTestClient):
            return operation(*args, **kwargs)
    return run


if __name__ == '__main__':
    # Root scripts are outside this task's writable scope; provide their test accounts here.
    sys.argv = sys.argv[1:]
    authenticated_http(runpy.run_path)(sys.argv[0], run_name='__main__')
