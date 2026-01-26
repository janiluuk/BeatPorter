
from __future__ import annotations
import uuid
from pathlib import Path
import re
from typing import Dict, List, Optional, Any
import time

from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, validator

from .models import Library, Track
from .parsers import (
    detect_format, 
    parse_m3u, 
    parse_rekordbox_xml, 
    parse_serato_csv, 
    parse_traktor_nml,
    DEFAULT_DURATION_SECONDS
)

app = FastAPI(title="BeatPorter v0.6")

SUPPORTED_EXPORT_FORMATS = ("m3u", "serato", "rekordbox", "traktor", "txt")

# Track library access times for cleanup
LIBRARIES: Dict[str, Library] = {}
LIBRARY_ACCESS_TIMES: Dict[str, float] = {}
LIBRARY_TTL_SECONDS = 3600 * 2  # 2 hours
MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


def _cleanup_old_libraries():
    """Remove libraries that haven't been accessed recently.
    
    This is called on every library access to ensure stale libraries
    are eventually cleaned up without requiring a background task.
    """
    current_time = time.time()
    to_remove = [
        lib_id for lib_id, access_time in LIBRARY_ACCESS_TIMES.items()
        if current_time - access_time > LIBRARY_TTL_SECONDS
    ]
    
    for lib_id in to_remove:
        LIBRARIES.pop(lib_id, None)
        LIBRARY_ACCESS_TIMES.pop(lib_id, None)
    
    return len(to_remove)


def get_library_or_404(library_id: str) -> Library:
    # Clean up old libraries before accessing
    _cleanup_old_libraries()
    
    lib = LIBRARIES.get(library_id)
    if not lib:
        raise HTTPException(status_code=404, detail="Library not found")
    
    # Update access time
    LIBRARY_ACCESS_TIMES[library_id] = time.time()
    return lib


# Static mounting (only if frontend exists)
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR.parent.parent / "frontend"
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


@app.get("/")
def root():
    """Redirect root to static frontend."""
    return RedirectResponse(url="/static/", status_code=307)


class ImportResponse(BaseModel):
    library_id: str
    source_format: str
    track_count: int
    playlist_count: int


