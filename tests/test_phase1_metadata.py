
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def _import_m3u_library():
    content = """#EXTM3U
#EXTINF:300,Artist One -  First Track  
/path/to/first.mp3
#EXTINF:240,  ,  
/path/to/second.mp3
"""
    files = {"file": ("meta.m3u", content, "audio/x-mpegurl")}
    resp = client.post("/api/import", files=files)
    assert resp.status_code == 200
    data = resp.json()
    return data["library_id"]


def test_metadata_issues_and_autofix():
    library_id = _import_m3u_library()
    from backend.app.main import LIBRARIES

    lib = LIBRARIES[library_id]
    t0 = lib.tracks[0]
    t0.bpm = None
    t0.key = "  8a "
    t0.year = 0

    t1 = lib.tracks[1]
    t1.bpm = 400
    t1.key = ""
    t1.year = -1
    t1.file_path = None
    t1.title = "   "
    t1.artist = ""

    resp = client.get(f"/api/library/{library_id}/metadata_issues")
    assert resp.status_code == 200
    issues = resp.json()["issues"]
    assert t0.id in issues["missing_bpm"]
    assert t0.id in issues["missing_year"]
    assert t1.id in issues["suspicious_bpm"]
    assert t1.id in issues["missing_key"]
    assert t1.id in issues["missing_file_path"]
    assert t1.id in issues["empty_title"]
    assert t1.id in issues["empty_artist"]

    resp = client.post(
        f"/api/library/{library_id}/metadata_auto_fix",
        json={
            "normalize_whitespace": True,
            "upper_case_keys": True,
            "zero_year_to_null": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["changed_tracks"] >= 1

    assert t0.key == "8A"
    assert t0.year is None
