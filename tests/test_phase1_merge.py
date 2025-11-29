
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
#EXTINF:360,Artist Two - Second Track
/path/to/second.mp3
#EXTINF:420,Artist Three - Third Track
/path/to/third.mp3
"""
    files = {"file": ("merge.m3u", content, "audio/x-mpegurl")}
    resp = client.post("/api/import", files=files)
    assert resp.status_code == 200
    data = resp.json()
    return data["library_id"]


def test_merge_playlists_deduplicates_tracks():
    library_id = _import_m3u_library()
    from backend.app.main import LIBRARIES

    lib = LIBRARIES[library_id]
    ids = [t.id for t in lib.tracks]
    p1 = lib.add_playlist("P1", ids[:2])
    p2 = lib.add_playlist("P2", ids[1:])

    resp = client.post(
        f"/api/library/{library_id}/merge_playlists",
        json={
            "source_playlist_ids": [p1, p2],
            "name": "Merged",
            "deduplicate": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["track_count"] == len(set(ids))


def test_merge_playlists_missing_source_404():
    library_id = _import_m3u_library()

    resp = client.post(
        f"/api/library/{library_id}/merge_playlists",
        json={
            "source_playlist_ids": ["nope"],
            "name": "Merged",
            "deduplicate": True,
        },
    )
    assert resp.status_code == 404
