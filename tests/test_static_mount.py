import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def test_static_index_served():
    """Ensure /static/ returns the frontend index and HTTP 200."""
    resp = client.get("/static/")
    assert resp.status_code == 200
    # We expect the bundled UI to contain the app name somewhere in the HTML
    text = resp.text
    assert "BeatPorter" in text or "beatporter" in text.lower()
    # Content type should be HTML-ish
    assert "text/html" in resp.headers.get("content-type", "")


def test_static_index_html_direct():
    """/static/index.html should also be reachable directly."""
    resp = client.get("/static/index.html")
    assert resp.status_code == 200
    assert "BeatPorter" in resp.text or "beatporter" in resp.text.lower()
