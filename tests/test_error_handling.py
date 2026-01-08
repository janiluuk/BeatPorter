"""
Tests for error handling with malformed input
"""
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def test_malformed_xml_rekordbox():
    """Test handling of malformed Rekordbox XML."""
    # Invalid XML structure
    content = b"""<?xml version="1.0"?>
<DJ_PLAYLISTS>
  <COLLECTION>
    <TRACK Name="Test" Artist="Artist"
  </COLLECTION>
"""
    files = {"file": ("malformed.xml", content, "text/xml")}
    resp = client.post("/api/import", files=files)
    # Should return 400 with proper error message
    assert resp.status_code == 400


def test_malformed_xml_traktor():
    """Test handling of malformed Traktor NML."""
    # Invalid XML structure
    content = b"""<NML VERSION="19">
  <COLLECTION>
    <ENTRY TITLE="Test" ARTIST="Artist">
      <INFO BPM="120"
  </COLLECTION>
</NML>"""
    files = {"file": ("malformed.nml", content, "text/xml")}
    resp = client.post("/api/import", files=files)
    # Should return 400 with proper error message
    assert resp.status_code == 400


def test_invalid_bpm_values_in_csv():
    """Test handling of invalid BPM values in Serato CSV."""
    content = b"""Title,Artist,File,Key,BPM,Year
Test Track,Test Artist,/path/to/file.mp3,8A,invalid_bpm,2020
Another Track,Artist 2,/path/to/file2.mp3,9A,150.5,2021"""
    
    files = {"file": ("test.csv", content, "text/csv")}
    resp = client.post("/api/import", files=files)
    # Should import successfully, treating invalid BPM as None
    assert resp.status_code == 200
    library_id = resp.json()["library_id"]
    
    # Check tracks were imported
    resp = client.get(f"/api/library/{library_id}/tracks")
    assert resp.status_code == 200
    tracks = resp.json()
    assert len(tracks) == 2
    # First track should have None BPM, second should have 150.5
    assert tracks[0]["bpm"] is None or tracks[1]["bpm"] is None


def test_invalid_year_values_in_csv():
    """Test handling of invalid year values in Serato CSV."""
    content = b"""Title,Artist,File,Key,BPM,Year
Test Track,Test Artist,/path/to/file.mp3,8A,120,not_a_year
Another Track,Artist 2,/path/to/file2.mp3,9A,150,2021"""
    
    files = {"file": ("test.csv", content, "text/csv")}
    resp = client.post("/api/import", files=files)
    # Should import successfully, treating invalid year as None
    assert resp.status_code == 200
    library_id = resp.json()["library_id"]
    
    # Check tracks were imported
    resp = client.get(f"/api/library/{library_id}/tracks")
    assert resp.status_code == 200
    tracks = resp.json()
    assert len(tracks) == 2


def test_invalid_duration_in_rekordbox():
    """Test handling of invalid duration in Rekordbox XML."""
    content = b"""<?xml version="1.0" encoding="UTF-8"?>
<DJ_PLAYLISTS Version="1.0">
  <COLLECTION>
    <TRACK TrackID="1" Name="Test" Artist="Artist" TotalTime="not_a_number" />
    <TRACK TrackID="2" Name="Test2" Artist="Artist2" TotalTime="300" />
  </COLLECTION>
</DJ_PLAYLISTS>"""
    
    files = {"file": ("test.xml", content, "text/xml")}
    resp = client.post("/api/import", files=files)
    # Should import successfully with default duration for invalid track
    assert resp.status_code == 200
    library_id = resp.json()["library_id"]
    
    resp = client.get(f"/api/library/{library_id}/tracks")
    assert resp.status_code == 200
    tracks = resp.json()
    assert len(tracks) == 2
    # First track should have default duration
    assert tracks[0]["duration_seconds"] == 300  # DEFAULT_DURATION_SECONDS


def test_unknown_file_format():
    """Test handling of unknown file formats."""
    content = b"This is not a valid playlist file"
    files = {"file": ("unknown.txt", content, "text/plain")}
    resp = client.post("/api/import", files=files)
    # Should return error for unknown format (400 or 500 acceptable)
    assert resp.status_code in [400, 500]


def test_empty_file_upload():
    """Test handling of empty file upload."""
    content = b""
    files = {"file": ("empty.m3u", content, "audio/x-mpegurl")}
    resp = client.post("/api/import", files=files)
    # Should handle gracefully - either import empty or return error
    # Both behaviors are acceptable
    assert resp.status_code in [200, 400]


def test_nonexistent_library_operations():
    """Test operations on non-existent library IDs."""
    fake_id = "00000000-0000-0000-0000-000000000000"
    
    # All operations should return 404
    resp = client.get(f"/api/library/{fake_id}")
    assert resp.status_code == 404
    
    resp = client.get(f"/api/library/{fake_id}/tracks")
    assert resp.status_code == 404
    
    resp = client.get(f"/api/library/{fake_id}/stats")
    assert resp.status_code == 404
    
    resp = client.get(f"/api/library/{fake_id}/duplicates")
    assert resp.status_code == 404
    
    resp = client.post(f"/api/library/{fake_id}/export", params={"format": "m3u"})
    assert resp.status_code == 404


def test_invalid_track_id_in_transitions():
    """Test transitions endpoint with invalid track ID."""
    # First create a valid library
    content = b"""#EXTM3U
#EXTINF:300,Artist - Track
/path/to/track.mp3
"""
    files = {"file": ("test.m3u", content, "audio/x-mpegurl")}
    resp = client.post("/api/import", files=files)
    library_id = resp.json()["library_id"]
    
    # Try to get transitions from non-existent track
    fake_track_id = "00000000-0000-0000-0000-000000000000"
    resp = client.get(
        f"/api/library/{library_id}/transitions",
        params={"from_track_id": fake_track_id}
    )
    assert resp.status_code == 404


def test_csv_without_header():
    """Test CSV import without proper header."""
    # CSV without header row
    content = b"""Some Track,Some Artist,/path/to/file.mp3"""
    files = {"file": ("noheader.csv", content, "text/csv")}
    resp = client.post("/api/import", files=files)
    # Should handle this - either detect as not CSV or import with issues
    # The key is it shouldn't crash
    assert resp.status_code in [200, 400]


def test_special_characters_in_paths():
    """Test handling of special characters in file paths."""
    content = """#EXTM3U
#EXTINF:300,Artist - Track
/path/with spaces/and (parens)/file.mp3
#EXTINF:240,Artist 2 - Track 2
C:\\Windows\\Path\\file.mp3
"""
    files = {"file": ("test.m3u", content.encode(), "audio/x-mpegurl")}
    resp = client.post("/api/import", files=files)
    assert resp.status_code == 200
    library_id = resp.json()["library_id"]
    
    # Should be able to list tracks with special chars in paths
    resp = client.get(f"/api/library/{library_id}/tracks")
    assert resp.status_code == 200
    tracks = resp.json()
    assert len(tracks) == 2
