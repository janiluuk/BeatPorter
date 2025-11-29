
import io
import uuid
from typing import Dict, List, Optional

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .models import Library, Playlist, Track
from .parsers import detect_format, parse_m3u, parse_rekordbox_xml, parse_serato_csv, parse_traktor_nml

app = FastAPI(title="BeatPorter v0.4")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="../../frontend", html=True), name="static")

LIBRARIES: Dict[str, Library] = {}

class PathRewriteRequest(BaseModel):
    search: str
    replace: str
    playlist_id: Optional[str] = None

class GeneratePlaylistResponse(BaseModel):
    playlist_id: str
    name: str
    track_count: int
    approx_duration_minutes: int

def _build_library_from_tracks(tracks: List[Track], playlists: List[Playlist], source_format: str) -> Library:
    lib_id = str(uuid.uuid4())
    tracks_dict = {t.id: t for t in tracks}
    library = Library(
        id=lib_id,
        source_format=source_format,
        tracks=tracks_dict,
        playlists=playlists,
    )
    LIBRARIES[lib_id] = library
    return library

@app.post("/api/import")
async def import_library(file: UploadFile = File(...)):
    content = await file.read()
    fmt = detect_format(file.filename, content)

    if fmt == "m3u":
        tracks, playlists, src = parse_m3u(content)
    elif fmt == "rekordbox":
        tracks, playlists, src = parse_rekordbox_xml(content)
    elif fmt == "serato":
        tracks, playlists, src = parse_serato_csv(content)
    elif fmt == "traktor":
        tracks, playlists, src = parse_traktor_nml(content)
    else:
        raise HTTPException(status_code=400, detail=f"Could not detect format for file '{file.filename}'")

    library = _build_library_from_tracks(tracks, playlists, src)
    return {
        "library_id": library.id,
        "source_format": library.source_format,
        "track_count": len(library.tracks),
        "playlist_count": len(library.playlists),
        "playlists": [p.dict() for p in library.playlists],
    }

@app.get("/api/library/{library_id}")
async def get_library(library_id: str):
    library = LIBRARIES.get(library_id)
    if not library:
        raise HTTPException(status_code=404, detail="Library not found")
    return library

@app.get("/api/library/{library_id}/tracks")
async def list_tracks(
    library_id: str,
    q: Optional[str] = Query(None, description="Search query for title/artist/path"),
    key: Optional[str] = Query(None, description="Filter by musical key"),
    sort: str = Query("newest", description="Sort order: newest|oldest|title|bpm|key|year"),
    playlist_id: Optional[str] = Query(None, description="Limit to a specific playlist"),
):
    library = LIBRARIES.get(library_id)
    if not library:
        raise HTTPException(status_code=404, detail="Library not found")

    tracks: List[Track] = list(library.tracks.values())

    if playlist_id:
        pl = next((p for p in library.playlists if p.id == playlist_id), None)
        if not pl:
            raise HTTPException(status_code=404, detail="Playlist not found")
        track_set = set(pl.track_ids)
        tracks = [t for t in tracks if t.id in track_set]

    if q:
        ql = q.lower()

        def match(t: Track) -> bool:
            return (
                ql in (t.title or "").lower()
                or ql in (t.artist or "").lower()
                or ql in (t.file_path or "").lower()
            )

        tracks = [t for t in tracks if match(t)]

    if key:
        tracks = [t for t in tracks if (t.key or "").lower() == key.lower()]

    if sort == "newest":
        tracks.sort(key=lambda t: t.id, reverse=True)
    elif sort == "oldest":
        tracks.sort(key=lambda t: t.id)
    elif sort == "title":
        tracks.sort(key=lambda t: (t.title or "").lower())
    elif sort == "bpm":
        tracks.sort(key=lambda t: (t.bpm is None, t.bpm or 0.0))
    elif sort == "key":
        tracks.sort(key=lambda t: (t.key is None, (t.key or "").lower()))
    elif sort == "year":
        tracks.sort(key=lambda t: (t.year is None, t.year or 0))

    return [t.dict() for t in tracks]

