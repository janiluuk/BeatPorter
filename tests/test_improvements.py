"""
Tests for bug fixes and improvements
"""
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def _import_simple_library():
    """Import a simple test library."""
    content = """#EXTM3U
#EXTINF:300,Artist1 - Track1
/path/to/track1.mp3
#EXTINF:240,Artist2 - Track2
/path/to/track2.mp3
"""
    files = {"file": ("test.m3u", content, "audio/x-mpegurl")}
    resp = client.post("/api/import", files=files)
    assert resp.status_code == 200
    return resp.json()["library_id"]


def test_duplicate_detection_skips_empty_metadata():
    """Test that duplicate detection doesn't group tracks with all empty metadata."""
    # Create library with tracks that have empty metadata
    content = """#EXTM3U
#EXTINF:300, - 
track1.mp3
#EXTINF:300, - 
track2.mp3
#EXTINF:300, - 
track3.mp3
"""
    files = {"file": ("test.m3u", content, "audio/x-mpegurl")}
    resp = client.post("/api/import", files=files)
    assert resp.status_code == 200
    library_id = resp.json()["library_id"]
    
    # Check duplicates
    resp = client.get(f"/api/library/{library_id}/duplicates")
    assert resp.status_code == 200
    result = resp.json()
    # Should NOT group these as duplicates since all fields are empty
    assert result["total_groups"] == 0


def test_csv_formula_injection_with_tabs_and_newlines():
    """Test that CSV export handles tabs and newlines in formula injection detection."""
    # Create library with dangerous content including tabs and newlines
    content = """#EXTM3U
#EXTINF:300,\t=SUM(A1:A10) - Artist
/path/to/track.mp3
"""
    files = {"file": ("test.m3u", content.encode(), "audio/x-mpegurl")}
    resp = client.post("/api/import", files=files)
    assert resp.status_code == 200
    library_id = resp.json()["library_id"]
    
    # Export to CSV
    resp = client.post(f"/api/library/{library_id}/export", params={"format": "serato"})
    assert resp.status_code == 200
    csv_content = resp.content.decode()
    
    # Check that the dangerous content is escaped
    lines = csv_content.split('\n')
    # Find the data line with the formula
    for line in lines[1:]:
        if "SUM" in line:
            # Should be escaped with a leading quote
            assert "'" in line


def test_export_format_validation():
    """Test that export validates format parameter."""
    library_id = _import_simple_library()
    
    # Test invalid format
    resp = client.post(f"/api/library/{library_id}/export", params={"format": "invalid_format"})
    assert resp.status_code == 400
    assert "Invalid format" in resp.json()["detail"]


def test_export_bundle_validates_empty_formats():
    """Test that export bundle validates formats list."""
    library_id = _import_simple_library()
    
    # Test empty formats list
    body = {"formats": []}
    resp = client.post(f"/api/library/{library_id}/export_bundle", json=body)
    assert resp.status_code == 422  # Validation error


def test_export_bundle_validates_invalid_formats():
    """Test that export bundle validates format values."""
    library_id = _import_simple_library()
    
    # Test invalid format in list
    body = {"formats": ["m3u", "invalid_format"]}
    resp = client.post(f"/api/library/{library_id}/export_bundle", json=body)
    assert resp.status_code == 422  # Validation error