@app.post("/api/import", response_model=ImportResponse)
async def import_library(file: UploadFile = File(...)):
    try:
        content = await file.read()
        
        # Check file size to prevent memory exhaustion
        if len(content) > MAX_UPLOAD_SIZE_BYTES:
            raise HTTPException(
                status_code=413, 
                detail=f"File too large. Maximum size is {MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)} MB"
            )
        
        fmt = detect_format(file.filename, content)
        if fmt == "m3u":
            lib, meta = parse_m3u(file.filename, content)
        elif fmt == "serato":
            lib, meta = parse_serato_csv(file.filename, content)
        elif fmt == "rekordbox":
            lib, meta = parse_rekordbox_xml(file.filename, content)
        elif fmt == "traktor":
            lib, meta = parse_traktor_nml(file.filename, content)
        else:
            raise HTTPException(status_code=400, detail="Could not detect format")

        LIBRARIES[lib.id] = lib
        LIBRARY_ACCESS_TIMES[lib.id] = time.time()
        return ImportResponse(
            library_id=lib.id,
            source_format=meta["source_format"],
            track_count=meta["track_count"],
            playlist_count=meta["playlist_count"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to import library: {str(e)}")


@app.get("/api/library/{library_id}")
def get_library(library_id: str):
    lib = get_library_or_404(library_id)
    return {
        "id": lib.id,
        "name": lib.name,
        "track_count": len(lib.tracks),
        "playlist_count": len(lib.playlists),
    }


@app.delete("/api/library/{library_id}")
def delete_library(library_id: str):
    """Delete a library from memory to free resources."""
    lib = LIBRARIES.pop(library_id, None)
    LIBRARY_ACCESS_TIMES.pop(library_id, None)
    if not lib:
        raise HTTPException(status_code=404, detail="Library not found")
    return {"status": "deleted", "library_id": library_id}


@app.get("/api/library/{library_id}/tracks")
def list_tracks(
    library_id: str,
    playlist_id: Optional[str] = None,
    q: Optional[str] = None,
):
    lib = get_library_or_404(library_id)
    tracks = lib.tracks

    if playlist_id:
        pl = lib.playlists.get(playlist_id)
        if not pl:
            raise HTTPException(status_code=404, detail="Playlist not found")
        allowed = set(pl.track_ids)
        tracks = [t for t in tracks if t.id in allowed]

    if q:
        ql = q.lower()
        tracks = [
            t for t in tracks
            if ql in (t.title or "").lower()
            or ql in (t.artist or "").lower()
            or ql in (t.file_path or "").lower()
        ]

    return [
        {
            "id": t.id,
            "title": t.title,
            "artist": t.artist,
            "file_path": t.file_path,
            "bpm": t.bpm,
            "key": t.key,
            "year": t.year,
            "duration_seconds": t.duration_seconds,
            "genre": t.genre,
            "custom_fields": t.custom_fields,
            "tags": t.tags,
        }
        for t in tracks
    ]


class SmartPlaylistParamsV1(BaseModel):
    target_minutes: int = 60
    keyword: Optional[str] = None


@app.post("/api/library/{library_id}/generate_playlist")
def generate_playlist_v1(library_id: str, params: SmartPlaylistParamsV1):
    lib = get_library_or_404(library_id)
    candidates = lib.tracks
    if params.keyword:
        ql = params.keyword.lower()
        candidates = [
            t for t in candidates
            if ql in (t.title or "").lower()
            or ql in (t.artist or "").lower()
        ]

    total_sec = 0
    selected: List[Track] = []
    for t in candidates:
        dur = t.duration_seconds or DEFAULT_DURATION_SECONDS
        if total_sec >= params.target_minutes * 60:
            break
        selected.append(t)
        total_sec += dur

    name = f"Auto {params.target_minutes} min"
    pid = lib.add_playlist(name, [t.id for t in selected])
    return {
        "playlist_id": pid,
        "name": name,
        "track_count": len(selected),
        "approx_duration_minutes": int(round(total_sec / 60)) if selected else 0,
    }


class RewritePathsRequest(BaseModel):
    search: str
    replace: str


@app.post("/api/library/{library_id}/preview_rewrite_paths")
def preview_rewrite_paths(library_id: str, req: RewritePathsRequest):
    lib = get_library_or_404(library_id)
    
    # Validate inputs
    if not req.search:
        raise HTTPException(status_code=400, detail="search string cannot be empty")
    
    total = len(lib.tracks)
    affected = 0
    examples: List[dict] = []

    for t in lib.tracks:
        path = t.file_path or ""
        if req.search in path:
            affected += 1
            if len(examples) < 5:
                examples.append(
                    {
                        "track_id": t.id,
                        "old_path": path,
                        "new_path": path.replace(req.search, req.replace),
                    }
                )

    return {
        "total_tracks": total,
        "affected_tracks": affected,
        "examples": examples,
    }


@app.post("/api/library/{library_id}/apply_rewrite_paths")
def apply_rewrite_paths(library_id: str, req: RewritePathsRequest):
    lib = get_library_or_404(library_id)
    
    # Validate inputs
    if not req.search:
        raise HTTPException(status_code=400, detail="search string cannot be empty")
    
    changed = 0
    for t in lib.tracks:
        path = t.file_path or ""
        if req.search in path:
            t.file_path = path.replace(req.search, req.replace)
            changed += 1
    return {"changed_tracks": changed}



def _escape_xml(text: str) -> str:
    """Escape special XML characters to prevent injection."""
    if not text:
        return ""
    return (text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;"))


def _escape_csv(text: str) -> str:
    """Escape CSV injection characters to prevent formula injection attacks.
    
    Prepends a single quote to any field that starts with dangerous characters
    (=, +, -, @, tab, or carriage return) that could be interpreted as formulas
    by spreadsheet applications.
    """
    if not text:
        return ""
    # Check for leading whitespace followed by dangerous characters
    # or dangerous characters at the start
    if re.match(r"^[\s\t\r\n]*[=+\-@\t\r]", text):
        return "'" + text
    return text


def _render_export_tracks(tracks: List[Track], fmt: str) -> str:
    fmt = fmt.lower()
    if fmt == "m3u":
        lines = ["#EXTM3U"]
        for t in tracks:
            dur = t.duration_seconds or DEFAULT_DURATION_SECONDS
            artist = t.artist or ""
            title = t.title or ""
            path = t.file_path or ""
            lines.append(f"#EXTINF:{dur},{artist} - {title}")
            lines.append(path)
        return "\n".join(lines)

    if fmt == "serato":
        import csv
        import io as _io
        output = _io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Title", "Artist", "File", "Key", "BPM", "Year"])
        for t in tracks:
            writer.writerow(
                [
                    _escape_csv(t.title or ""),
                    _escape_csv(t.artist or ""),
                    _escape_csv(t.file_path or ""),
                    _escape_csv(t.key or ""),
                    t.bpm or "",
                    t.year or "",
                ]
            )
        return output.getvalue()

    if fmt == "rekordbox":
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<DJ_PLAYLISTS Version="1.0">',
            "  <COLLECTION>",
        ]
        for i, t in enumerate(tracks, start=1):
            loc = _escape_xml(t.file_path or "")
            title = _escape_xml(t.title or "")
            artist = _escape_xml(t.artist or "")
            key = _escape_xml(t.key or "")
            bpm = t.bpm or ""
            year = t.year or ""
            lines.append(
                f'    <TRACK TrackID="{i}" Name="{title}" Artist="{artist}" '
                f'Location="{loc}" AverageBpm="{bpm}" Year="{year}" '
                f'TotalTime="{t.duration_seconds or DEFAULT_DURATION_SECONDS}" Tonality="{key}" />'
            )
        lines.append("  </COLLECTION>")
        lines.append("  <PLAYLISTS>")
        lines.append('    <NODE Name="ROOT" Type="0">')
        lines.append('      <NODE Name="Exported" Type="1">')
        for i, _t in enumerate(tracks, start=1):
            lines.append(f'        <TRACK Key="{i}" />')
        lines.append("      </NODE>")
        lines.append("    </NODE>")
        lines.append("  </PLAYLISTS>")
        lines.append("</DJ_PLAYLISTS>")
        return "\n".join(lines)

    if fmt == "traktor":
        lines = [
            '<NML VERSION="19">',
            "  <COLLECTION>",
        ]
        for t in tracks:
            title = _escape_xml(t.title or "")
            artist = _escape_xml(t.artist or "")
            bpm = t.bpm or ""
            key = _escape_xml(t.key or "")
            year = t.year or ""
            duration = t.duration_seconds or DEFAULT_DURATION_SECONDS
            file_path = t.file_path or ""
            dir_part = ""
            file_name = file_path
            if "/" in file_path:
                dir_part = file_path.rsplit("/", 1)[0] + "/"
                file_name = file_path.rsplit("/", 1)[1]
            dir_part = _escape_xml(dir_part)
            file_name = _escape_xml(file_name)
            lines.append(
                f'    <ENTRY TITLE="{title}" ARTIST="{artist}">'
                f'<INFO BPM="{bpm}" MUSICAL_KEY="{key}" RELEASE_DATE="{year}-01-01" PLAYTIME="{duration}" />'
                f'<LOCATION DIR="{dir_part}" FILE="{file_name}" />'
                f"</ENTRY>"
            )
        lines.append("  </COLLECTION>")
        lines.append("  <PLAYLISTS>")
        lines.append('    <NODE NAME="ROOT" TYPE="FOLDER">')
        lines.append('      <NODE NAME="Exported" TYPE="PLAYLIST">')
        # Use file_path as KEY to match what the parser expects
        for t in tracks:
            track_key = _escape_xml(t.file_path if t.file_path else t.title or "")
            lines.append(f'        <ENTRY KEY="{track_key}" />')
        lines.append("      </NODE>")
        lines.append("    </NODE>")
        lines.append("  </PLAYLISTS>")
        lines.append("</NML>")
        return "\n".join(lines)

    if fmt == "txt":
        lines = []
        for i, t in enumerate(tracks, start=1):
            artist = (t.artist or "").strip()
            title = (t.title or "").strip()
            # Format: "Artist - Title" or use title if artist is missing
            if artist and title:
                lines.append(f"{i}. {artist} - {title}")
            elif title:
                lines.append(f"{i}. {title}")
            elif artist:
                lines.append(f"{i}. {artist}")
            else:
                # Fallback to file path if both are missing
                # Handle both Unix (/) and Windows (\) path separators
                if t.file_path:
                    filename = t.file_path.replace("\\", "/").split("/")[-1]
                else:
                    filename = "Unknown Track"
                lines.append(f"{i}. {filename}")
        return "\n".join(lines)

    raise HTTPException(status_code=400, detail="Unsupported export format")


@app.post("/api/library/{library_id}/export")
def export_library(
    library_id: str,
    format: str = Query(..., alias="format"),
    playlist_id: Optional[str] = None,
):
    lib = get_library_or_404(library_id)
    
    # Validate format early
    if format.lower() not in SUPPORTED_EXPORT_FORMATS:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid format '{format}'. Must be one of: {', '.join(SUPPORTED_EXPORT_FORMATS)}"
        )
    
    tracks = lib.tracks
    if playlist_id:
        pl = lib.playlists.get(playlist_id)
        if not pl:
            raise HTTPException(status_code=404, detail="Playlist not found")
        allowed = set(pl.track_ids)
        tracks = [t for t in tracks if t.id in allowed]

    text = _render_export_tracks(tracks, format)
    return PlainTextResponse(text)



class ExportBundleRequest(BaseModel):
    formats: List[str]
    playlist_id: Optional[str] = None

    @validator("formats")
    def validate_formats(cls, value: List[str]) -> List[str]:
        if not value:
            raise ValueError("formats must include at least one format")

        normalized: List[str] = []
        seen = set()
        duplicates = set()
        for fmt in value:
            norm = fmt.strip().lower()
            if norm in seen:
                duplicates.add(norm)
            else:
                seen.add(norm)
                normalized.append(norm)

        if duplicates:
            dup_list = ", ".join(sorted(duplicates))
            raise ValueError(f"Duplicate export formats: {dup_list}")

        unsupported = [fmt for fmt in normalized if fmt not in SUPPORTED_EXPORT_FORMATS]
        if unsupported:
            supported = ", ".join(SUPPORTED_EXPORT_FORMATS)
            unsupported_list = ", ".join(unsupported)
            raise ValueError(
                f"Unsupported export format(s): {unsupported_list}. Supported formats: {supported}."
            )

        return normalized


@app.post("/api/library/{library_id}/export_bundle")
def export_bundle(library_id: str, body: ExportBundleRequest):
    import io
    import zipfile
    from fastapi.responses import Response

    lib = get_library_or_404(library_id)
    tracks = lib.tracks
    if body.playlist_id:
        pl = lib.playlists.get(body.playlist_id)
        if not pl:
            raise HTTPException(status_code=404, detail="Playlist not found")
        allowed = set(pl.track_ids)
        tracks = [t for t in tracks if t.id in allowed]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for fmt in body.formats:
            text = _render_export_tracks(tracks, fmt)
            if fmt == "m3u":
                fname = "library.m3u"
            elif fmt == "serato":
                fname = "library_serato.csv"
            elif fmt == "rekordbox":
                fname = "library_rekordbox.xml"
            elif fmt == "traktor":
                fname = "library_traktor.nml"
            else:  # f == "txt"
                fname = "library_tracklist.txt"
            
            z.writestr(fname, text)

    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="beatporter_export.zip"'},
    )


