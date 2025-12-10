
from __future__ import annotations
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .models import Library, Track
from .parsers import detect_format, parse_m3u, parse_rekordbox_xml, parse_serato_csv, parse_traktor_nml

app = FastAPI(title="BeatPorter v0.6")

LIBRARIES: Dict[str, Library] = {}


def get_library_or_404(library_id: str) -> Library:
    lib = LIBRARIES.get(library_id)
    if not lib:
        raise HTTPException(status_code=404, detail="Library not found")
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
    content = await file.read()
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
    return ImportResponse(
        library_id=lib.id,
        source_format=meta["source_format"],
        track_count=meta["track_count"],
        playlist_count=meta["playlist_count"],
    )


@app.get("/api/library/{library_id}")
def get_library(library_id: str):
    lib = get_library_or_404(library_id)
    return {
        "id": lib.id,
        "name": lib.name,
        "track_count": len(lib.tracks),
        "playlist_count": len(lib.playlists),
    }


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
        dur = t.duration_seconds or 300
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
    changed = 0
    for t in lib.tracks:
        path = t.file_path or ""
        if req.search in path:
            t.file_path = path.replace(req.search, req.replace)
            changed += 1
    return {"changed_tracks": changed}



def _render_export_tracks(tracks: List[Track], fmt: str) -> str:
    fmt = fmt.lower()
    if fmt == "m3u":
        lines = ["#EXTM3U"]
        for t in tracks:
            dur = t.duration_seconds or 300
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
                    t.title or "",
                    t.artist or "",
                    t.file_path or "",
                    t.key or "",
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
            loc = t.file_path or ""
            lines.append(
                f'    <TRACK TrackID="{i}" Name="{t.title}" Artist="{t.artist}" '
                f'Location="{loc}" AverageBpm="{t.bpm or ""}" Year="{t.year or ""}" '
                f'TotalTime="{t.duration_seconds or 300}" Tonality="{t.key or ""}" />'
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
            title = t.title or ""
            artist = t.artist or ""
            bpm = t.bpm or ""
            key = t.key or ""
            year = t.year or ""
            file_path = t.file_path or ""
            dir_part = ""
            file_name = file_path
            if "/" in file_path:
                dir_part = file_path.rsplit("/", 1)[0] + "/"
                file_name = file_path.rsplit("/", 1)[1]
            lines.append(
                f'    <ENTRY TITLE="{title}" ARTIST="{artist}">'
                f'<INFO BPM="{bpm}" MUSICAL_KEY="{key}" RELEASE_DATE="{year}-01-01" />'
                f'<LOCATION DIR="{dir_part}" FILE="{file_name}" />'
                f"</ENTRY>"
            )
        lines.append("  </COLLECTION>")
        lines.append("  <PLAYLISTS>")
        lines.append('    <NODE NAME="ROOT" TYPE="FOLDER">')
        lines.append('      <NODE NAME="Exported" TYPE="PLAYLIST">')
        for i, _t in enumerate(tracks, start=1):
            lines.append(f'        <ENTRY KEY="{i}" />')
        lines.append("      </NODE>")
        lines.append("    </NODE>")
        lines.append("  </PLAYLISTS>")
        lines.append("</NML>")
        return "\n".join(lines)

    raise HTTPException(status_code=400, detail="Unsupported export format")


@app.post("/api/library/{library_id}/export")
def export_library(
    library_id: str,
    format: str = Query(..., alias="format"),
    playlist_id: Optional[str] = None,
):
    lib = get_library_or_404(library_id)
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
            f = fmt.lower()
            if f == "m3u":
                fname = "library.m3u"
            elif f == "serato":
                fname = "library_serato.csv"
            elif f == "rekordbox":
                fname = "library_rekordbox.xml"
            elif f == "traktor":
                fname = "library_traktor.nml"
            else:
                raise HTTPException(status_code=400, detail=f"Unsupported export format in bundle: {fmt}")
            z.writestr(fname, text)

    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="beatporter_export.zip"'},
    )


from collections import defaultdict

def _normalize_for_dup(value: str | None) -> str:
    if not value:
        return ""
    value = value.strip().lower()
    return "".join(ch for ch in value if ch.isalnum() or ch.isspace())