@app.post("/api/library/{library_id}/generate_playlist", response_model=GeneratePlaylistResponse)
async def generate_playlist(
    library_id: str,
    name: Optional[str] = Query(None),
    target_minutes: int = Query(120, ge=1, le=24 * 60),
    year_from: Optional[int] = Query(None),
    year_to: Optional[int] = Query(None),
    keyword: Optional[str] = Query(None),
):
    library = LIBRARIES.get(library_id)
    if not library:
        raise HTTPException(status_code=404, detail="Library not found")

    tracks: List[Track] = list(library.tracks.values())

    if year_from is not None:
        tracks = [t for t in tracks if t.year is not None and t.year >= year_from]
    if year_to is not None:
        tracks = [t for t in tracks if t.year is not None and t.year <= year_to]
    if keyword:
        ql = keyword.lower()
        tracks = [
            t
            for t in tracks
            if ql in (t.title or "").lower()
            or ql in (t.artist or "").lower()
            or ql in (t.file_path or "").lower()
        ]

    tracks.sort(key=lambda t: (t.year is None, t.year or 0))

    selected_ids: List[int] = []
    total_sec = 0
    target_sec = target_minutes * 60
    for t in tracks:
        dur = t.duration_sec if t.duration_sec is not None else 300
        if total_sec + dur > target_sec and selected_ids:
            break
        selected_ids.append(t.id)
        total_sec += dur

    if not selected_ids and tracks:
        selected_ids.append(tracks[0].id)
        total_sec = tracks[0].duration_sec or 300

    pl_name = name or "Smart playlist"
    pl_id = f"smart_{len(library.playlists)+1}"
    playlist = Playlist(id=pl_id, name=pl_name, track_ids=selected_ids)
    library.playlists.append(playlist)
    LIBRARIES[library_id] = library

    return GeneratePlaylistResponse(
        playlist_id=pl_id,
        name=pl_name,
        track_count=len(selected_ids),
        approx_duration_minutes=int(total_sec // 60),
    )

@app.post("/api/library/{library_id}/preview_rewrite_paths")
async def preview_rewrite_paths(
    library_id: str,
    req: PathRewriteRequest,
):
    library = LIBRARIES.get(library_id)
    if not library:
        raise HTTPException(status_code=404, detail="Library not found")

    tracks: List[Track] = list(library.tracks.values())
    if req.playlist_id:
        pl = next((p for p in library.playlists if p.id == req.playlist_id), None)
        if not pl:
            raise HTTPException(status_code=404, detail="Playlist not found")
        track_ids = set(pl.track_ids)
        tracks = [t for t in tracks if t.id in track_ids]

    affected = []
    for t in tracks:
        if not t.file_path or req.search not in t.file_path:
            continue
        new_path = t.file_path.replace(req.search, req.replace)
        affected.append(
            {
                "track_id": t.id,
                "title": t.title,
                "old_path": t.file_path,
                "new_path": new_path,
            }
        )

    return {
        "total_tracks": len(tracks),
        "affected_tracks": len(affected),
        "examples": affected[:50],
    }

@app.post("/api/library/{library_id}/apply_rewrite_paths")
async def apply_rewrite_paths(
    library_id: str,
    req: PathRewriteRequest,
):
    library = LIBRARIES.get(library_id)
    if not library:
        raise HTTPException(status_code=404, detail="Library not found")

    tracks: List[Track] = list(library.tracks.values())
    if req.playlist_id:
        pl = next((p for p in library.playlists if p.id == req.playlist_id), None)
        if not pl:
            raise HTTPException(status_code=404, detail="Playlist not found")
        track_ids = set(pl.track_ids)
        tracks = [t for t in tracks if t.id in track_ids]

    changed = 0
    for t in tracks:
        if not t.file_path or req.search not in t.file_path:
            continue
        t.file_path = t.file_path.replace(req.search, req.replace)
        library.tracks[t.id] = t
        changed += 1

    LIBRARIES[library_id] = library

    return {
        "total_tracks": len(tracks),
        "changed_tracks": changed,
    }

def _export_m3u(library: Library, playlist: Optional[Playlist]) -> bytes:
    lines = ["#EXTM3U"]
    track_ids = playlist.track_ids if playlist else sorted(library.tracks.keys())
    for tid in track_ids:
        t = library.tracks.get(tid)
        if not t or not t.file_path:
            continue
        dur = t.duration_sec if t.duration_sec is not None else -1
        title = f"{t.artist} - {t.title}" if t.artist and t.title else (t.title or t.artist or "")
        lines.append(f"#EXTINF:{dur},{title}")
        lines.append(t.file_path)
    return ("\n".join(lines) + "\n").encode()

def _export_serato_csv(library: Library, playlist: Optional[Playlist]) -> bytes:
    import csv

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Artist", "Title", "File", "Key", "BPM", "Year"])
    track_ids = playlist.track_ids if playlist else sorted(library.tracks.keys())
    for tid in track_ids:
        t = library.tracks.get(tid)
        if not t:
            continue
        writer.writerow(
            [
                t.artist or "",
                t.title or "",
                t.file_path or "",
                t.key or "",
                t.bpm or "",
                t.year or "",
            ]
        )
    return buf.getvalue().encode()

def _export_rekordbox_xml(library: Library, playlist: Optional[Playlist]) -> bytes:
    from xml.etree.ElementTree import Element, SubElement, tostring

    dj = Element("DJ_PLAYLISTS")
    col = SubElement(dj, "COLLECTION")
    track_ids = sorted(library.tracks.keys())
    for tid in track_ids:
        t = library.tracks[tid]
        tr = SubElement(col, "TRACK")
        tr.set("TrackID", str(tid))
        if t.title:
            tr.set("Name", t.title)
        if t.artist:
            tr.set("Artist", t.artist)
        if t.file_path:
            tr.set("Location", t.file_path)
        if t.key:
            tr.set("Tonality", t.key)
        if t.bpm is not None:
            tr.set("AverageBpm", str(t.bpm))
        if t.year is not None:
            tr.set("Year", str(t.year))
        if t.duration_sec is not None:
            tr.set("TotalTime", str(t.duration_sec))

    pls_root = SubElement(dj, "PLAYLISTS")
    root_node = SubElement(pls_root, "NODE", Name="ROOT", Type="0")
    if playlist:
        nodes = [playlist]
    else:
        nodes = library.playlists
    for pl in nodes:
        pnode = SubElement(root_node, "NODE", Name=pl.name, Type="1")
        for tid in pl.track_ids:
            if tid in library.tracks:
                tr = SubElement(pnode, "TRACK")
                tr.set("Key", str(tid))

    xml_bytes = tostring(dj, encoding="utf-8")
    return xml_bytes

def _export_traktor_nml(library: Library, playlist: Optional[Playlist]) -> bytes:
    from xml.etree.ElementTree import Element, SubElement, tostring

    nml = Element("NML")
    collection = SubElement(nml, "COLLECTION")
    track_ids_all = sorted(library.tracks.keys())
    for tid in track_ids_all:
        t = library.tracks[tid]
        e = SubElement(collection, "ENTRY")
        e.set("TITLE", t.title or "")
        e.set("ARTIST", t.artist or "")
        info = SubElement(e, "INFO")
        if t.bpm is not None:
            info.set("BPM", str(t.bpm))
        if t.key:
            info.set("MUSICAL_KEY", t.key)
        if t.year is not None:
            info.set("RELEASE_DATE", f"{t.year}-01-01")
        loc = SubElement(e, "LOCATION")
        if t.file_path:
            directory, _, file_name = t.file_path.rpartition("/")
            loc.set("DIR", directory + "/" if directory else "")
            loc.set("FILE", file_name)

    pls_root = SubElement(nml, "PLAYLISTS")
    root_node = SubElement(pls_root, "NODE", NAME="ROOT", TYPE="FOLDER")
    if playlist:
        nodes = [playlist]
    else:
        nodes = library.playlists
    for pl in nodes:
        pnode = SubElement(root_node, "NODE", NAME=pl.name, TYPE="PLAYLIST")
        for tid in pl.track_ids:
            e = SubElement(pnode, "ENTRY")
            e.set("KEY", str(tid))

    return tostring(nml, encoding="utf-8")

@app.post("/api/library/{library_id}/export")
async def export_library(
    library_id: str,
    format: str = Query(..., alias="format"),
    playlist_id: Optional[str] = Query(None),
):
    library = LIBRARIES.get(library_id)
    if not library:
        raise HTTPException(status_code=404, detail="Library not found")

    playlist = None
    if playlist_id:
        playlist = next((p for p in library.playlists if p.id == playlist_id), None)
        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")

    fmt = format.lower()
    if fmt == "m3u":
        data = _export_m3u(library, playlist)
        filename = "playlist.m3u"
        media_type = "audio/x-mpegurl"
    elif fmt == "serato":
        data = _export_serato_csv(library, playlist)
        filename = "playlist_serato.csv"
        media_type = "text/csv"
    elif fmt == "rekordbox":
        data = _export_rekordbox_xml(library, playlist)
        filename = "playlist_rekordbox.xml"
        media_type = "application/xml"
    elif fmt == "traktor":
        data = _export_traktor_nml(library, playlist)
        filename = "playlist_traktor.nml"
        media_type = "application/xml"
    else:
        raise HTTPException(status_code=400, detail="Unsupported export format")

    return StreamingResponse(
        io.BytesIO(data),
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
