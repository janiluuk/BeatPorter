
from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any


@dataclass
class Track:
    id: str
    title: str = ""
    artist: str = ""
    file_path: Optional[str] = None
    bpm: Optional[float] = None
    key: Optional[str] = None
    year: Optional[int] = None
    duration_seconds: Optional[int] = None
    genre: Optional[str] = None
    # Custom metadata fields - extensible dictionary for user-defined tags
    custom_fields: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)


@dataclass
class PlaylistFolder:
    """Represents a folder that can contain playlists and other folders."""
    id: str
    name: str
    parent_id: Optional[str] = None  # None means root level
    playlist_ids: List[str] = field(default_factory=list)
    subfolder_ids: List[str] = field(default_factory=list)


@dataclass
class Playlist:
    id: str
    name: str
    track_ids: List[str] = field(default_factory=list)
    folder_id: Optional[str] = None  # Which folder this playlist belongs to


@dataclass
class Library:
    id: str
    name: str
    tracks: List[Track] = field(default_factory=list)
    playlists: Dict[str, Playlist] = field(default_factory=dict)
    folders: Dict[str, PlaylistFolder] = field(default_factory=dict)
    _track_index: Dict[str, Track] = field(default_factory=dict, init=False, repr=False)

    def add_track(self, track: Track):
        self.tracks.append(track)
        self._track_index[track.id] = track

    def get_track(self, track_id: str) -> Optional[Track]:
        """Get track by ID using optimized index."""
        return self._track_index.get(track_id)

    def add_playlist(self, name: str, track_ids: List[str], folder_id: Optional[str] = None) -> str:
        pid = str(uuid.uuid4())
        self.playlists[pid] = Playlist(id=pid, name=name, track_ids=list(track_ids), folder_id=folder_id)
        
        # If playlist is in a folder, add it to that folder's playlist list
        if folder_id and folder_id in self.folders:
            self.folders[folder_id].playlist_ids.append(pid)
        
        return pid
    
    def add_folder(self, name: str, parent_id: Optional[str] = None) -> str:
        """Add a new folder to the library."""
        folder_id = str(uuid.uuid4())
        self.folders[folder_id] = PlaylistFolder(id=folder_id, name=name, parent_id=parent_id)
        
        # If this folder has a parent, add it to the parent's subfolder list
        if parent_id and parent_id in self.folders:
            self.folders[parent_id].subfolder_ids.append(folder_id)
        
        return folder_id
    
    def get_folder_hierarchy(self) -> Dict[str, Any]:
        """Get the complete folder hierarchy as a nested structure."""
        def build_folder_tree(folder_id: Optional[str] = None) -> List[Dict[str, Any]]:
            """Recursively build folder tree starting from given folder_id."""
            result = []
            
            # Find all folders with this parent_id
            for fid, folder in self.folders.items():
                if folder.parent_id == folder_id:
                    folder_data = {
                        "id": folder.id,
                        "name": folder.name,
                        "playlists": [
                            {"id": pid, "name": self.playlists[pid].name}
                            for pid in folder.playlist_ids
                            if pid in self.playlists
                        ],
                        "subfolders": build_folder_tree(folder.id)
                    }
                    result.append(folder_data)
            
            return result
        
        # Get root-level folders and playlists without folders
        root_folders = build_folder_tree(None)
        root_playlists = [
            {"id": pid, "name": p.name}
            for pid, p in self.playlists.items()
            if p.folder_id is None
        ]
        
        return {
            "folders": root_folders,
            "playlists": root_playlists
        }