@app.get("/api/library/{library_id}/duplicates")
def get_duplicates(library_id: str):
    lib = get_library_or_404(library_id)
    buckets: Dict[tuple, List[Track]] = defaultdict(list)

    for t in lib.tracks:
        norm_title = _normalize_for_dup(getattr(t, "title", None))
        norm_artist = _normalize_for_dup(getattr(t, "artist", None))
        file_name = ""
        path = getattr(t, "file_path", None)
        if path:
            file_name = path.replace("\\", "/").split("/")[-1].lower()
        key = (norm_artist, norm_title, file_name)
        buckets[key].append(t)

    groups: List[dict] = []
    for (_a, _t, _f), tracks in buckets.items():
        if len(tracks) < 2:
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
        bpm = getattr(t, "bpm", None)
        key = getattr(t, "key", None)
        year = getattr(t, "year", None)
        path = getattr(t, "file_path", None)
        title = getattr(t, "title", None)
        artist = getattr(t, "artist", None)

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
        before = (t.title, t.artist, getattr(t, "key", None), getattr(t, "year", None))

        if req.normalize_whitespace:
            if getattr(t, "title", None):
                t.title = t.title.strip()
            if getattr(t, "artist", None):
                t.artist = t.artist.strip()
            if getattr(t, "key", None):
                t.key = t.key.strip()
                while "  " in t.key:
                    t.key = t.key.replace("  ", " ")

        if req.upper_case_keys and getattr(t, "key", None):
            t.key = t.key.upper()

        if req.zero_year_to_null and getattr(t, "year", None) == 0:
            t.year = None

        after = (t.title, t.artist, getattr(t, "key", None), getattr(t, "year", None))
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

    bpms = [t.bpm for t in lib.tracks if getattr(t, "bpm", None) is not None]
    years = [t.year for t in lib.tracks if getattr(t, "year", None) is not None]

    bpm_min = min(bpms) if bpms else None
    bpm_max = max(bpms) if bpms else None
    bpm_avg = round(sum(bpms) / len(bpms), 1) if bpms else None

    year_min = min(years) if years else None
    year_max = max(years) if years else None

    key_distribution: Dict[str, int] = {}
    for t in lib.tracks:
        key = (t.key or "").strip().upper()
        if not key:
            continue
        key_distribution[key] = key_distribution.get(key, 0) + 1

    artist_counts: Dict[str, int] = {}
    for t in lib.tracks:
        artist = (t.artist or "").strip()
        if not artist:
            continue
        artist_counts[artist] = artist_counts.get(artist, 0) + 1

    top_artists = sorted(
        [{"artist": a, "count": c} for a, c in artist_counts.items()],
        key=lambda x: (-x["count"], x["artist"]),
    )[:10]

    total_seconds = 0
    default_duration = 300
    for t in lib.tracks:
        total_seconds += t.duration_seconds or default_duration

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

    current_year = datetime.datetime.utcnow().year
    valid_exts = {".mp3", ".wav", ".aiff", ".aif", ".flac", ".m4a", ".ogg"}

    for t in lib.tracks:
        tid = t.id
        path = t.file_path or ""
        bpm = getattr(t, "bpm", None)
        year = getattr(t, "year", None)
        dur = getattr(t, "duration_seconds", None)

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


@app.post("/api/library/{library_id}/generate_playlist_v2")
def generate_playlist_v2(library_id: str, params: SmartPlaylistParams):
    lib = get_library_or_404(library_id)

    def matches(t: Track) -> bool:
        if params.keyword:
            hay = f"{t.title or ''} {t.artist or ''} {t.file_path or ''}".lower()
            if params.keyword.lower() not in hay:
                return False
        bpm = getattr(t, "bpm", None)
        year = getattr(t, "year", None)
        key = (getattr(t, "key", None) or "").upper()

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
            if key and key not in allowed:
                return False
        return True

    candidates = [t for t in lib.tracks if matches(t)]

    if params.sort_by == "bpm":
        candidates.sort(key=lambda t: (getattr(t, "bpm", None) is None, getattr(t, "bpm", 0)))
    elif params.sort_by == "year":
        candidates.sort(key=lambda t: (getattr(t, "year", None) is None, getattr(t, "year", 0)))
    elif params.sort_by == "key":
        candidates.sort(key=lambda t: (getattr(t, "key", None) is None, getattr(t, "key", "")))
    elif params.sort_by == "random":
        import random
        random.shuffle(candidates)

    total_sec = 0
    selected: List[Track] = []
    for t in candidates:
        dur = t.duration_seconds or 300
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
    bpm_tolerance: float = 5.0,
    max_results: int = 20,
):
    """Suggest simple next tracks based on BPM + key proximity.

    Kept intentionally simple for UI:
    - Same key (case-insensitive) is preferred.
    - BPM difference within `bpm_tolerance` if both tracks have BPM.
    - Falls back gracefully if metadata is missing.
    """
    lib = get_library_or_404(library_id)
    base = None
    for t in lib.tracks:
        if t.id == from_track_id:
            base = t
            break
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