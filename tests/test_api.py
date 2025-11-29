
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def _import_m3u_library():
    content = """#EXTM3U
#EXTINF:300,Artist One - First Track
/path/to/first.mp3
#EXTINF:240,Artist Two - Second Track
/path/to/second.mp3
"""
    files = {"file": ("test.m3u", content, "audio/x-mpegurl")}
    resp = client.post("/api/import", files=files)
    assert resp.status_code == 200
    data = resp.json()
    return data["library_id"], data


def test_import_m3u_and_list_tracks():
    library_id, meta = _import_m3u_library()
    assert meta["track_count"] == 2
    resp = client.get(f"/api/library/{library_id}/tracks")
    assert resp.status_code == 200
    tracks = resp.json()
    assert len(tracks) == 2
    titles = {t["title"] for t in tracks}
    assert "First Track" in titles
    assert "Second Track" in titles


def test_export_m3u_and_rekordbox_and_traktor():
    library_id, _ = _import_m3u_library()

    resp = client.post(f"/api/library/{library_id}/export", params={"format": "m3u"})
    assert resp.status_code == 200
    assert resp.content.startswith(b"#EXTM3U")

    resp = client.post(f"/api/library/{library_id}/export", params={"format": "rekordbox"})
    assert resp.status_code == 200
    text = resp.content.decode()
    assert "<DJ_PLAYLISTS" in text

    resp = client.post(f"/api/library/{library_id}/export", params={"format": "traktor"})
    assert resp.status_code == 200
    text = resp.content.decode()
    assert "<NML" in text
