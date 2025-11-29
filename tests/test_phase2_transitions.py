
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
#EXTINF:302,Artist Two - Second Track
/path/to/second.mp3
#EXTINF:340,Artist Three - Third Track
/path/to/third.mp3
"""
    files = {"file": ("transitions.m3u", content, "audio/x-mpegurl")}
    resp = client.post("/api/import", files=files)
    assert resp.status_code == 200
    data = resp.json()
    return data["library_id"]


def test_transitions_prefers_key_and_bpm_match():
    library_id = _import_m3u_library()
    from backend.app.main import LIBRARIES

    lib = LIBRARIES[library_id]
    # base track
    base = lib.tracks[0]
    base.bpm = 128
    base.key = "8A"

    # close match
    lib.tracks[1].bpm = 130
    lib.tracks[1].key = "8A"

    # far bpm + different key
    lib.tracks[2].bpm = 150
    lib.tracks[2].key = "10B"

    resp = client.get(
        f"/api/library/{library_id}/transitions",
        params={"from_track_id": base.id, "bpm_tolerance": 5, "max_results": 5},
    )
    assert resp.status_code == 200
    data = resp.json()
    candidates = data["candidates"]
    assert len(candidates) >= 1
    # Best candidate should be the 2nd track
    assert candidates[0]["id"] == lib.tracks[1].id
    assert candidates[0]["key_match"] is True