from collections import defaultdict
import re

# Pre-compile regex for performance
_NORM_REGEX = re.compile(r'[^a-z0-9\s]')

def _normalize_for_dup(value: str | None) -> str:
    if not value:
        return ""
    # Convert to lowercase and remove non-alphanumeric characters in one pass
    value = value.strip().lower()
    return _NORM_REGEX.sub('', value)


@app.get("/api/library/{library_id}/duplicates")
def get_duplicates(library_id: str):
    lib = get_library_or_404(library_id)
    buckets: Dict[tuple, List[Track]] = defaultdict(list)

    for t in lib.tracks:
        norm_title = _normalize_for_dup(t.title)
        norm_artist = _normalize_for_dup(t.artist)
        file_name = ""
        path = t.file_path
        if path:
            file_name = path.replace("\\", "/").split("/")[-1].lower()
        key = (norm_artist, norm_title, file_name)
        buckets[key].append(t)

    groups: List[dict] = []
    for (norm_artist, norm_title, file_name), tracks in buckets.items():
        if len(tracks) < 2:
            continue
        # Skip groups where all identifying fields are empty
        # (these aren't real duplicates, just tracks with missing metadata)
        if not norm_artist and not norm_title and not file_name:
            continue
        groups.append(
            {
                "canonical_title": tracks[0].title,
                "canonical_artist": tracks[0].artist,
                "file_names": sorted(
                    {(tr.file_path or "").replace("\\", "/").split("/")[-1] for tr in tracks}
                ),
                "track_ids": [tr.id for tr in tracks],
                "count": len(tracks),
            }
        )

    return {
        "total_groups": len(groups),
        "duplicate_groups": groups,
    }


