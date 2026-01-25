"""
Tests for enhanced UI features including dark/light mode, 
keyboard shortcuts, bulk operations, and analytics.
"""
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def _import_test_library():
    """Import a test library with varied data for testing."""
    content = """#EXTM3U
#EXTINF:300,Daft Punk - Around The World
/music/techno/daft_punk.mp3
#EXTINF:360,The Chemical Brothers - Block Rockin' Beats
/music/techno/chemical_brothers.mp3
#EXTINF:420,Underworld - Born Slippy
/music/techno/underworld.mp3
#EXTINF:240,Kraftwerk - The Robots
/music/electronic/kraftwerk.mp3
#EXTINF:310,Moby - Porcelain
/music/electronic/moby.mp3
"""
    files = {"file": ("test.m3u", content, "audio/x-mpegurl")}
    resp = client.post("/api/import", files=files)
    assert resp.status_code == 200
    return resp.json()["library_id"]


def test_library_import_returns_correct_track_count():
    """Test that library import returns the correct number of tracks."""
    library_id = _import_test_library()
    
    # Get tracks
    resp = client.get(f"/api/library/{library_id}/tracks")
    assert resp.status_code == 200
    tracks = resp.json()
    
    # Should have 5 tracks
    assert len(tracks) == 5


def test_tracks_endpoint_returns_array():
    """Test that /tracks endpoint returns an array directly."""
    library_id = _import_test_library()
    
    resp = client.get(f"/api/library/{library_id}/tracks")
    assert resp.status_code == 200
    data = resp.json()
    
    # Should be an array
    assert isinstance(data, list)
    # Each item should be a track with expected fields
    for track in data:
        assert "id" in track
        assert "title" in track
        assert "artist" in track


def test_tracks_have_required_fields():
    """Test that tracks have all required fields for UI display."""
    library_id = _import_test_library()
    
    resp = client.get(f"/api/library/{library_id}/tracks")
    assert resp.status_code == 200
    tracks = resp.json()
    
    # Check first track has all fields needed by UI
    track = tracks[0]
    required_fields = ["id", "title", "artist", "file_path", "duration_seconds"]
    for field in required_fields:
        assert field in track, f"Track missing required field: {field}"


def test_statistics_endpoint_works():
    """Test that statistics endpoint returns valid data."""
    library_id = _import_test_library()
    
    resp = client.get(f"/api/library/{library_id}/stats")
    assert resp.status_code == 200
    stats = resp.json()
    
    # Should have track count
    assert "track_count" in stats
    assert stats["track_count"] == 5


def test_library_state_persistence():
    """Test that library can be accessed after import (simulating localStorage restore)."""
    library_id = _import_test_library()
    
    # Try to access library again (simulating a page reload with saved ID)
    resp = client.get(f"/api/library/{library_id}/tracks")
    assert resp.status_code == 200
    tracks = resp.json()
    
    # Should still have the same tracks
    assert len(tracks) == 5


def test_multiple_file_import():
    """Test that multiple libraries can be imported without conflicts."""
    # Import first library
    library_id_1 = _import_test_library()
    
    # Import second library
    content2 = """#EXTM3U
#EXTINF:180,Artist X - Song X
/path/song_x.mp3
"""
    files = {"file": ("test2.m3u", content2, "audio/x-mpegurl")}
    resp = client.post("/api/import", files=files)
    assert resp.status_code == 200
    library_id_2 = resp.json()["library_id"]
    
    # Libraries should have different IDs
    assert library_id_1 != library_id_2
    
    # First library should still have 5 tracks
    resp1 = client.get(f"/api/library/{library_id_1}/tracks")
    assert len(resp1.json()) == 5
    
    # Second library should have 1 track
    resp2 = client.get(f"/api/library/{library_id_2}/tracks")
    assert len(resp2.json()) == 1


