
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient

from backend.app.main import app, LIBRARIES

client = TestClient(app)


def _import_basic_library():
    content = """#EXTM3U
#EXTINF:180,Artist One - A Track
/C:/music/one.mp3
#EXTINF:420,Artist Two - Second
/C:/music/two.wav
#EXTINF:20,Mystery - Very Short
C:/weird/path/file.txt
"""
    files = {"file": ("stats.m3u", content, "audio/x-mpegurl")}
    resp = client.post("/api/import", files=files)
    assert resp.status_code == 200
    data = resp.json()
    return data["library_id"]


def test_stats_endpoint_returns_reasonable_aggregates():
    library_id = _import_basic_library()
    lib = LIBRARIES[library_id]

    # Add some metadata so stats have content
    lib.tracks[0].bpm = 128
    lib.tracks[0].year = 2005
    lib.tracks[0].key = "8A"
    lib.tracks[0].artist = "Artist One"

    lib.tracks[1].bpm = 132
    lib.tracks[1].year = 2010
    lib.tracks[1].key = "9A"
    lib.tracks[1].artist = "Artist Two"

    # Leave third track without bpm/year to test robustness
    resp = client.get(f"/api/library/{library_id}/stats")
    assert resp.status_code == 200
    stats = resp.json()

    assert stats["track_count"] == 3
    assert stats["playlist_count"] >= 1

    bpm = stats["bpm"]
    assert bpm["min"] == 128
    assert bpm["max"] == 132
    # avg of 128 and 132 is 130.0
    assert bpm["avg"] == 130.0

    year = stats["year"]
    assert year["min"] == 2005
    assert year["max"] == 2010

    # keys distribution
    keys = stats["keys"]
    assert keys["8A"] == 1
    assert keys["9A"] == 1

    # top artists should contain the ones we set
    names = {a["artist"] for a in stats["top_artists"]}
    assert "Artist One" in names
    assert "Artist Two" in names

    # duration stats should reflect non-zero total
    assert stats["duration"]["total_minutes"] > 0


def test_health_endpoint_flags_suspicious_tracks():
    library_id = _import_basic_library()
    lib = LIBRARIES[library_id]

    # First track: normal
    lib.tracks[0].bpm = 128
    lib.tracks[0].year = 2010
    lib.tracks[0].duration_seconds = 180

    # Second track: weird bpm and weird year and unknown extension
    lib.tracks[1].file_path = "/music/oddfile.xyz"
    lib.tracks[1].bpm = 250
    lib.tracks[1].year = 2100
    lib.tracks[1].duration_seconds = 400

    # Third track: very short, missing file_path
    lib.tracks[2].file_path = ""
    lib.tracks[2].bpm = 50
    lib.tracks[2].year = 1900
    lib.tracks[2].duration_seconds = 20

    resp = client.get(f"/api/library/{library_id}/health")
    assert resp.status_code == 200
    data = resp.json()
    issues = data["issues"]

    # Check issue categories exist
    for k in [
        "missing_file_path",
        "unknown_extension",
        "very_short_duration",
        "unusual_bpm",
        "unusual_year",
    ]:
        assert k in issues

    # Second track should be marked for unknown_extension, unusual_bpm, unusual_year
    t1 = lib.tracks[1].id
    assert t1 in issues["unknown_extension"]
    assert t1 in issues["unusual_bpm"]
    assert t1 in issues["unusual_year"]

    # Third track should be marked missing_file_path, very_short_duration, unusual_bpm, unusual_year
    t2 = lib.tracks[2].id
    assert t2 in issues["missing_file_path"]
    assert t2 in issues["very_short_duration"]
    assert t2 in issues["unusual_bpm"]
    assert t2 in issues["unusual_year"]