class MetadataAutoFixRequest(BaseModel):
    normalize_whitespace: bool = True
    upper_case_keys: bool = True
    zero_year_to_null: bool = True


@app.get("/api/library/{library_id}/metadata_issues")
def get_metadata_issues(library_id: str):
    lib = get_library_or_404(library_id)
    issues: Dict[str, List[str]] = {
        "missing_bpm": [],
        "missing_key": [],
        "missing_year": [],
        "missing_file_path": [],
        "suspicious_bpm": [],
        "empty_title": [],
        "empty_artist": [],
    }

    for t in lib.tracks:
        tid = t.id
        bpm = t.bpm
        key = t.key
        year = t.year
        path = t.file_path
        title = t.title
        artist = t.artist

        if not title or not title.strip():
            issues["empty_title"].append(tid)
        if not artist or not artist.strip():
            issues["empty_artist"].append(tid)

        if bpm is None or bpm <= 0:
            issues["missing_bpm"].append(tid)
        elif bpm is not None and bpm > 300:
            issues["suspicious_bpm"].append(tid)

        if not key or not key.strip():
            issues["missing_key"].append(tid)

        if year is None or year <= 0:
            issues["missing_year"].append(tid)

        if not path:
            issues["missing_file_path"].append(tid)

    return {
        "total_tracks": len(lib.tracks),
        "issues": issues,
    }



@app.post("/api/library/{library_id}/metadata_auto_fix")
def metadata_auto_fix(library_id: str, req: MetadataAutoFixRequest):
    lib = get_library_or_404(library_id)
    changed = 0
    for t in lib.tracks:
        before = (t.title, t.artist, t.key, t.year)

        if req.normalize_whitespace:
            if t.title:
                t.title = t.title.strip()
            if t.artist:
                t.artist = t.artist.strip()
            if t.key:
                t.key = t.key.strip()
                # Use regex to replace multiple spaces with single space (more efficient)
                t.key = re.sub(r'\s+', ' ', t.key)

        if req.upper_case_keys and t.key:
            t.key = t.key.upper()

        if req.zero_year_to_null and t.year == 0:
            t.year = None

        after = (t.title, t.artist, t.key, t.year)
        if before != after:
            changed += 1

    return {"changed_tracks": changed}


@app.get("/api/library/{library_id}/stats")
def get_library_stats(library_id: str):
    """Return simple aggregate statistics about the library.

    Designed for a small, clean UI card:
    - total tracks / playlists
    - BPM range + average (for tracks with BPM)
    - year range
    - key distribution
    - top artists
    - total duration approximation
    """
    lib = get_library_or_404(library_id)

    track_count = len(lib.tracks)
    playlist_count = len(lib.playlists)

    # Single pass through tracks for all statistics
    bpms = []
    years = []
    key_distribution: Dict[str, int] = {}
    artist_counts: Dict[str, int] = {}
    total_seconds = 0

    for t in lib.tracks:
        # BPM stats
        if t.bpm is not None:
            bpms.append(t.bpm)
        
        # Year stats
        if t.year is not None:
            years.append(t.year)
        
        # Key distribution
        key = (t.key or "").strip().upper()
        if key:
            key_distribution[key] = key_distribution.get(key, 0) + 1
        
        # Artist counts
        artist = (t.artist or "").strip()
        if artist:
            artist_counts[artist] = artist_counts.get(artist, 0) + 1
        
        # Total duration
        total_seconds += t.duration_seconds or DEFAULT_DURATION_SECONDS

    bpm_min = min(bpms) if bpms else None
    bpm_max = max(bpms) if bpms else None
    bpm_avg = round(sum(bpms) / len(bpms), 1) if bpms else None

    year_min = min(years) if years else None
    year_max = max(years) if years else None

    top_artists = sorted(
        [{"artist": a, "count": c} for a, c in artist_counts.items()],
        key=lambda x: (-x["count"], x["artist"]),
    )[:10]

    approx_total_minutes = int(round(total_seconds / 60)) if track_count > 0 else 0
    approx_avg_minutes = (
        round((total_seconds / track_count) / 60, 1) if track_count > 0 else None
    )

    return {
        "track_count": track_count,
        "playlist_count": playlist_count,
        "bpm": {
            "min": bpm_min,
            "max": bpm_max,
            "avg": bpm_avg,
        },
        "year": {
            "min": year_min,
            "max": year_max,
        },
        "keys": key_distribution,
        "top_artists": top_artists,
        "duration": {
            "total_minutes": approx_total_minutes,
            "avg_minutes": approx_avg_minutes,
        },
    }


