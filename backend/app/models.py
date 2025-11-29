
from typing import Dict, List, Optional
from pydantic import BaseModel

class Track(BaseModel):
    id: int
    title: Optional[str] = None
    artist: Optional[str] = None
    file_path: Optional[str] = None
    key: Optional[str] = None
    bpm: Optional[float] = None
    year: Optional[int] = None
    duration_sec: Optional[int] = None

class Playlist(BaseModel):
    id: str
    name: str
    track_ids: List[int] = []

class Library(BaseModel):
    id: str
    source_format: str
    tracks: Dict[int, Track]
    playlists: List[Playlist]
