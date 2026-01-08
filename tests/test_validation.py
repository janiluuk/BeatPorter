"""
Tests for input validation and edge cases
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
#EXTINF:300,Artist - Track
/path/to/track.mp3
"""
    files = {"file": ("test.m3u", content, "audio/x-mpegurl")}
    resp = client.post("/api/import", files=files)
    assert resp.status_code == 200
    return resp.json()["library_id"]


def test_smart_playlist_validates_target_minutes():
    """Test that target_minutes is validated."""
    library_id = _import_simple_library()
    
    # Test too small
    body = {"target_minutes": 0}
    resp = client.post(f"/api/library/{library_id}/generate_playlist_v2", json=body)
    assert resp.status_code == 422  # Validation error
    
    # Test too large
    body = {"target_minutes": 2000}
    resp = client.post(f"/api/library/{library_id}/generate_playlist_v2", json=body)
    assert resp.status_code == 422  # Validation error
    
    # Test valid
    body = {"target_minutes": 60}
    resp = client.post(f"/api/library/{library_id}/generate_playlist_v2", json=body)
    assert resp.status_code == 200


def test_smart_playlist_validates_bpm_range():
    """Test that BPM range is validated."""
    library_id = _import_simple_library()
    
    # Test negative BPM
    body = {"min_bpm": -10, "target_minutes": 60}
    resp = client.post(f"/api/library/{library_id}/generate_playlist_v2", json=body)
    assert resp.status_code == 422  # Validation error
    
    # Test excessive BPM
    body = {"max_bpm": 1000, "target_minutes": 60}
    resp = client.post(f"/api/library/{library_id}/generate_playlist_v2", json=body)
    assert resp.status_code == 422  # Validation error
    
    # Test min > max
    body = {"min_bpm": 150, "max_bpm": 100, "target_minutes": 60}
    resp = client.post(f"/api/library/{library_id}/generate_playlist_v2", json=body)
    assert resp.status_code == 422  # Validation error


def test_smart_playlist_validates_year_range():
    """Test that year range is validated."""
    library_id = _import_simple_library()
    
    # Test invalid year
    body = {"min_year": 1800, "target_minutes": 60}
    resp = client.post(f"/api/library/{library_id}/generate_playlist_v2", json=body)
    assert resp.status_code == 422  # Validation error
    
    # Test min > max
    body = {"min_year": 2020, "max_year": 2010, "target_minutes": 60}
    resp = client.post(f"/api/library/{library_id}/generate_playlist_v2", json=body)
    assert resp.status_code == 422  # Validation error


def test_smart_playlist_validates_sort_by():
    """Test that sort_by parameter is validated."""
    library_id = _import_simple_library()
    
    # Test invalid sort
    body = {"sort_by": "invalid", "target_minutes": 60}
    resp = client.post(f"/api/library/{library_id}/generate_playlist_v2", json=body)
    assert resp.status_code == 422  # Validation error
    
    # Test valid sorts
    for sort in ["bpm", "year", "key", "random"]:
        body = {"sort_by": sort, "target_minutes": 60}
        resp = client.post(f"/api/library/{library_id}/generate_playlist_v2", json=body)
        assert resp.status_code == 200


def test_transitions_validates_parameters():
    """Test that transitions endpoint validates parameters."""
    library_id = _import_simple_library()
    
    # Get a track ID
    resp = client.get(f"/api/library/{library_id}/tracks")
    tracks = resp.json()
    track_id = tracks[0]["id"]
    
    # Test negative bpm_tolerance
    resp = client.get(
        f"/api/library/{library_id}/transitions",
        params={"from_track_id": track_id, "bpm_tolerance": -5}
    )
    assert resp.status_code == 422  # Validation error
    
    # Test excessive bpm_tolerance
    resp = client.get(
        f"/api/library/{library_id}/transitions",
        params={"from_track_id": track_id, "bpm_tolerance": 100}
    )
    assert resp.status_code == 422  # Validation error
    
    # Test invalid max_results
    resp = client.get(
        f"/api/library/{library_id}/transitions",
        params={"from_track_id": track_id, "max_results": 0}
    )
    assert resp.status_code == 422  # Validation error
    
    # Test excessive max_results
    resp = client.get(
        f"/api/library/{library_id}/transitions",
        params={"from_track_id": track_id, "max_results": 200}
    )
    assert resp.status_code == 422  # Validation error