@app.get("/api/library/{library_id}/health")
def get_library_health(library_id: str):
    """Quick, non-destructive 'health check' for the library.

    This is intentionally shallow: it only inspects metadata and paths.
    It's meant to power a small 'Health' panel in the UI, not to be an
    audio validator.

    Flags:
    - missing_file_path
    - unknown_extension
    - very_short_duration (< 30s)
    - unusual_bpm (< 60 or > 200)
    - unusual_year (< 1950 or > current_year + 1)
    """
    import datetime

    lib = get_library_or_404(library_id)

    issues: Dict[str, List[str]] = {
        "missing_file_path": [],
        "unknown_extension": [],
        "very_short_duration": [],
        "unusual_bpm": [],
        "unusual_year": [],
    }

    current_year = datetime.datetime.now(datetime.UTC).year
    valid_exts = {".mp3", ".wav", ".aiff", ".aif", ".flac", ".m4a", ".ogg"}

    for t in lib.tracks:
        tid = t.id
        path = t.file_path or ""
        bpm = t.bpm
        year = t.year
        dur = t.duration_seconds

        if not path:
            issues["missing_file_path"].append(tid)
        else:
            lower = path.lower()
            dot = lower.rfind(".")
            ext = lower[dot:] if dot != -1 else ""
            if ext and ext not in valid_exts:
                issues["unknown_extension"].append(tid)

        if dur is not None and dur < 30:
            issues["very_short_duration"].append(tid)

        if bpm is not None and (bpm < 60 or bpm > 200):
            issues["unusual_bpm"].append(tid)

        if year is not None and (year < 1950 or year > current_year + 1):
            issues["unusual_year"].append(tid)

    return {
        "total_tracks": len(lib.tracks),
        "issues": issues,
    }



class SmartPlaylistParams(BaseModel):
    target_minutes: int = 60
    keyword: Optional[str] = None
    min_bpm: Optional[float] = None
    max_bpm: Optional[float] = None
    min_year: Optional[int] = None
    max_year: Optional[int] = None
    keys: Optional[List[str]] = None
    sort_by: str = "bpm"
    playlist_name: Optional[str] = None

    @validator('target_minutes')
    def validate_target_minutes(cls, v):
        if v < 1 or v > 1440:
            raise ValueError('target_minutes must be between 1 and 1440')
        return v

    @validator('min_bpm', 'max_bpm')
    def validate_bpm(cls, v):
        if v is not None and (v < 0 or v > 500):
            raise ValueError('BPM must be between 0 and 500')
        return v

    @validator('min_year', 'max_year')
    def validate_year(cls, v):
        if v is not None and (v < 1900 or v > 2100):
            raise ValueError('Year must be between 1900 and 2100')
        return v

    @validator('sort_by')
    def validate_sort_by(cls, v):
        if v not in ['bpm', 'year', 'key', 'random']:
            raise ValueError('sort_by must be one of: bpm, year, key, random')
        return v

    @validator('max_bpm')
    def validate_bpm_range(cls, v, values):
        if v is not None and 'min_bpm' in values and values['min_bpm'] is not None:
            if v < values['min_bpm']:
                raise ValueError('max_bpm must be greater than or equal to min_bpm')
        return v

    @validator('max_year')
    def validate_year_range(cls, v, values):
        if v is not None and 'min_year' in values and values['min_year'] is not None:
            if v < values['min_year']:
                raise ValueError('max_year must be greater than or equal to min_year')
        return v


@app.post("/api/library/{library_id}/generate_playlist_v2")
def generate_playlist_v2(library_id: str, params: SmartPlaylistParams):
    lib = get_library_or_404(library_id)

    def matches(t: Track) -> bool:
        if params.keyword:
            hay = f"{t.title or ''} {t.artist or ''} {t.file_path or ''}".lower()
            if params.keyword.lower() not in hay:
                return False
        bpm = t.bpm
        year = t.year
        key = (t.key or "").upper()

        if params.min_bpm is not None:
            if bpm is None or bpm < params.min_bpm:
                return False
        if params.max_bpm is not None:
            if bpm is None or bpm > params.max_bpm:
                return False
        if params.min_year is not None:
            if year is None or year < params.min_year:
                return False
        if params.max_year is not None:
            if year is None or year > params.max_year:
                return False
        if params.keys:
            allowed = [k.upper() for k in params.keys]
            # Only filter if track has a key; allow tracks without keys to pass through
            if key and key not in allowed:
                return False
        return True

    candidates = [t for t in lib.tracks if matches(t)]

    if params.sort_by == "bpm":
        candidates.sort(key=lambda t: (t.bpm is None, t.bpm or 0))
    elif params.sort_by == "year":
        candidates.sort(key=lambda t: (t.year is None, t.year or 0))
    elif params.sort_by == "key":
        candidates.sort(key=lambda t: (t.key is None, t.key or ""))
    elif params.sort_by == "random":
        import random
        random.shuffle(candidates)

    total_sec = 0
    selected: List[Track] = []
    for t in candidates:
        dur = t.duration_seconds or DEFAULT_DURATION_SECONDS
        if total_sec >= params.target_minutes * 60:
            break
        selected.append(t)
        total_sec += dur

    name = params.playlist_name or f"Smart {params.target_minutes} min"
    playlist_id = lib.add_playlist(name, [t.id for t in selected])

    return {
        "playlist_id": playlist_id,
        "name": name,
        "track_count": len(selected),
        "approx_duration_minutes": int(round(total_sec / 60)) if selected else 0,
    }


class MergePlaylistsRequest(BaseModel):
    source_playlist_ids: List[str]
    name: str
    deduplicate: bool = True

    @validator('source_playlist_ids')
    def validate_source_playlists(cls, v):
        if not v:
            raise ValueError('source_playlist_ids list cannot be empty')
        # Check for duplicates in the source list
        if len(v) != len(set(v)):
            raise ValueError('source_playlist_ids contains duplicates')
        return v

    @validator('name')
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError('name cannot be empty')
        if len(v) > 200:
            raise ValueError('name too long (max 200 characters)')
        return v.strip()


