
# BeatPorter

BeatPorter is a tiny web app + API that takes the chaos of DJ library files
and turns it into something clean, searchable, and portable.

![BeatPorter - Initial View (Dark Mode)](https://github.com/user-attachments/assets/e855d3c1-f99f-4b1d-90e5-6e1bac262564)

Drag in a playlist file and BeatPorter will:
- detect its format (Rekordbox, Serato, Traktor, M3U),
- parse tracks + playlists into a neutral in‑memory library,
- let you clean things up,
- and export everything back out again in multiple formats.

The focus is:
- **simple web UI** you can run locally or in a small server,
- **predictable API** that is easy to automate,
- **no external database** – everything happens in memory per import.

## What you can do with it

From a single import you can:

- 🔁 **Convert between formats**
  - Import Rekordbox XML, Serato CSV, Traktor NML, or M3U
  - Export as M3U / Serato CSV / Rekordbox XML / Traktor NML / TXT
  - Or download a **multi‑format bundle** in one ZIP

- 🧹 **Clean up your library**
  - Find duplicate tracks (title + artist + filename heuristics)
  - Detect broken / suspicious metadata
    - empty titles / artists
    - missing / suspicious BPM values
    - missing years, missing file paths
  - Apply safe, mechanical fixes:
    - trim whitespace
    - normalize key casing (8a → 8A)
    - convert `year = 0` to `null`
  - Run a quick **health check**:
    - missing or odd file paths
    - obviously non‑audio extensions
    - very short durations (< 30s)
    - unusual BPM (< 60 or > 200)
    - unusual year (< 1950 or in the far future)

- 🎛 **Build DJ‑friendly playlists**
  - Generate a simple “2h of techno from 1995–2015” style set:
    - filter by BPM range, year range, keys, keyword
    - control approximate total length (in minutes)
    - choose sort order (BPM / year / key / random)
  - Merge multiple playlists into one combined list

- 🔍 **Navigate a big library**
  - Ask for suggested **transition candidates** from a given track:
    - prefers same key
    - keeps BPM within a configurable tolerance
    - gracefully handles missing metadata
  - Search by title / artist / file path and see:
    - where each track lives (playlist usage)
  - Get a fast **stats snapshot**:
    - total tracks / playlists
    - BPM range + average
    - year range
    - key distribution
    - top artists
    - approximate total playtime

The UI features dark and light modes, keyboard shortcuts for power users,
bulk track operations, drag-and-drop reordering, and visual analytics charts.
It's designed to be quick to use in practice and easy to evolve.

---

## Screenshots

### Dark Mode (Default)
![BeatPorter - Dark Mode](https://github.com/user-attachments/assets/e855d3c1-f99f-4b1d-90e5-6e1bac262564)
*Clean, modern dark interface with a single dropzone to get started.*

### Light Mode
![BeatPorter - Light Mode](https://github.com/user-attachments/assets/4619219d-26fd-40b0-846e-82cd98afdca0)
*Toggle to light mode with a single click (or press `T`) for comfortable viewing in any environment.*

### Track Browser with Bulk Selection
![Track Browser with Bulk Operations](https://github.com/user-attachments/assets/d7b492db-3a57-4489-a691-f4d1d5bf977d)
*Browse and search through your tracks with sortable columns, pagination, and bulk selection for batch operations.*

### Analytics Dashboard
![Analytics Modal](https://github.com/user-attachments/assets/514181bd-f494-4e63-b953-61aabba27e6e)
*Visual charts showing BPM distribution, year distribution, key analysis, and genre breakdown of your library.*

### Keyboard Shortcuts
![Keyboard Shortcuts Modal](https://github.com/user-attachments/assets/1e62b5df-0f2f-432f-9f5d-d56b2ef7613d)
*Power user friendly with keyboard shortcuts for all common actions. Press `?` to view all available shortcuts.*

## Running the app

### Option 1: Docker / docker compose

Prerequisites:
- Docker
- docker compose (v2)

Clone the project and then:

```bash
docker compose up --build
```

This will:
- build a small image with FastAPI + the static frontend,
- expose the app on **http://localhost:8080**.

Open that URL in your browser, drag a playlist file into the dropzone,
and start playing with the tools.

### Option 2: Local Python environment

Prerequisites:
- Python 3.11+

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the app:

```bash
uvicorn backend.app.main:app --reload --port 8080
```

Then open **http://localhost:8080** in your browser.

---

## API overview

All endpoints are under `/api`.

### Import a library

```http
POST /api/import
Content-Type: multipart/form-data
file: <playlist file>
```

Response:

```json
{
  "library_id": "uuid",
  "source_format": "rekordbox_xml|serato_csv|traktor_nml|m3u",
  "track_count": 123,
  "playlist_count": 7
}
```

Internally the library is kept in memory under that `library_id` until
the process is restarted.

### Inspect tracks

```http
GET /api/library/{id}/tracks
```

Returns a flat list of tracks with basic metadata.

### Export to a single format

```http
POST /api/library/{id}/export?format=m3u|serato|rekordbox|traktor|txt
```

Returns a text body in the chosen format. Use this to save a new playlist
back into your DJ software.

The `txt` format exports a simple numbered tracklist in the format:
```
1. Artist - Title
2. Artist - Title
...
```

### Export a multi‑format bundle

```http
POST /api/library/{id}/export_bundle
Content-Type: application/json

{
  "formats": ["m3u", "rekordbox", "traktor", "txt"],
  "playlist_id": null
}
```

Returns a `application/zip` containing e.g.:

- `library.m3u`
- `library_rekordbox.xml`
- `library_traktor.nml`
- `library_tracklist.txt`

If `playlist_id` is provided, only that playlist’s tracks are exported.

### Duplicate finder

```http
GET /api/library/{id}/duplicates
```

Groups potential duplicates based on:
- normalized artist,
- normalized title,
- filename (where available).

Each group contains the list of track IDs and their core metadata.

### Metadata issues

```http
GET /api/library/{id}/metadata_issues
```

Returns:

```json
{
  "total_tracks": 123,
  "issues": {
    "empty_title": ["track-id", "..."],
    "empty_artist": ["track-id", "..."],
    "missing_bpm": ["track-id", "..."],
    "suspicious_bpm": ["track-id", "..."],
    "missing_key": ["track-id", "..."],
    "missing_year": ["track-id", "..."],
    "missing_file_path": ["track-id", "..."]
  }
}
```

#### Auto‑fix helper

```http
POST /api/library/{id}/metadata_auto_fix
Content-Type: application/json

{
  "normalize_whitespace": true,
  "upper_case_keys": true,
  "zero_year_to_null": true
}
```

Applies safe, mechanical cleanup in‑place.

### Path rewrite (for moved crates)

Preview:

```http
POST /api/library/{id}/preview_rewrite_paths
{
  "search": "/old/disk/",
  "replace": "/new/ssd/"
}
```

Apply:

```http
POST /api/library/{id}/apply_rewrite_paths
{
  "search": "/old/disk/",
  "replace": "/new/ssd/"
}
```

### Smart playlist generator

Version 2 endpoint:

```http
POST /api/library/{id}/generate_playlist_v2
{
  "target_minutes": 120,
  "keyword": "techno",
  "min_bpm": 120,
  "max_bpm": 140,
  "min_year": 1995,
  "max_year": 2015,
  "keys": ["8A", "9A"],
  "sort_by": "bpm",
  "playlist_name": "Techno 2h 1995–2015"
}
```

Returns a new playlist object and the actual duration.

### Playlist merge helper

```http
POST /api/library/{id}/merge_playlists
{
  "source_playlist_ids": ["id1", "id2"],
  "name": "Combined crate",
  "deduplicate": true
}
```

Creates a new playlist containing the unique union of tracks.

### Transition assistant

```http
GET /api/library/{id}/transitions
  ?from_track_id=<track-id>
  &bpm_tolerance=5
  &max_results=20
```

Returns a ranked list of candidate tracks, preferring:
- same key,
- BPM close to the source track,
- stable sort so results feel deterministic.

### Global search + usage

```http
GET /api/library/{id}/search?q=acid
```

Finds tracks by title / artist / file path and shows which playlists each
track belongs to.

### Library stats

```http
GET /api/library/{id}/stats
```

Aggregate snapshot as described above.

### Library health

```http
GET /api/library/{id}/health
```

Light‑weight health report as described above.

---

## Tests & CI

Tests are written with `pytest`.

Run them locally with:

```bash
PYTHONPATH=. pytest -q
```

The project also includes a GitHub Actions workflow in
`.github/workflows/tests.yml` that runs the same command on each push /
pull request.

If you keep the structure intact, you can drop this folder into a repo,
enable Actions, and immediately get simple CI for your BeatPorter
instance.

---

BeatPorter is deliberately small and opinionated. It’s not trying to
replace a full DJ library manager – it’s trying to sit on the side,
be your neutral translator + janitor, and make it easier to move
between ecosystems without losing your mind (or your crates).

---

## Roadmap

BeatPorter is focused on staying lean and practical, but here are some features and improvements on the horizon:

### Near-term (Next few releases)

- **🎨 Enhanced UI Features**
  - Dark/light mode toggle
  - Drag-and-drop track reordering within playlists
  - Keyboard shortcuts for common actions
  - Bulk track selection and operations

- **🔧 Advanced Library Management**
  - Auto-save library state to localStorage for quick recovery
  - Support for importing multiple files at once
  - Playlist folders and hierarchical organization
  - Custom metadata fields and tags

- **📊 Better Analytics**
  - Visual charts for BPM distribution, year distribution, and key analysis
  - Energy level analysis and visualization
  - Genre detection and classification
  - Playlist similarity comparison

### Mid-term

- **🔄 Format Improvements**
  - Support for additional formats (Engine DJ, VirtualDJ, Denon)
  - Better metadata preservation across conversions
  - Cue point and beatgrid support
  - Artwork/cover art management

- **🤖 Smart Features**
  - AI-powered duplicate detection improvements
  - Automatic playlist generation based on mood/energy
  - Smart recommendations for track order
  - Automatic BPM and key detection for files

- **💾 Persistence Options**
  - Optional PostgreSQL/SQLite backend for larger libraries
  - Export/import library as portable JSON
  - Cloud storage integration (Dropbox, Google Drive)
  - Multi-user support with shared libraries

### Long-term Ideas

- **🎵 Audio Analysis**
  - Direct audio file analysis (no DJ software needed)
  - Waveform visualization
  - Harmonic mixing suggestions
  - Audio fingerprinting for better duplicate detection

- **🌐 Collaboration**
  - Share playlists with other DJs
  - Public playlist gallery
  - Collaborative playlist editing
  - Version control for library changes

- **📱 Mobile Support**
  - Progressive Web App (PWA) support
  - Touch-optimized interface
  - Offline mode
  - Mobile file picker integration

### Community Contributions Welcome!

BeatPorter is open to community input. If you have ideas, feature requests, or want to contribute:
- Open an issue on GitHub with your suggestion
- Submit a pull request with improvements
- Share your use cases and workflows

The goal is to keep BeatPorter simple and focused, but flexible enough to handle real DJ workflows.