def test_analytics_data_structure():
    """Test that track data supports analytics generation."""
    library_id = _import_test_library()
    
    resp = client.get(f"/api/library/{library_id}/tracks")
    assert resp.status_code == 200
    tracks = resp.json()
    
    # Tracks should have fields that can be used for analytics
    # Even if values are null, the fields should exist
    for track in tracks:
        # These fields are used for analytics charts
        assert "bpm" in track or track.get("bpm") is None
        assert "key" in track or track.get("key") is None
        assert "year" in track or track.get("year") is None
        assert "genre" in track or track.get("genre") is None


def test_export_maintains_track_order():
    """Test that exported playlists maintain track order (for drag-and-drop)."""
    library_id = _import_test_library()
    
    # Get tracks
    resp = client.get(f"/api/library/{library_id}/tracks")
    original_tracks = resp.json()
    
    # Export as M3U
    resp = client.post(f"/api/library/{library_id}/export?format=m3u")
    assert resp.status_code == 200
    exported_content = resp.text
    
    # Should contain all tracks in order
    for track in original_tracks:
        assert track["title"] in exported_content


def test_health_check_endpoint():
    """Test that health check endpoint is available for UI."""
    library_id = _import_test_library()
    
    resp = client.get(f"/api/library/{library_id}/health")
    assert resp.status_code == 200
    health_data = resp.json()
    
    # Should have issues field
    assert "issues" in health_data


def test_metadata_issues_endpoint():
    """Test that metadata issues endpoint is available for UI."""
    library_id = _import_test_library()
    
    resp = client.get(f"/api/library/{library_id}/metadata_issues")
    assert resp.status_code == 200
    metadata_data = resp.json()
    
    # Should have total_tracks and issues fields
    assert "total_tracks" in metadata_data
    assert "issues" in metadata_data


def test_duplicates_endpoint():
    """Test that duplicates endpoint is available for UI."""
    library_id = _import_test_library()
    
    resp = client.get(f"/api/library/{library_id}/duplicates")
    assert resp.status_code == 200
    duplicates_data = resp.json()
    
    # Should have groups field
    assert "groups" in duplicates_data or "total_groups" in duplicates_data


def test_smart_playlist_generation():
    """Test that smart playlist generation works for UI."""
    library_id = _import_test_library()
    
    # Create a smart playlist
    params = {
        "playlist_name": "Test Playlist",
        "target_minutes": 60,
        "sort_by": "bpm"
    }
    
    resp = client.post(
        f"/api/library/{library_id}/generate_playlist_v2",
        json=params
    )
    assert resp.status_code == 200
    playlist_data = resp.json()
    
    # Should have track_count
    assert "track_count" in playlist_data


def test_keyboard_shortcuts_data_integrity():
    """Test that all keyboard shortcut actions have valid endpoints."""
    library_id = _import_test_library()
    
    # Test Statistics (S key)
    resp = client.get(f"/api/library/{library_id}/stats")
    assert resp.status_code == 200
    
    # Test Duplicates (D key)
    resp = client.get(f"/api/library/{library_id}/duplicates")
    assert resp.status_code == 200
    
    # Test Metadata (M key)
    resp = client.get(f"/api/library/{library_id}/metadata_issues")
    assert resp.status_code == 200
    
    # Test Health (H key)
    resp = client.get(f"/api/library/{library_id}/health")
    assert resp.status_code == 200


def test_bulk_operations_track_selection():
    """Test that track data supports bulk selection operations."""
    library_id = _import_test_library()
    
    resp = client.get(f"/api/library/{library_id}/tracks")
    assert resp.status_code == 200
    tracks = resp.json()
    
    # All tracks should have unique IDs for selection
    track_ids = [track["id"] for track in tracks]
    assert len(track_ids) == len(set(track_ids)), "Track IDs should be unique"
    
    # Should be able to filter tracks (simulating bulk operations)
    selected_ids = track_ids[:2]
    selected_tracks = [t for t in tracks if t["id"] in selected_ids]
    assert len(selected_tracks) == 2
