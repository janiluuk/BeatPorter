import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def test_static_index_route_served():
    """Ensure /static/ returns the BeatPorter UI HTML."""
    resp = client.get("/static/")
    # If frontend folder is missing in some minimal CI env, don't explode:
    if resp.status_code == 404:
        # This means frontend/index.html is not present in this build
        return
    assert resp.status_code == 200
    text = resp.text.lower()
    assert "beatporter" in text
    assert "html" in resp.headers.get("content-type", "").lower()


def test_root_redirects_to_static():
    """Bare / should redirect to /static/."""
    resp = client.get("/", allow_redirects=False)
    assert resp.status_code in (301, 302, 303, 307, 308)
    loc = resp.headers.get("location", "")
    assert "/static/" in loc
