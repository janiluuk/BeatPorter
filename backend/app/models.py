
from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from typing import List, Dict, Optional


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


@dataclass
class Playlist:
    id: str
    name: str
    track_ids: List[str] = field(default_factory=list)


@dataclass
class Library:
    id: str
    name: str
    tracks: List[Track] = field(default_factory=list)
    playlists: Dict[str, Playlist] = field(default_factory=dict)
    _track_index: Dict[str, Track] = field(default_factory=dict, init=False, repr=False)

    def add_track(self, track: Track):
        self.tracks.append(track)
        self._track_index[track.id] = track

    def get_track(self, track_id: str) -> Optional[Track]:
        """Get track by ID using optimized index."""
        return self._track_index.get(track_id)

    def add_playlist(self, name: str, track_ids: List[str]) -> str:
        pid = str(uuid.uuid4())
        self.playlists[pid] = Playlist(id=pid, name=name, track_ids=list(track_ids))
        return pid
