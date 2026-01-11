
from __future__ import annotations
from typing import Tuple, List, Dict
from .models import Library, Track
import uuid
import xml.etree.ElementTree as ET
import csv
import io

# Default duration for tracks when not specified (5 minutes in seconds)
DEFAULT_DURATION_SECONDS = 300


def detect_format(filename: str, content: bytes) -> str:
    lower = (filename or "").lower()
    text = content.decode(errors="ignore")
    # Primary hints: file extension
    if lower.endswith(".m3u") or lower.endswith(".m3u8"):
        return "m3u"
    if lower.endswith(".xml"):
        if "DJ_PLAYLISTS" in text:
            return "rekordbox"
        if "<NML" in text:
            return "traktor"
        return "xml"
    if lower.endswith(".nml"):
        return "traktor"
    if lower.endswith(".csv"):
        # Be stricter for CSV: require a header row that looks like a DJ library export
        lines = text.splitlines()
        first_line = lines[0].strip() if lines else ""
        header_candidates = ["Title", "Artist", "File", "Key", "BPM"]
        if any(col in first_line for col in header_candidates):
            return "serato"
        return "unknown"

    # Content-based hints
    if "#EXTM3U" in text:
        return "m3u"
    if "<DJ_PLAYLISTS" in text:
        return "rekordbox"
    if "<NML" in text:
        return "traktor"

    # Very loose CSV heuristic as last resort
    lines = text.splitlines()
    if lines:
        first_line = lines[0].strip()
        header_candidates = ["Title", "Artist", "File", "Key", "BPM"]
        if "," in first_line and any(col in first_line for col in header_candidates):
            return "serato"

    return "unknown"


def parse_m3u(filename: str, content: bytes) -> Tuple[Library, Dict]:
    text = content.decode(errors="ignore")
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    lib = Library(id=str(uuid.uuid4()), name=filename)
    current_title_artist = ("", "")
    duration = None
    playlist_track_ids: List[str] = []

    for line in lines:
        if line.startswith("#EXTINF:"):
            # #EXTINF:300,Artist - Title
            try:
                meta = line.split(":", 1)[1]
                dur_str, rest = meta.split(",", 1)
                duration = int(float(dur_str))
                if " - " in rest:
                    artist, title = rest.split(" - ", 1)
                else:
                    artist, title = "", rest
                # Don't strip() to preserve leading/trailing whitespace for security checks
                current_title_artist = (title, artist)
            except Exception:
                current_title_artist = ("", "")
                duration = None
        elif not line.startswith("#"):
            file_path = line
            title, artist = current_title_artist
            tid = str(uuid.uuid4())
            track = Track(
                id=tid,
                title=title or file_path.split("/")[-1],
                artist=artist,
                file_path=file_path,
                duration_seconds=duration or DEFAULT_DURATION_SECONDS,
            )
            lib.add_track(track)
            playlist_track_ids.append(tid)

    # Single default playlist
    if playlist_track_ids:
        lib.add_playlist("Imported", playlist_track_ids)

    meta = {
        "source_format": "m3u",
        "track_count": len(lib.tracks),
        "playlist_count": len(lib.playlists),
    }
    return lib, meta


def parse_serato_csv(filename: str, content: bytes) -> Tuple[Library, Dict]:
    try:
        text = content.decode(errors="ignore")
        reader = csv.DictReader(io.StringIO(text))
        lib = Library(id=str(uuid.uuid4()), name=filename)
        playlist_ids: List[str] = []

        for row in reader:
            title = row.get("Title", "") or ""
            artist = row.get("Artist", "") or ""
            file_path = row.get("File", "") or ""
            key = row.get("Key", "") or ""
            bpm = row.get("BPM") or None
            year = row.get("Year") or None
            tid = str(uuid.uuid4())
            
            # Handle BPM conversion with error handling
            bpm_val = None
            if bpm:
                try:
                    bpm_val = float(bpm)
                except (ValueError, TypeError):
                    bpm_val = None
            
            # Handle year conversion with error handling
            year_val = None
            if year:
                try:
                    year_val = int(year)
                except (ValueError, TypeError):
                    year_val = None
            
            track = Track(
                id=tid,
                title=title,
                artist=artist,
                file_path=file_path,
                key=key,
                bpm=bpm_val,
                year=year_val,
                duration_seconds=DEFAULT_DURATION_SECONDS,
            )
            lib.add_track(track)
            playlist_ids.append(tid)

        if playlist_ids:
            lib.add_playlist("Imported", playlist_ids)

        meta = {
            "source_format": "serato_csv",
            "track_count": len(lib.tracks),
            "playlist_count": len(lib.playlists),
        }
        return lib, meta
    except Exception as e:
        raise ValueError(f"Failed to parse Serato CSV: {str(e)}")


