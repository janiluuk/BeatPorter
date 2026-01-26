"""
Tests for playlist folders and custom metadata features.
"""
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def _import_test_library():
    """Import a test library."""
    content = """#EXTM3U
#EXTINF:300,Artist One - Track One
/path/to/track1.mp3
#EXTINF:240,Artist Two - Track Two
/path/to/track2.mp3
#EXTINF:360,Artist Three - Track Three
/path/to/track3.mp3
"""
    files = {"file": ("test.m3u", content, "audio/x-mpegurl")}
    resp = client.post("/api/import", files=files)
    assert resp.status_code == 200
    return resp.json()["library_id"]


# ===== Folder Tests =====

def test_create_root_folder():
    """Test creating a root-level folder."""
    library_id = _import_test_library()
    
    resp = client.post(
        f"/api/library/{library_id}/folders",
        json={"name": "Electronic Music"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Electronic Music"
    assert data["parent_id"] is None
    assert "folder_id" in data


def test_create_nested_folder():
    """Test creating a folder inside another folder."""
    library_id = _import_test_library()
    
    # Create parent folder
    resp1 = client.post(
        f"/api/library/{library_id}/folders",
        json={"name": "Electronic"}
    )
    assert resp1.status_code == 200
    parent_id = resp1.json()["folder_id"]
    
    # Create child folder
    resp2 = client.post(
        f"/api/library/{library_id}/folders",
        json={"name": "Techno", "parent_id": parent_id}
    )
    assert resp2.status_code == 200
    data = resp2.json()
    assert data["name"] == "Techno"
    assert data["parent_id"] == parent_id


def test_get_folder_hierarchy():
    """Test retrieving folder hierarchy."""
    library_id = _import_test_library()
    
    # Create folders
    resp1 = client.post(
        f"/api/library/{library_id}/folders",
        json={"name": "Electronic"}
    )
    parent_id = resp1.json()["folder_id"]
    
    client.post(
        f"/api/library/{library_id}/folders",
        json={"name": "Techno", "parent_id": parent_id}
    )
    
    # Get hierarchy
    resp = client.get(f"/api/library/{library_id}/folders")
    assert resp.status_code == 200
    data = resp.json()
    assert "folders" in data
    assert "playlists" in data
    assert len(data["folders"]) > 0
    assert data["folders"][0]["name"] == "Electronic"
    assert len(data["folders"][0]["subfolders"]) == 1
    assert data["folders"][0]["subfolders"][0]["name"] == "Techno"


def test_delete_folder():
    """Test deleting a folder."""
    library_id = _import_test_library()
    
    resp1 = client.post(
        f"/api/library/{library_id}/folders",
        json={"name": "Test Folder"}
    )
    folder_id = resp1.json()["folder_id"]
    
    resp2 = client.delete(f"/api/library/{library_id}/folders/{folder_id}")
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "deleted"
    
    # Verify folder is gone
    resp3 = client.get(f"/api/library/{library_id}/folders")
    assert resp3.status_code == 200
    assert len(resp3.json()["folders"]) == 0


def test_move_folder():
    """Test moving a folder to a different parent."""
    library_id = _import_test_library()
    
    # Create folders
    resp1 = client.post(
        f"/api/library/{library_id}/folders",
        json={"name": "Parent 1"}
    )
    parent1_id = resp1.json()["folder_id"]
    
    resp2 = client.post(
        f"/api/library/{library_id}/folders",
        json={"name": "Parent 2"}
    )
    parent2_id = resp2.json()["folder_id"]
    
    resp3 = client.post(
        f"/api/library/{library_id}/folders",
        json={"name": "Child", "parent_id": parent1_id}
    )
    child_id = resp3.json()["folder_id"]
    
    # Move child from parent1 to parent2
    resp4 = client.post(
        f"/api/library/{library_id}/folders/{child_id}/move",
        json={"new_parent_id": parent2_id}
    )
    assert resp4.status_code == 200
    assert resp4.json()["new_parent_id"] == parent2_id
    
    # Verify hierarchy
    resp5 = client.get(f"/api/library/{library_id}/folders")
    data = resp5.json()
    parent2_folder = [f for f in data["folders"] if f["id"] == parent2_id][0]
    assert len(parent2_folder["subfolders"]) == 1
    assert parent2_folder["subfolders"][0]["name"] == "Child"


def test_move_folder_circular_reference():
    """Test that moving a folder into its own subfolder is prevented."""
    library_id = _import_test_library()
    
    resp1 = client.post(
        f"/api/library/{library_id}/folders",
        json={"name": "Parent"}
    )
    parent_id = resp1.json()["folder_id"]
    
    resp2 = client.post(
        f"/api/library/{library_id}/folders",
        json={"name": "Child", "parent_id": parent_id}
    )
    child_id = resp2.json()["folder_id"]
    
    # Try to move parent into child (should fail)
    resp3 = client.post(
        f"/api/library/{library_id}/folders/{parent_id}/move",
        json={"new_parent_id": child_id}
    )
    assert resp3.status_code == 400


def test_move_playlist_to_folder():
    """Test moving a playlist to a folder."""
    library_id = _import_test_library()
    
    # Create folder
    resp1 = client.post(
        f"/api/library/{library_id}/folders",
        json={"name": "My Folder"}
    )
    folder_id = resp1.json()["folder_id"]
    
    # Create playlist (using existing generate_playlist_v2 endpoint)
    resp2 = client.post(
        f"/api/library/{library_id}/generate_playlist_v2",
        json={"playlist_name": "Test Playlist", "target_minutes": 30}
    )
    assert resp2.status_code == 200
    playlist_id = resp2.json()["playlist_id"]
    
    # Move playlist to folder
    resp3 = client.post(
        f"/api/library/{library_id}/playlists/{playlist_id}/move",
        json={"folder_id": folder_id}
    )
    assert resp3.status_code == 200
    assert resp3.json()["folder_id"] == folder_id
    
    # Verify in hierarchy
    resp4 = client.get(f"/api/library/{library_id}/folders")
    data = resp4.json()
    my_folder = [f for f in data["folders"] if f["id"] == folder_id][0]
    assert len(my_folder["playlists"]) == 1
    assert my_folder["playlists"][0]["name"] == "Test Playlist"


# ===== Custom Metadata and Tags Tests =====

def test_update_track_custom_fields():
    """Test adding custom metadata fields to a track."""
    library_id = _import_test_library()
    
    # Get a track
    resp1 = client.get(f"/api/library/{library_id}/tracks")
    tracks = resp1.json()
    track_id = tracks[0]["id"]
    
    # Add custom fields
    resp2 = client.post(
        f"/api/library/{library_id}/tracks/{track_id}/custom_fields",
        json={"custom_fields": {"energy": 8, "mood": "uplifting", "rating": 4.5}}
    )
    assert resp2.status_code == 200
    data = resp2.json()
    assert data["custom_fields"]["energy"] == 8
    assert data["custom_fields"]["mood"] == "uplifting"
    assert data["custom_fields"]["rating"] == 4.5


def test_get_track_custom_fields():
    """Test retrieving custom metadata fields."""
    library_id = _import_test_library()
    
    resp1 = client.get(f"/api/library/{library_id}/tracks")
    track_id = resp1.json()[0]["id"]
    
    # Set custom fields
    client.post(
        f"/api/library/{library_id}/tracks/{track_id}/custom_fields",
        json={"custom_fields": {"danceability": 9}}
    )
    
    # Get custom fields
    resp2 = client.get(f"/api/library/{library_id}/tracks/{track_id}/custom_fields")
    assert resp2.status_code == 200
    assert resp2.json()["custom_fields"]["danceability"] == 9


def test_update_track_tags():
    """Test adding tags to a track."""
    library_id = _import_test_library()
    
    resp1 = client.get(f"/api/library/{library_id}/tracks")
    track_id = resp1.json()[0]["id"]
    
    # Add tags
    resp2 = client.post(
        f"/api/library/{library_id}/tracks/{track_id}/tags",
        json={"tags": ["peak-time", "driving", "melodic"]}
    )
    assert resp2.status_code == 200
    assert "peak-time" in resp2.json()["tags"]
    assert "driving" in resp2.json()["tags"]
    assert "melodic" in resp2.json()["tags"]


def test_get_track_tags():
    """Test retrieving tags for a track."""
    library_id = _import_test_library()
    
    resp1 = client.get(f"/api/library/{library_id}/tracks")
    track_id = resp1.json()[0]["id"]
    
    # Set tags
    client.post(
        f"/api/library/{library_id}/tracks/{track_id}/tags",
        json={"tags": ["techno", "hypnotic"]}
    )
    
    # Get tags
    resp2 = client.get(f"/api/library/{library_id}/tracks/{track_id}/tags")
    assert resp2.status_code == 200
    assert set(resp2.json()["tags"]) == {"techno", "hypnotic"}


def test_get_all_tags():
    """Test retrieving all unique tags in the library."""
    library_id = _import_test_library()
    
    resp1 = client.get(f"/api/library/{library_id}/tracks")
    tracks = resp1.json()
    
    # Add tags to multiple tracks
    client.post(
        f"/api/library/{library_id}/tracks/{tracks[0]['id']}/tags",
        json={"tags": ["techno", "peak-time"]}
    )
    client.post(
        f"/api/library/{library_id}/tracks/{tracks[1]['id']}/tags",
        json={"tags": ["house", "groovy"]}
    )
    client.post(
        f"/api/library/{library_id}/tracks/{tracks[2]['id']}/tags",
        json={"tags": ["techno", "dark"]}
    )
    
    # Get all tags
    resp2 = client.get(f"/api/library/{library_id}/tags")
    assert resp2.status_code == 200
    tags = resp2.json()["tags"]
    assert "techno" in tags
    assert "house" in tags
    assert "peak-time" in tags
    assert "groovy" in tags
    assert "dark" in tags


def test_get_custom_field_keys():
    """Test retrieving all custom field keys in the library."""
    library_id = _import_test_library()
    
    resp1 = client.get(f"/api/library/{library_id}/tracks")
    tracks = resp1.json()
    
    # Add custom fields to multiple tracks
    client.post(
        f"/api/library/{library_id}/tracks/{tracks[0]['id']}/custom_fields",
        json={"custom_fields": {"energy": 8, "rating": 4}}
    )
    client.post(
        f"/api/library/{library_id}/tracks/{tracks[1]['id']}/custom_fields",
        json={"custom_fields": {"mood": "happy", "rating": 5}}
    )
    
    # Get all custom field keys
    resp2 = client.get(f"/api/library/{library_id}/custom_field_keys")
    assert resp2.status_code == 200
    keys = resp2.json()["custom_field_keys"]
    assert "energy" in keys
    assert "rating" in keys
    assert "mood" in keys


def test_tracks_include_custom_fields_and_tags():
    """Test that /tracks endpoint includes custom fields and tags."""
    library_id = _import_test_library()
    
    resp1 = client.get(f"/api/library/{library_id}/tracks")
    track_id = resp1.json()[0]["id"]
    
    # Add custom fields and tags
    client.post(
        f"/api/library/{library_id}/tracks/{track_id}/custom_fields",
        json={"custom_fields": {"energy": 9}}
    )
    client.post(
        f"/api/library/{library_id}/tracks/{track_id}/tags",
        json={"tags": ["favorite"]}
    )
    
    # Get tracks again
    resp2 = client.get(f"/api/library/{library_id}/tracks")
    track = [t for t in resp2.json() if t["id"] == track_id][0]
    
    assert "custom_fields" in track
    assert "tags" in track
    assert track["custom_fields"]["energy"] == 9
    assert "favorite" in track["tags"]