@app.post("/api/library/{library_id}/merge_playlists")
def merge_playlists(library_id: str, body: MergePlaylistsRequest):
    lib = get_library_or_404(library_id)
    all_track_ids: List[str] = []
    for pid in body.source_playlist_ids:
        pl = lib.playlists.get(pid)
        if pl is None:
            raise HTTPException(status_code=404, detail=f"Playlist {pid} not found")
        all_track_ids.extend(pl.track_ids)

    if body.deduplicate:
        seen: set[str] = set()
        deduped: List[str] = []
        for tid in all_track_ids:
            if tid in seen:
                continue
            seen.add(tid)
            deduped.append(tid)
        all_track_ids = deduped

    new_id = lib.add_playlist(body.name, all_track_ids)
    return {
        "playlist_id": new_id,
        "track_count": len(all_track_ids),
    }


@app.get("/api/library/{library_id}/transitions")
def suggest_transitions(
    library_id: str,
    from_track_id: str,
    bpm_tolerance: float = Query(5.0, ge=0, le=50),
    max_results: int = Query(20, ge=1, le=100),
):
    """Suggest simple next tracks based on BPM + key proximity.

    Kept intentionally simple for UI:
    - Same key (case-insensitive) is preferred.
    - BPM difference within `bpm_tolerance` if both tracks have BPM.
    - Falls back gracefully if metadata is missing.
    """
    lib = get_library_or_404(library_id)
    base = lib.get_track(from_track_id)
    if base is None:
        raise HTTPException(status_code=404, detail="from_track not found")

    base_bpm = base.bpm
    base_key = (base.key or "").upper()

    candidates: List[dict] = []
    for t in lib.tracks:
        if t.id == base.id:
            continue
        cand_bpm = t.bpm
        cand_key = (t.key or "").upper()

        bpm_diff = None
        bpm_ok = True
        if base_bpm is not None and cand_bpm is not None:
            bpm_diff = abs(cand_bpm - base_bpm)
            bpm_ok = bpm_diff <= bpm_tolerance

        key_match = bool(base_key and cand_key and base_key == cand_key)

        if not bpm_ok and not key_match:
            # If we have both bpm and keys and both fail, skip
            if base_bpm is not None and cand_bpm is not None and base_key and cand_key:
                continue

        candidates.append(
            {
                "id": t.id,
                "title": t.title,
                "artist": t.artist,
                "bpm": t.bpm,
                "key": t.key,
                "year": t.year,
                "bpm_diff": bpm_diff,
                "key_match": key_match,
            }
        )

    # Sort: key_match first, then bpm_diff (None goes last), then title
    def sort_key(c):
        return (
            0 if c["key_match"] else 1,
            9999 if c["bpm_diff"] is None else c["bpm_diff"],
            c["title"] or "",
        )

    candidates.sort(key=sort_key)
    if max_results > 0:
        candidates = candidates[:max_results]

    return {
        "from_track": {
            "id": base.id,
            "title": base.title,
            "artist": base.artist,
            "bpm": base.bpm,
            "key": base.key,
            "year": base.year,
        },
        "candidates": candidates,
    }


@app.get("/api/library/{library_id}/search")
def global_search(library_id: str, q: str):
    """Search tracks in a library and show where they appear.

    Returns track details plus the list of playlists where each track is used.
    """
    lib = get_library_or_404(library_id)
    
    # Require minimum query length
    if not q or len(q.strip()) < 1:
        raise HTTPException(status_code=400, detail="Search query must be at least 1 character")
    
    ql = q.lower()

    # Precompute usage map: track_id -> list of (playlist_id, playlist_name)
    usage: Dict[str, List[dict]] = {}
    for pid, pl in lib.playlists.items():
        for tid in pl.track_ids:
            usage.setdefault(tid, []).append({"id": pid, "name": pl.name})

    results: List[dict] = []
    for t in lib.tracks:
        hay = f"{t.title or ''} {t.artist or ''} {t.file_path or ''}".lower()
        if ql not in hay:
            continue
        results.append(
            {
                "track": {
                    "id": t.id,
                    "title": t.title,
                    "artist": t.artist,
                    "file_path": t.file_path,
                    "bpm": t.bpm,
                    "key": t.key,
                    "year": t.year,
                },
                "playlists": usage.get(t.id, []),
            }
        )

    return {
        "query": q,
        "results": results,
    }


# ===== Folder Management Endpoints =====

class CreateFolderRequest(BaseModel):
    name: str
    parent_id: Optional[str] = None


class CreateFolderResponse(BaseModel):
    folder_id: str
    name: str
    parent_id: Optional[str]


@app.post("/api/library/{library_id}/folders", response_model=CreateFolderResponse)
def create_folder(library_id: str, request: CreateFolderRequest):
    """Create a new playlist folder."""
    lib = get_library_or_404(library_id)
    
    # Validate parent_id if provided
    if request.parent_id and request.parent_id not in lib.folders:
        raise HTTPException(status_code=404, detail="Parent folder not found")
    
    folder_id = lib.add_folder(request.name, request.parent_id)
    
    return CreateFolderResponse(
        folder_id=folder_id,
        name=request.name,
        parent_id=request.parent_id
    )


@app.get("/api/library/{library_id}/folders")
def get_folder_hierarchy(library_id: str):
    """Get the complete folder hierarchy with playlists."""
    lib = get_library_or_404(library_id)
    return lib.get_folder_hierarchy()


