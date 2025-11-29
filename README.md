
# BeatPorter v0.4

BeatPorter is a simple webapp for DJ playlist surgery in a browser.

- Drag-and-drop **Rekordbox XML**, **Serato CSV**, **Traktor NML** or **M3U/M3U8**.
- Get a unified library model with tracks and playlists.
- Export to:
  - Rekordbox XML
  - Serato CSV
  - M3U
  - Traktor NML
- Browse & filter tracks, sorted by:
  - Newest / Oldest
  - Title
  - BPM
  - Key
  - Year
- Pick which playlist is active with a **playlist picker**.
- Generate a **smart playlist** (e.g. “2 hours of techno from 1995–2015”).
- Rewrite file paths with **preview** before applying (for moving between OSes/drives).

## Running with Docker

Build the image:

```bash
docker build -t beatporter:0.4 .
```

Run the container:

```bash
docker run --rm -p 8080:8080 beatporter:0.4
```

Then open:

- http://localhost:8080/static/index.html

## Running with docker-compose

Use the included `docker-compose.yml` to run everything with one command:

```bash
docker-compose up --build
```

This will:
- Build the BeatPorter image from the local Dockerfile.
- Start the app container and expose port `8080` on your host.

Then open:

- http://localhost:8080/static/index.html


## Tests

Run the FastAPI tests locally with:

```bash
pip install -r requirements.txt pytest
pytest -q
```

A GitHub Actions workflow (`.github/workflows/tests.yml`) is included to run the test suite on each push and pull request.