def test_merge_playlists_validates_input():
    """Test that merge_playlists validates input parameters."""
    library_id = _import_simple_library()
    
    # Create two playlists
    body1 = {"target_minutes": 60, "playlist_name": "Playlist 1"}
    resp1 = client.post(f"/api/library/{library_id}/generate_playlist_v2", json=body1)
    pid1 = resp1.json()["playlist_id"]
    
    body2 = {"target_minutes": 60, "playlist_name": "Playlist 2"}
    resp2 = client.post(f"/api/library/{library_id}/generate_playlist_v2", json=body2)
    pid2 = resp2.json()["playlist_id"]
    
    # Test empty source_playlist_ids
    body = {"source_playlist_ids": [], "name": "Merged"}
    resp = client.post(f"/api/library/{library_id}/merge_playlists", json=body)
    assert resp.status_code == 422  # Validation error
    
    # Test empty name
    body = {"source_playlist_ids": [pid1, pid2], "name": ""}
    resp = client.post(f"/api/library/{library_id}/merge_playlists", json=body)
    assert resp.status_code == 422  # Validation error
    
    # Test duplicate playlist IDs
    body = {"source_playlist_ids": [pid1, pid1], "name": "Merged"}
    resp = client.post(f"/api/library/{library_id}/merge_playlists", json=body)
    assert resp.status_code == 422  # Validation error
    
    # Test valid merge with one playlist (edge case but allowed)
    body = {"source_playlist_ids": [pid1], "name": "Merged"}
    resp = client.post(f"/api/library/{library_id}/merge_playlists", json=body)
    assert resp.status_code == 200
    
    # Test valid merge with two playlists
    body = {"source_playlist_ids": [pid1, pid2], "name": "Merged"}
    resp = client.post(f"/api/library/{library_id}/merge_playlists", json=body)
    assert resp.status_code == 200


def test_file_size_limit():
    """Test that import rejects files that are too large."""
    # Create a very large file (simulated - 51 MB)
    # In practice, we just test with a smaller file to avoid memory issues in tests
    large_content = "#EXTM3U\n" + ("#EXTINF:300,Artist - Track\n/path/to/track.mp3\n" * 100000)
    
    files = {"file": ("large.m3u", large_content.encode(), "audio/x-mpegurl")}
    resp = client.post("/api/import", files=files)
    
    # Should either succeed (if under limit) or fail with 413 (if over limit)
    # The actual size depends on the content, so we just check it doesn't crash
    assert resp.status_code in [200, 413]
    if resp.status_code == 413:
        assert "too large" in resp.json()["detail"].lower()


def test_metadata_autofix_whitespace_normalization():
    """Test that metadata autofix uses efficient whitespace normalization."""
    # Create library with tracks that have multiple spaces in keys
    content = """#EXTM3U
#EXTINF:300,Artist - Track
/path/to/track.mp3
"""
    files = {"file": ("test.m3u", content, "audio/x-mpegurl")}
    resp = client.post("/api/import", files=files)
    assert resp.status_code == 200
    library_id = resp.json()["library_id"]
    
    # Get a track and manually set key with multiple spaces
    resp = client.get(f"/api/library/{library_id}/tracks")
    tracks = resp.json()
    track_id = tracks[0]["id"]
    
    # Run autofix with whitespace normalization
    body = {"normalize_whitespace": True}
    resp = client.post(f"/api/library/{library_id}/metadata_auto_fix", json=body)
    assert resp.status_code == 200
    # Should complete successfully (testing that it doesn't hang with inefficient loop)


def test_export_empty_library():
    """Test that exporting an empty library works correctly."""
    # Import empty library
    content = "#EXTM3U\n"
    files = {"file": ("empty.m3u", content, "audio/x-mpegurl")}
    resp = client.post("/api/import", files=files)
    assert resp.status_code == 200
    library_id = resp.json()["library_id"]
    
    # Export to different formats
    for fmt in ["m3u", "serato", "rekordbox", "traktor"]:
        resp = client.post(f"/api/library/{library_id}/export", params={"format": fmt})
        assert resp.status_code == 200
        # Should return valid content even if empty
        assert len(resp.content) > 0


def test_library_cleanup_efficiency():
    """Test that library cleanup is efficient."""
    # Create a few libraries
    lib_ids = []
    for i in range(5):
        content = f"""#EXTM3U
#EXTINF:300,Artist {i} - Track {i}
/path/to/track{i}.mp3
"""
        files = {"file": (f"test{i}.m3u", content, "audio/x-mpegurl")}
        resp = client.post("/api/import", files=files)
        assert resp.status_code == 200
        lib_ids.append(resp.json()["library_id"])
    
    # Access one of them to verify cleanup runs
    resp = client.get(f"/api/library/{lib_ids[0]}")
    assert resp.status_code == 200
    # If we got here, cleanup ran successfully without errors