@app.delete("/api/library/{library_id}/folders/{folder_id}")
def delete_folder(library_id: str, folder_id: str):
    """Delete a folder (playlists are moved to parent or root)."""
    lib = get_library_or_404(library_id)
    
    if folder_id not in lib.folders:
        raise HTTPException(status_code=404, detail="Folder not found")
    
    folder = lib.folders[folder_id]
    parent_id = folder.parent_id
    
    # Move playlists to parent folder (or root)
    for pid in folder.playlist_ids:
        if pid in lib.playlists:
            lib.playlists[pid].folder_id = parent_id
            if parent_id and parent_id in lib.folders:
                lib.folders[parent_id].playlist_ids.append(pid)
    
    # Move subfolders to parent folder (or root)
    for subfolder_id in folder.subfolder_ids:
        if subfolder_id in lib.folders:
            lib.folders[subfolder_id].parent_id = parent_id
            if parent_id and parent_id in lib.folders:
                lib.folders[parent_id].subfolder_ids.append(subfolder_id)
    
    # Remove folder from parent's subfolder list
    if parent_id and parent_id in lib.folders:
        parent_folder = lib.folders[parent_id]
        if folder_id in parent_folder.subfolder_ids:
            parent_folder.subfolder_ids.remove(folder_id)
    
    # Delete the folder
    del lib.folders[folder_id]
    
    return {"status": "deleted", "folder_id": folder_id}


class MoveFolderRequest(BaseModel):
    new_parent_id: Optional[str] = None


@app.post("/api/library/{library_id}/folders/{folder_id}/move")
def move_folder(library_id: str, folder_id: str, request: MoveFolderRequest):
    """Move a folder to a different parent folder."""
    lib = get_library_or_404(library_id)
    
    if folder_id not in lib.folders:
        raise HTTPException(status_code=404, detail="Folder not found")
    
    # Validate new parent exists
    if request.new_parent_id and request.new_parent_id not in lib.folders:
        raise HTTPException(status_code=404, detail="Target parent folder not found")
    
    # Check for circular reference
    if request.new_parent_id:
        current = request.new_parent_id
        while current:
            if current == folder_id:
                raise HTTPException(status_code=400, detail="Cannot move folder into its own subfolder")
            current = lib.folders[current].parent_id if current in lib.folders else None
    
    folder = lib.folders[folder_id]
    old_parent_id = folder.parent_id
    
    # Remove from old parent's subfolder list
    if old_parent_id and old_parent_id in lib.folders:
        old_parent = lib.folders[old_parent_id]
        if folder_id in old_parent.subfolder_ids:
            old_parent.subfolder_ids.remove(folder_id)
    
    # Add to new parent's subfolder list
    if request.new_parent_id and request.new_parent_id in lib.folders:
        new_parent = lib.folders[request.new_parent_id]
        if folder_id not in new_parent.subfolder_ids:
            new_parent.subfolder_ids.append(folder_id)
    
    # Update folder's parent
    folder.parent_id = request.new_parent_id
    
    return {"status": "moved", "folder_id": folder_id, "new_parent_id": request.new_parent_id}


class MovePlaylistToFolderRequest(BaseModel):
    folder_id: Optional[str] = None


@app.post("/api/library/{library_id}/playlists/{playlist_id}/move")
def move_playlist_to_folder(library_id: str, playlist_id: str, request: MovePlaylistToFolderRequest):
    """Move a playlist to a different folder."""
    lib = get_library_or_404(library_id)
    
    if playlist_id not in lib.playlists:
        raise HTTPException(status_code=404, detail="Playlist not found")
    
    # Validate folder exists
    if request.folder_id and request.folder_id not in lib.folders:
        raise HTTPException(status_code=404, detail="Target folder not found")
    
    playlist = lib.playlists[playlist_id]
    old_folder_id = playlist.folder_id
    
    # Remove from old folder's playlist list
    if old_folder_id and old_folder_id in lib.folders:
        old_folder = lib.folders[old_folder_id]
        if playlist_id in old_folder.playlist_ids:
            old_folder.playlist_ids.remove(playlist_id)
    
    # Add to new folder's playlist list
    if request.folder_id and request.folder_id in lib.folders:
        new_folder = lib.folders[request.folder_id]
        if playlist_id not in new_folder.playlist_ids:
            new_folder.playlist_ids.append(playlist_id)
    
    # Update playlist's folder
    playlist.folder_id = request.folder_id
    
    return {"status": "moved", "playlist_id": playlist_id, "folder_id": request.folder_id}


# ===== Custom Metadata and Tags Endpoints =====

class UpdateCustomFieldsRequest(BaseModel):
    custom_fields: dict  # Using dict instead of Dict[str, Any] for Pydantic 1.x compatibility
    
    class Config:
        arbitrary_types_allowed = True


class UpdateTagsRequest(BaseModel):
    tags: List[str]


@app.post("/api/library/{library_id}/tracks/{track_id}/custom_fields")
def update_track_custom_fields(library_id: str, track_id: str, request: UpdateCustomFieldsRequest):
    """Update custom metadata fields for a track."""
    lib = get_library_or_404(library_id)
    track = lib.get_track(track_id)
    
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    
    # Update custom fields (merge with existing)
    track.custom_fields.update(request.custom_fields)
    
    return {
        "track_id": track_id,
        "custom_fields": track.custom_fields
    }


@app.get("/api/library/{library_id}/tracks/{track_id}/custom_fields")
def get_track_custom_fields(library_id: str, track_id: str):
    """Get custom metadata fields for a track."""
    lib = get_library_or_404(library_id)
    track = lib.get_track(track_id)
    
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    
    return {
        "track_id": track_id,
        "custom_fields": track.custom_fields
    }


