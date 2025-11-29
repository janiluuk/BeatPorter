
# BeatPorter v0.6

BeatPorter is a tiny webapp + API that lets you throw your chaotic DJ playlists at it and get something clean, portable and usable back.

Drag in:
- Rekordbox XML
- Serato CSV
- Traktor NML
- M3U playlists

BeatPorter will:
- Detect the format
- Parse tracks + playlists into a neutral library
- Let you clean, merge, and export that library in multiple formats.


## Features

### Core

- **Format detection & import**
  - Auto-detects M3U, Rekordbox XML, Serato CSV, Traktor NML.
  - Normalizes everything into an in-memory `Library` (tracks + playlists).

- **Track listing**
  - `GET /api/library/{id}/tracks`
  - Filter by search term `q` and/or `playlist_id`.

- **Export in multiple formats**
  - `POST /api/library/{id}/export?format=m3u|serato|rekordbox|traktor`
  - Export whole library or a single playlist.


### Phase 1: Library brain upgrades

#### 1. Duplicate Finder

`GET /api/library/{id}/duplicates`

- Groups potential duplicates by:
  - Normalized **artist**
  - Normalized **title**
  - File name (case-insensitive)
- Returns clusters like:
  ```json
  {
    "total_groups": 1,
    "duplicate_groups": [
      {
        "canonical_title": "First Track",
        "canonical_artist": "Artist One",
        "file_names": ["first.mp3", "FIRST_COPY.MP3"],
        "track_ids": ["uuid-1", "uuid-2"],
        "count": 2
      }
    ]
  }
  ```

Use it as a **dup radar** before you start deleting things in your real library.

---

#### 2. Metadata Cleanup Wizard

- `GET /api/library/{id}/metadata_issues`  
  Scans the library for:
  - `missing_bpm`
  - `missing_key`
  - `missing_year`
  - `missing_file_path`
  - `suspicious_bpm` ( > 300 )
  - `empty_title`
  - `empty_artist`

- `POST /api/library/{id}/metadata_auto_fix`
  ```json
  {
    "normalize_whitespace": true,
    "upper_case_keys": true,
    "zero_year_to_null": true
  }
  ```

Applies safe, mechanical fixes:
- Trims title/artist/key
- Uppercases key (8a → 8A)
- Converts `year = 0` to `null`

This is the “tidy up without doing anything musically opinionated” pass.

---

#### 3. Smart Playlist 2.0

`POST /api/library/{id}/generate_playlist_v2`

Body:

```json
{
  "target_minutes": 120,
  "keyword": "warehouse",
  "min_bpm": 125,
  "max_bpm": 135,
  "min_year": 1995,
  "max_year": 2015,
  "keys": ["8A", "9A"],
  "sort_by": "bpm",
  "playlist_name": "Warehouse 1995–2015"
}
```

What it does:

- Filters tracks by:
  - Text keyword (title/artist/path)
  - BPM range
  - Year range
  - Key whitelist
- Sorts them by BPM / year / key / random.
- Packs tracks until `target_minutes` is reached.
- Creates a real playlist in the library and returns:
  ```json
  {
    "playlist_id": "...",
    "name": "Warehouse 1995–2015",
    "track_count": 23,
    "approx_duration_minutes": 121
  }
  ```

This is the “build me a set skeleton” button.

---

#### 4. Playlist Merge Tool

`POST /api/library/{id}/merge_playlists`

Body:

```json
{
  "source_playlist_ids": ["p1", "p2", "p3"],
  "name": "All-time Favourites",
  "deduplicate": true
}
```

- Takes multiple playlists.
- Flattens all their tracks.
- Optionally deduplicates by track ID.
- Creates a new playlist and returns:
  ```json
  {
    "playlist_id": "new123",
    "track_count": 45
  }
  ```

This is perfect when you:
- Inherit multiple old USB playlists.
- Want one “mega crate” without manual drag-drop chaos.

---

## API Overview (Quick cheatsheet)

- `POST /api/import`  
  Upload a Rekordbox/Serato/Traktor/M3U file. Returns `library_id`.

- `GET /api/library/{id}`  
  Basic info: name, track_count, playlist_count.

- `GET /api/library/{id}/tracks`  
  Optional params: `playlist_id`, `q`.

