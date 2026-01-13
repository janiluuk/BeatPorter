
import os
import sys
import zipfile
import io

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def _import_m3u_library():
    content = """#EXTM3U
#EXTINF:300,Artist One - First Track
/path/to/first.mp3
#EXTINF:360,Artist Two - Warehouse Anthem
/path/to/second.mp3
"""
    files = {"file": ("search.m3u", content, "audio/x-mpegurl")}
    resp = client.post("/api/import", files=files)
    assert resp.status_code == 200
    data = resp.json()
    return data["library_id"]


def test_global_search_returns_usage():
    library_id = _import_m3u_library()
    from backend.app.main import LIBRARIES

    lib = LIBRARIES[library_id]
    # Make an explicit playlist using the second track
    t1 = lib.tracks[1]
    pid = lib.add_playlist("Warehouse", [t1.id])

    resp = client.get(f"/api/library/{library_id}/search", params={"q": "warehouse"})
    assert resp.status_code == 200
    data = resp.json()
    results = data["results"]
    assert len(results) == 1
    assert results[0]["track"]["id"] == t1.id
    playlist_names = [p["name"] for p in results[0]["playlists"]]
    assert "Warehouse" in playlist_names


def test_export_bundle_creates_zip_with_formats():
    library_id = _import_m3u_library()

    resp = client.post(
        f"/api/library/{library_id}/export_bundle",
        json={"formats": ["m3u", "rekordbox"]},
    )
    assert resp.status_code == 200
    assert "application/zip" in resp.headers.get("content-type", "")
    buf = io.BytesIO(resp.content)
    with zipfile.ZipFile(buf, "r") as z:
        names = z.namelist()
        assert "library.m3u" in names
        assert "library_rekordbox.xml" in names


def test_export_bundle_rejects_empty_formats():
    library_id = _import_m3u_library()

    resp = client.post(
        f"/api/library/{library_id}/export_bundle",
        json={"formats": []},
    )
    assert resp.status_code == 422


def test_export_bundle_rejects_duplicate_formats():
    library_id = _import_m3u_library()

    resp = client.post(
        f"/api/library/{library_id}/export_bundle",
        json={"formats": ["m3u", "M3U"]},
    )
    assert resp.status_code == 422
