# BeatPorter

BeatPorter is a tiny web tool for DJs who live in Rekordbox, Serato, Traktor and folders full of `.m3u`.

Drop in a playlist file, tidy your library, and walk away with mix‑ready exports – all in one simple page.

## What you can do with it

From the browser, you can:

- **Drag & drop any supported playlist**
  - Rekordbox XML
  - Serato CSV
  - Traktor NML
  - M3U / M3U8
- **See your library at a glance**
  - Total tracks / playlists
  - Estimated total playtime
  - BPM and year ranges
- **Run quick health checks**
  - Spot tracks that are missing title / artist / file path
  - See where BPM, key or year metadata is missing
  - Find duplicate tracks by artist + title
- **Export for different platforms**
  - One‑click **M3U export**
  - **Multi‑format export bundle** (M3U + other formats) as a ZIP
  - **Mix‑ready text export** – numbered tracklist sorted by BPM, with BPM / key / year, ready to print or keep next to the mixer
- **Build smarter playlists**
  - Generate sets by BPM / year window and duration target
  - Use the results as a starting point for a 2‑hour techno set, warm‑up, closing set, etc.
- **Search & inspect**
  - Search by track, artist or file path
  - See which playlists use each track

All of this runs in your browser – just point it at the container and start dragging files.

## Dark / light theme

BeatPorter ships with a **dark club mode** and a **light studio mode**:

- Use the **moon / sun toggle** in the header to switch themes.
- Your choice is remembered (per browser) so the app opens in your favourite look.

The UI is fully responsive and works on laptops, tablets and phones.

## Drag & drop UX

The dropzone is designed for “I’m in a hurry” flows:

- Large drop target with format hints
- Animated glow when you drag a file over it
- Click it if you prefer a classic file picker

Once your library is loaded, the header will show the number of tracks and the summary cards will update in real time.

## Mix‑ready export

The **Mix‑ready export** button takes your library and turns it into a human‑readable tracklist:

- Sorted by BPM by default (you can tweak this later in the code)
- Shows **BPM / key / year** for each track
- Lets you choose a **target length** in minutes (roughly 6 minutes per track as a starting point)

The output is plain text, so you can:

- Paste it into your notes app
- Print it and keep it next to the decks
- Share it with a back‑to‑back partner

## Running with Docker

1. Build and start the stack:

   ```bash
   docker compose up --build
   ```

2. Open the app in your browser:

   ```text
   http://localhost:8000/static/
   ```

3. Drag a playlist file into the drop area and watch the metrics update.

The backend is a small **FastAPI** service; the frontend is a single static HTML file that talks to it via JSON.

## Local development

```bash
python -m venv .venv
source .venv/bin/activate      # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
pytest
uvicorn backend.app.main:app --reload
```

Then open:

```text
http://localhost:8000/static/
```

and iterate on `frontend/index.html`.

---

BeatPorter is meant to stay small, fast, and DJ‑friendly.  
If you want to wire it into your own tools, the FastAPI backend is easy to extend with more endpoints and formats.