@app.post("/api/library/{library_id}/tracks/{track_id}/tags")
def update_track_tags(library_id: str, track_id: str, request: UpdateTagsRequest):
    """Update tags for a track."""
    lib = get_library_or_404(library_id)
    track = lib.get_track(track_id)
    
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    
    track.tags = request.tags
    
    return {
        "track_id": track_id,
        "tags": track.tags
    }


@app.get("/api/library/{library_id}/tracks/{track_id}/tags")
def get_track_tags(library_id: str, track_id: str):
    """Get tags for a track."""
    lib = get_library_or_404(library_id)
    track = lib.get_track(track_id)
    
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    
    return {
        "track_id": track_id,
        "tags": track.tags
    }


@app.get("/api/library/{library_id}/tags")
def get_all_tags(library_id: str):
    """Get all unique tags used in the library."""
    lib = get_library_or_404(library_id)
    
    all_tags = set()
    for track in lib.tracks:
        all_tags.update(track.tags)
    
    return {
        "tags": sorted(list(all_tags))
    }


@app.get("/api/library/{library_id}/custom_field_keys")
def get_custom_field_keys(library_id: str):
    """Get all custom field keys used in the library."""
    lib = get_library_or_404(library_id)
    
    all_keys = set()
    for track in lib.tracks:
        all_keys.update(track.custom_fields.keys())
    
    return {
        "custom_field_keys": sorted(list(all_keys))
    }


# ===== Playlist Similarity Comparison =====

@app.get("/api/library/{library_id}/playlists/{playlist_id}/similar")
def find_similar_playlists(
    library_id: str,
    playlist_id: str,
    min_similarity: float = Query(0.5, ge=0.0, le=1.0, description="Minimum similarity score (0-1)")
):
    """
    Find playlists similar to the given playlist based on genre, key, and BPM.
    Similarity is calculated as the average of:
    - Genre overlap ratio
    - Key overlap ratio  
    - BPM proximity ratio
    """
    lib = get_library_or_404(library_id)
    
    if playlist_id not in lib.playlists:
        raise HTTPException(status_code=404, detail="Playlist not found")
    
    source_playlist = lib.playlists[playlist_id]
    source_tracks = [lib.get_track(tid) for tid in source_playlist.track_ids if lib.get_track(tid)]
    
    if not source_tracks:
        return {
            "source_playlist_id": playlist_id,
            "source_playlist_name": source_playlist.name,
            "similar_playlists": []
        }
    
    # Calculate source playlist characteristics
    source_genres = set(t.genre for t in source_tracks if t.genre)
    source_keys = set(t.key for t in source_tracks if t.key)
    source_bpms = [t.bpm for t in source_tracks if t.bpm]
    source_avg_bpm = sum(source_bpms) / len(source_bpms) if source_bpms else None
    
    similar_playlists = []
    
    for pid, playlist in lib.playlists.items():
        if pid == playlist_id:
            continue
            
        playlist_tracks = [lib.get_track(tid) for tid in playlist.track_ids if lib.get_track(tid)]
        
        if not playlist_tracks:
            continue
        
        # Calculate target playlist characteristics
        target_genres = set(t.genre for t in playlist_tracks if t.genre)
        target_keys = set(t.key for t in playlist_tracks if t.key)
        target_bpms = [t.bpm for t in playlist_tracks if t.bpm]
        target_avg_bpm = sum(target_bpms) / len(target_bpms) if target_bpms else None
        
        # Calculate similarity scores
        scores = []
        
        # Genre similarity (Jaccard similarity)
        if source_genres and target_genres:
            genre_intersection = len(source_genres & target_genres)
            genre_union = len(source_genres | target_genres)
            genre_similarity = genre_intersection / genre_union if genre_union > 0 else 0
            scores.append(genre_similarity)
        
        # Key similarity (Jaccard similarity)
        if source_keys and target_keys:
            key_intersection = len(source_keys & target_keys)
            key_union = len(source_keys | target_keys)
            key_similarity = key_intersection / key_union if key_union > 0 else 0
            scores.append(key_similarity)
        
        # BPM similarity (proximity-based)
        if source_avg_bpm and target_avg_bpm:
            bpm_diff = abs(source_avg_bpm - target_avg_bpm)
            # Consider playlists within 20 BPM as similar, scale linearly
            bpm_similarity = max(0, 1 - (bpm_diff / 20))
            scores.append(bpm_similarity)
        
        # Calculate overall similarity (average of available scores)
        if scores:
            overall_similarity = sum(scores) / len(scores)
            
            if overall_similarity >= min_similarity:
                similar_playlists.append({
                    "playlist_id": pid,
                    "playlist_name": playlist.name,
                    "track_count": len(playlist_tracks),
                    "similarity_score": round(overall_similarity, 3),
                    "common_genres": list(source_genres & target_genres) if source_genres and target_genres else [],
                    "common_keys": list(source_keys & target_keys) if source_keys and target_keys else [],
                    "avg_bpm": round(target_avg_bpm, 1) if target_avg_bpm else None,
                    "bpm_difference": round(abs(source_avg_bpm - target_avg_bpm), 1) if source_avg_bpm and target_avg_bpm else None
                })
    
    # Sort by similarity score descending
    similar_playlists.sort(key=lambda x: x["similarity_score"], reverse=True)
    
    return {
        "source_playlist_id": playlist_id,
        "source_playlist_name": source_playlist.name,
        "source_track_count": len(source_tracks),
        "source_characteristics": {
            "genres": list(source_genres),
            "keys": list(source_keys),
            "avg_bpm": round(source_avg_bpm, 1) if source_avg_bpm else None
        },
        "similar_playlists": similar_playlists,
        "total_found": len(similar_playlists)
    }
