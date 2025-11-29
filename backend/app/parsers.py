
import csv
import io
from typing import List, Tuple
from xml.etree import ElementTree as ET

from .models import Track, Playlist

def _next_id():
    i = 1
    while True:
        yield i
        i += 1

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
        # Be stricter for CSV: require a header row that looks like a DJ library export,
        # not just "has a comma".
        first_line = text.splitlines()[0].strip() if text.splitlines() else ""
        header_candidates = ["Title", "Artist", "File", "Key", "BPM"]
        if any(col in first_line for col in header_candidates):
            return "serato"
        # Unknown CSV-ish file → treat as unknown to avoid false-positives
        return "unknown"

    # Content-based hints (fallbacks)
    if "#EXTM3U" in text:
        return "m3u"
    if "<DJ_PLAYLISTS" in text:
        return "rekordbox"
    if "<NML" in text:
        return "traktor"

    # Very loose CSV heuristic as last resort: header with typical fields
    lines = text.splitlines()
    if lines:
        first_line = lines[0].strip()
        header_candidates = ["Title", "Artist", "File", "Key", "BPM"]
        if "," in first_line and any(col in first_line for col in header_candidates):
            return "serato"

    return "unknown"
def parse_m3u(content: bytes) -> Tuple[List[Track], List[Playlist], str]:
    text = content.decode(errors="ignore")
    lines = text.splitlines()
    gen_id = _next_id()
    tracks: List[Track] = []
    current_duration = None
    current_title = None

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#EXTM3U"):
            continue
        if line.startswith("#EXTINF:"):
            try:
                _, meta = line.split(":", 1)
                dur_str, info = meta.split(",", 1)
                current_duration = int(float(dur_str))
                current_title = info.strip()
            except ValueError:
                current_duration = None
                current_title = None
            continue
        file_path = line
        t_id = next(gen_id)
        title = current_title
        artist = None
        if title and " - " in title:
            artist, title = title.split(" - ", 1)
        tracks.append(Track(
            id=t_id,
            title=title,
            artist=artist,
            file_path=file_path,
            duration_sec=current_duration,
        ))
        current_duration = None
        current_title = None

    playlist = Playlist(id="pl1", name="M3U Playlist", track_ids=[t.id for t in tracks])
    return tracks, [playlist], "m3u"

def parse_rekordbox_xml(content: bytes) -> Tuple[List[Track], List[Playlist], str]:
    text = content.decode(errors="ignore")
    root = ET.fromstring(text)
    collection = root.find(".//COLLECTION")
    gen_id = _next_id()
    tracks: List[Track] = []
    rb_id_to_track_id = {}

    if collection is not None:
        for tr in collection.findall("TRACK"):
            t_id = next(gen_id)
            name = tr.get("Name") or tr.get("TITLE")
            artist = tr.get("Artist") or tr.get("ARTIST")
            loc = tr.get("Location")
            key = tr.get("Tonality")
            bpm = tr.get("AverageBpm") or tr.get("BPM")
            year = tr.get("Year")
            dur = tr.get("TotalTime")
            try:
                bpm_val = float(bpm) if bpm else None
            except ValueError:
                bpm_val = None
            try:
                year_val = int(year) if year else None
            except ValueError:
                year_val = None
            try:
                dur_val = int(dur) if dur else None
            except ValueError:
                dur_val = None
            tracks.append(Track(
                id=t_id,
                title=name,
                artist=artist,
                file_path=loc,
                key=key,
                bpm=bpm_val,
                year=year_val,
                duration_sec=dur_val,
            ))
            rb_id_to_track_id[tr.get("TrackID") or tr.get("TrackId") or str(t_id)] = t_id

    playlists: List[Playlist] = []
    playlists_root = root.find(".//PLAYLISTS")
    if playlists_root is not None:
        for node in playlists_root.findall(".//NODE"):
            if node.get("Type") == "1":
                name = node.get("Name") or "Playlist"
                ids = []
                for track in node.findall(".//TRACK"):
                    key = track.get("Key") or track.get("TrackID")
                    if key in rb_id_to_track_id:
                        ids.append(rb_id_to_track_id[key])
                if ids:
                    playlists.append(Playlist(id=f"pl_{len(playlists)+1}", name=name, track_ids=ids))

    if not playlists:
        playlists = [Playlist(id="pl1", name="Rekordbox Collection", track_ids=[t.id for t in tracks])]

    return tracks, playlists, "rekordbox_xml"