def test_search_validates_query():
    """Test that search endpoint validates query parameter."""
    library_id = _import_simple_library()
    
    # Test empty query
    resp = client.get(f"/api/library/{library_id}/search", params={"q": ""})
    assert resp.status_code == 400  # Bad request


def test_path_rewrite_validates_search():
    """Test that path rewrite validates search parameter."""
    library_id = _import_simple_library()
    
    # Test empty search
    body = {"search": "", "replace": "/new/path"}
    resp = client.post(f"/api/library/{library_id}/preview_rewrite_paths", json=body)
    assert resp.status_code == 400  # Bad request
    
    resp = client.post(f"/api/library/{library_id}/apply_rewrite_paths", json=body)
    assert resp.status_code == 400  # Bad request


def test_library_cleanup_and_deletion():
    """Test library cleanup mechanism."""
    library_id = _import_simple_library()
    
    # Should exist
    resp = client.get(f"/api/library/{library_id}")
    assert resp.status_code == 200
    
    # Delete it
    resp = client.delete(f"/api/library/{library_id}")
    assert resp.status_code == 200
    assert resp.json()["library_id"] == library_id
    
    # Should not exist anymore
    resp = client.get(f"/api/library/{library_id}")
    assert resp.status_code == 404


def test_empty_library_edge_cases():
    """Test edge cases with empty libraries."""
    # Import empty M3U
    content = "#EXTM3U\n"
    files = {"file": ("empty.m3u", content, "audio/x-mpegurl")}
    resp = client.post("/api/import", files=files)
    assert resp.status_code == 200
    library_id = resp.json()["library_id"]
    assert resp.json()["track_count"] == 0
    
    # Stats should work with empty library
    resp = client.get(f"/api/library/{library_id}/stats")
    assert resp.status_code == 200
    stats = resp.json()
    assert stats["track_count"] == 0
    assert stats["bpm"]["min"] is None
    assert stats["bpm"]["max"] is None
    
    # Health should work with empty library
    resp = client.get(f"/api/library/{library_id}/health")
    assert resp.status_code == 200
    
    # Duplicates should work with empty library
    resp = client.get(f"/api/library/{library_id}/duplicates")
    assert resp.status_code == 200
    assert resp.json()["total_groups"] == 0


def test_missing_metadata_edge_cases():
    """Test handling of tracks with missing metadata."""
    # Create library with tracks missing various metadata
    content = """#EXTM3U
#EXTINF:300, - 
/path/to/track1.mp3
#EXTINF:0,Artist - 
/path/to/track2.mp3
"""
    files = {"file": ("test.m3u", content, "audio/x-mpegurl")}
    resp = client.post("/api/import", files=files)
    assert resp.status_code == 200
    library_id = resp.json()["library_id"]
    
    # Metadata issues should detect the problems
    resp = client.get(f"/api/library/{library_id}/metadata_issues")
    assert resp.status_code == 200
    issues = resp.json()["issues"]
    assert len(issues["empty_title"]) > 0 or len(issues["empty_artist"]) > 0
    
    # Stats should handle missing data gracefully
    resp = client.get(f"/api/library/{library_id}/stats")
    assert resp.status_code == 200
    
    # Smart playlist should handle missing data
    body = {"target_minutes": 60, "min_bpm": 120}
    resp = client.post(f"/api/library/{library_id}/generate_playlist_v2", json=body)
    assert resp.status_code == 200
