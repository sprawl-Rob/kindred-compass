import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ai.credentials import MemoryStore  # noqa: E402
from app.main import create_app  # noqa: E402

H = {"X-Kindred": "1"}


class Client:
    """TestClient wrapper that always sends the CSRF header on writes."""

    def __init__(self, app):
        self.app = app
        # Keep one event loop for the client's lifetime (like the real server), so background AI runs continue.
        self.c = TestClient(app).__enter__()

    def get(self, url, **kw):
        return self.c.get(url, **kw)

    def post(self, url, json=None, **kw):
        return self.c.post(url, json=json, headers={**H, **kw.pop("headers", {})}, **kw)

    def patch(self, url, json=None, **kw):
        return self.c.patch(url, json=json, headers=H, **kw)

    def put(self, url, json=None, **kw):
        return self.c.put(url, json=json, headers=H, **kw)

    def delete(self, url, **kw):
        return self.c.delete(url, headers=H, **kw)

    def ok(self, method, url, **kw):
        r = getattr(self, method)(url, **kw)
        assert r.status_code < 400, (r.status_code, r.text)
        return r.json()


@pytest.fixture
def data_dir(tmp_path):
    return tmp_path / "data"


@pytest.fixture
def creds():
    return MemoryStore()


@pytest.fixture
def make_client(data_dir, creds):
    def _make(load_demo=False, factories=None):
        return Client(create_app(data_dir, creds=creds, ai_factories=factories, load_demo=load_demo))
    return _make


@pytest.fixture
def client(make_client):
    return make_client()


@pytest.fixture
def project(client):
    return client.ok("post", "/api/projects", json={"name": "Test project"})


def by_name(groups, name):
    for g, items in groups.items():
        for c in items:
            if c["name"] == name:
                return g, c
    return None, None