def parse_serato_csv(content: bytes) -> Tuple[List[Track], List[Playlist], str]:
    text = content.decode(errors="ignore")
    reader = csv.DictReader(io.StringIO(text))
    gen_id = _next_id()
    tracks: List[Track] = []
    for row in reader:
        title = row.get("Title") or row.get("Name") or row.get("Song")
        artist = row.get("Artist")
        file_path = row.get("File") or row.get("Location") or row.get("Filename")
        key = row.get("Key")
        bpm = row.get("BPM") or row.get("Tempo")
        year = row.get("Year") or row.get("Release Year")
        try:
            bpm_val = float(bpm) if bpm else None
        except ValueError:
            bpm_val = None
        try:
            year_val = int(year) if year else None
        except ValueError:
            year_val = None
        t_id = next(gen_id)
        tracks.append(Track(
            id=t_id,
            title=title,
            artist=artist,
            file_path=file_path,
            key=key,
            bpm=bpm_val,
            year=year_val,
        ))
    playlist = Playlist(id="pl1", name="Serato Playlist", track_ids=[t.id for t in tracks])
    return tracks, [playlist], "serato_csv"

def parse_traktor_nml(content: bytes) -> Tuple[List[Track], List[Playlist], str]:
    text = content.decode(errors="ignore")
    root = ET.fromstring(text)
    collection = root.find(".//COLLECTION")
    gen_id = _next_id()
    tracks: List[Track] = []
    nml_id_to_track_id = {}

    if collection is not None:
        for entry in collection.findall("ENTRY"):
            t_id = next(gen_id)
            title = entry.get("TITLE")
            artist = entry.get("ARTIST")
            info = entry.find("INFO")
            bpm_val = None
            key = None
            year_val = None
            if info is not None:
                bpm = info.get("BPM")
                key = info.get("MUSICAL_KEY")
                year = info.get("RELEASE_DATE")
                try:
                    bpm_val = float(bpm) if bpm else None
                except ValueError:
                    bpm_val = None
                try:
                    if year and len(year) >= 4:
                        year_val = int(year[:4])
                except ValueError:
                    year_val = None
            loc = entry.find("LOCATION")
            file_path = None
            if loc is not None:
                directory = loc.get("DIR") or ""
                file_name = loc.get("FILE") or ""
                file_path = directory + file_name
            tr = Track(
                id=t_id,
                title=title,
                artist=artist,
                file_path=file_path,
                key=key,
                bpm=bpm_val,
                year=year_val,
            )
            tracks.append(tr)
            nml_id_to_track_id[entry.get("KEY") or str(t_id)] = t_id

    playlists: List[Playlist] = []
    playlists_root = root.find(".//PLAYLISTS")
    if playlists_root is not None:
        for node in playlists_root.findall(".//NODE"):
            if node.get("TYPE") == "PLAYLIST" or node.get("Type") == "1":
                name = node.get("NAME") or node.get("Name") or "Playlist"
                ids = []
                for entry in node.findall(".//ENTRY"):
                    key = entry.get("KEY")
                    if key in nml_id_to_track_id:
                        ids.append(nml_id_to_track_id[key])
                if ids:
                    playlists.append(Playlist(id=f"pl_{len(playlists)+1}", name=name, track_ids=ids))

    if not playlists:
        playlists = [Playlist(id="pl1", name="Traktor Collection", track_ids=[t.id for t in tracks])]

    return tracks, playlists, "traktor_nml"
