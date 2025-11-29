
import os
import sys
import copy

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
    files = {"file": ("dup.m3u", content, "audio/x-mpegurl")}
    resp = client.post("/api/import", files=files)
    assert resp.status_code == 200
    data = resp.json()
    return data["library_id"]


def test_duplicates_empty_for_clean_library():
    library_id = _import_m3u_library()
    resp = client.get(f"/api/library/{library_id}/duplicates")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_groups"] == 0
    assert data["duplicate_groups"] == []


def test_duplicates_detect_simple_clone():
    library_id = _import_m3u_library()
    from backend.app.main import LIBRARIES

    lib = LIBRARIES[library_id]
    first = lib.tracks[0]
    clone = copy.copy(first)
    clone.id = first.id + "_dup"
    lib.tracks.append(clone)

    resp = client.get(f"/api/library/{library_id}/duplicates")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_groups"] == 1
    group = data["duplicate_groups"][0]
    assert first.id in group["track_ids"]
    assert clone.id in group["track_ids"]
    assert group["count"] == 2