- `POST /api/library/{id}/generate_playlist`  
  Simple “duration + keyword” playlist.

- `POST /api/library/{id}/generate_playlist_v2`  
  Advanced smart playlist with BPM/year/key filters.

- `POST /api/library/{id}/preview_rewrite_paths`  
  Show how many file paths would change when you replace a prefix.

- `POST /api/library/{id}/apply_rewrite_paths`  
  Actually apply the path change.

- `POST /api/library/{id}/export?format=...`  
  Export as m3u / serato / rekordbox / traktor.

- `GET /api/library/{id}/duplicates`  
  Find duplicate clusters.

- `GET /api/library/{id}/metadata_issues`  
  Scan for missing/suspicious metadata.

- `POST /api/library/{id}/metadata_auto_fix`  
  Auto-fix whitespace + key casing + zero-year.

- `POST /api/library/{id}/merge_playlists`  
  Merge multiple playlists into one.

---


## Phase 2: Navigation & bundles (simple UI-friendly features)

Phase 2 focuses on things you can expose in the UI as **one-click helpers**, not configuration nightmares.

### 5. Transition Assistant

`GET /api/library/{id}/transitions?from_track_id=...&bpm_tolerance=5&max_results=20`

- Input: just the **track you’re currently playing** (its ID).
- Output: a ranked list of suggested next tracks with:
  - `bpm_diff`
  - `key_match` (true/false)
- Defaults are sane:
  - `bpm_tolerance = 5` by default
  - Max 20 results

UI idea: a **single “Suggest next tracks” button** in the track detail view, no extra sliders needed.

---

### 6. Global Search with usage

`GET /api/library/{id}/search?q=warehouse`

Returns:

```json
{
  "query": "warehouse",
  "results": [
    {
      "track": {
        "id": "...",
        "title": "Warehouse Anthem",
        "artist": "Artist Two",
        "file_path": "/music/...",
        "bpm": 130,
        "key": "8A",
        "year": 2012
      },
      "playlists": [
        { "id": "p1", "name": "Peak Time" },
        { "id": "p9", "name": "Festival Set" }
      ]
    }
  ]
}
```

UI idea:
- One global search bar.
- Click a result → see “where does this track live?” as a small list of playlist badges.

---

### 7. Multi-format export bundle

`POST /api/library/{id}/export_bundle`

Body:

```json
{
  "formats": ["m3u", "rekordbox", "traktor"],
  "playlist_id": null
}
```

- Produces a `.zip` with:
  - `library.m3u`
  - `library_rekordbox.xml`
  - `library_traktor.nml`
- If `playlist_id` is set, exports **just that playlist** instead of the whole library.

UI idea:
- Simple “Export bundle” dialog:
  - Checkbox list: [x] M3U [ ] Serato [x] Rekordbox [x] Traktor
  - Optional playlist dropdown.
  - One **Export** button.

All three features are designed to map directly onto **small, focused UI widgets**:
- No multi-step wizards.
- No dense configuration panels.
- Just “click → see helpful results”.


## Running locally

### With Python

```bash
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

pip install -r requirements.txt

PYTHONPATH=. uvicorn backend.app.main:app --reload --port 8080
```

Then open:

- API docs: http://localhost:8080/docs
- Minimal UI: http://localhost:8080/static/index.html (if served)

### With Docker

```bash
docker compose up --build
```

App listens on `http://localhost:8080`.

---

## Tests

There is a small but meaningful pytest suite:

- `tests/test_api.py` – core import/export behaviours
- `tests/test_phase1_duplicates.py` – duplicate finder
- `tests/test_phase1_metadata.py` – metadata issues + auto-fix
- `tests/test_phase1_smartplaylist.py` – smart playlist v2 filters
- `tests/test_phase1_merge.py` – playlist merge / 404 behaviour

Run them with:

```bash
PYTHONPATH=. pytest -q
```

GitHub Actions CI is set up in `.github/workflows/tests.yml` to run this automatically on push/PR.

---

BeatPorter v0.5 is now a **DJ library Swiss army knife**:
- it reads multiple ecosystems,
- shows you the ugly parts (dups, broken metadata),
- helps you clean them up,
- and then spits out smart playlists and clean exports.

Next steps (Phase 2) can layer on:
- transition suggestions,
- global search,
- bundle exports,
without touching the existing contract.
