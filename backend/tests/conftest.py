"""All in-process tests are offline; provider I/O must use MockTransport."""
import socket

import pytest


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError('Real network access is forbidden in backend tests')
    monkeypatch.setattr(socket.socket, 'connect', blocked)
    monkeypatch.setattr(socket.socket, 'connect_ex', blocked)
    monkeypatch.setattr(socket, 'getaddrinfo', blocked)