def parse_rekordbox_xml(filename: str, content: bytes) -> Tuple[Library, Dict]:
    try:
        text = content.decode(errors="ignore")
        root = ET.fromstring(text)
        lib = Library(id=str(uuid.uuid4()), name=filename)
        id_to_trackid: Dict[str, str] = {}

        collection = root.find(".//COLLECTION")
        if collection is not None:
            for track_el in collection.findall("TRACK"):
                track_id = track_el.get("TrackID") or str(uuid.uuid4())
                title = track_el.get("Name", "") or ""
                artist = track_el.get("Artist", "") or ""
                loc = track_el.get("Location", "") or ""
                bpm = track_el.get("AverageBpm") or None
                year = track_el.get("Year") or None
                key = track_el.get("Tonality") or ""
                
                # Handle BPM conversion with error handling
                bpm_val = None
                if bpm:
                    try:
                        bpm_val = float(bpm)
                    except (ValueError, TypeError):
                        bpm_val = None
                
                # Handle year conversion with error handling
                year_val = None
                if year:
                    try:
                        year_val = int(year)
                    except (ValueError, TypeError):
                        year_val = None
                
                # Handle duration conversion with error handling
                duration_val = DEFAULT_DURATION_SECONDS
                duration_str = track_el.get("TotalTime")
                if duration_str:
                    try:
                        duration_val = int(duration_str)
                    except (ValueError, TypeError):
                        duration_val = DEFAULT_DURATION_SECONDS
                
                tid = str(uuid.uuid4())
                track = Track(
                    id=tid,
                    title=title,
                    artist=artist,
                    file_path=loc,
                    bpm=bpm_val,
                    year=year_val,
                    key=key,
                    duration_seconds=duration_val,
                )
                lib.add_track(track)
                id_to_trackid[track_id] = tid

        playlist_count = 0
        playlists_root = root.find(".//PLAYLISTS")
        if playlists_root is not None:
            for node in playlists_root.findall(".//NODE"):
                if node.get("Type") == "1":  # playlist
                    name = node.get("Name", "Playlist")
                    tids: List[str] = []
                    for track_ref in node.findall("TRACK"):
                        key = track_ref.get("Key")
                        if key and key in id_to_trackid:
                            tids.append(id_to_trackid[key])
                    if tids:
                        lib.add_playlist(name, tids)
                        playlist_count += 1

        meta = {
            "source_format": "rekordbox_xml",
            "track_count": len(lib.tracks),
            "playlist_count": playlist_count or len(lib.playlists),
        }
        return lib, meta
    except ET.ParseError as e:
        raise ValueError(f"Failed to parse Rekordbox XML: {str(e)}")
    except Exception as e:
        raise ValueError(f"Failed to parse Rekordbox XML: {str(e)}")


def parse_traktor_nml(filename: str, content: bytes) -> Tuple[Library, Dict]:
    try:
        text = content.decode(errors="ignore")
        root = ET.fromstring(text)
        lib = Library(id=str(uuid.uuid4()), name=filename)
        id_to_trackid: Dict[str, str] = {}

        collection = root.find(".//COLLECTION")
        if collection is not None:
            for entry in collection.findall("ENTRY"):
                title = entry.get("TITLE", "") or ""
                artist = entry.get("ARTIST", "") or ""
                info = entry.find("INFO")
                loc = entry.find("LOCATION")
                
                bpm = info.get("BPM") if info is not None else None
                key = info.get("MUSICAL_KEY") if info is not None else ""
                year = None
                duration_seconds = DEFAULT_DURATION_SECONDS
                
                if info is not None:
                    date = info.get("RELEASE_DATE")
                    if date and len(date) >= 4:
                        try:
                            year = int(date[:4])
                        except (ValueError, TypeError):
                            year = None
                    # Parse PLAYTIME field (in seconds)
                    playtime = info.get("PLAYTIME")
                    if playtime:
                        try:
                            # Check if it's an integer or float
                            if '.' in playtime:
                                duration_seconds = int(float(playtime))
                            else:
                                duration_seconds = int(playtime)
                        except (ValueError, TypeError):
                            duration_seconds = DEFAULT_DURATION_SECONDS
                
                # Handle BPM conversion with error handling
                bpm_val = None
                if bpm:
                    try:
                        bpm_val = float(bpm)
                    except (ValueError, TypeError):
                        bpm_val = None
                
                file_path = ""
                if loc is not None:
                    directory = loc.get("DIR", "") or ""
                    file_name = loc.get("FILE", "") or ""
                    file_path = directory + file_name
                tid = str(uuid.uuid4())
                track = Track(
                    id=tid,
                    title=title,
                    artist=artist,
                    file_path=file_path,
                    bpm=bpm_val,
                    year=year,
                    key=key,
                    duration_seconds=duration_seconds,
                )
                lib.add_track(track)
                # Use file_path as the key for playlist references (more reliable than TITLE)
                # If file_path is empty, fall back to TITLE
                track_key = file_path if file_path else title
                if track_key:
                    id_to_trackid[track_key] = tid

        playlist_count = 0
        playlists_root = root.find(".//PLAYLISTS")
        if playlists_root is not None:
            for node in playlists_root.findall(".//NODE"):
                if node.get("TYPE", "").upper() == "PLAYLIST":
                    name = node.get("NAME", "Playlist")
                    tids: List[str] = []
                    for entry_ref in node.findall("ENTRY"):
                        key = entry_ref.get("KEY")
                        if key and key in id_to_trackid:
                            tids.append(id_to_trackid[key])
                    if tids:
                        lib.add_playlist(name, tids)
                        playlist_count += 1

        meta = {
            "source_format": "traktor_nml",
            "track_count": len(lib.tracks),
            "playlist_count": playlist_count or len(lib.playlists),
        }
        return lib, meta
    except ET.ParseError as e:
        raise ValueError(f"Failed to parse Traktor NML: {str(e)}")
    except Exception as e:
        raise ValueError(f"Failed to parse Traktor NML: {str(e)}")
