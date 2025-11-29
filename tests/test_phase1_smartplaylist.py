
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
"""
    files = {"file": ("smart.m3u", content, "audio/x-mpegurl")}
    resp = client.post("/api/import", files=files)
    assert resp.status_code == 200
    data = resp.json()
    return data["library_id"]


def test_generate_playlist_v2_filters_by_bpm_and_year():
    library_id = _import_m3u_library()
    from backend.app.main import LIBRARIES

    lib = LIBRARIES[library_id]
    lib.tracks[0].bpm = 125
    lib.tracks[0].year = 2005
    lib.tracks[1].bpm = 140
    lib.tracks[1].year = 2018

    resp = client.post(
        f"/api/library/{library_id}/generate_playlist_v2",
        json={
            "target_minutes": 10,
            "min_bpm": 130,
            "min_year": 2010,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["track_count"] == 1


def test_generate_playlist_v2_filters_by_keys_and_keyword():
    library_id = _import_m3u_library()
    from backend.app.main import LIBRARIES

    lib = LIBRARIES[library_id]
    lib.tracks[0].key = "8A"
    lib.tracks[1].key = "9A"
    lib.tracks[0].title = "Neptune Traveler"
    lib.tracks[1].title = "Warehouse Anthem"

    resp = client.post(
        f"/api/library/{library_id}/generate_playlist_v2",
        json={
            "target_minutes": 10,
            "keys": ["9a"],
            "keyword": "warehouse",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["track_count"] == 1
