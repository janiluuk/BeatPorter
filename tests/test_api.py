
    import io
    from fastapi.testclient import TestClient

    from backend.app.main import app

    client = TestClient(app)


    def _import_m3u_library():
        content = """#EXTM3U
#EXTINF:300,Artist One - First Track
/path/to/first.mp3
#EXTINF:240,Artist Two - Second Track
/path/to/second.mp3
"""
        files = {"file": ("test.m3u", content, "audio/x-mpegurl")}
        resp = client.post("/api/import", files=files)
        assert resp.status_code == 200
        data = resp.json()
        assert data["track_count"] == 2
        assert data["playlist_count"] == 1
        assert data["source_format"].startswith("m3u")
        return data["library_id"], data


    def test_import_m3u_and_list_tracks():
        library_id, _ = _import_m3u_library()

        # basic list
        resp = client.get(f"/api/library/{library_id}/tracks")
        assert resp.status_code == 200
        tracks = resp.json()
        assert len(tracks) == 2
        titles = {t["title"] for t in tracks}
        assert "First Track" in titles
        assert "Second Track" in titles

        # filter by search term
        resp = client.get(f"/api/library/{library_id}/tracks", params={"q": "Second"})
        assert resp.status_code == 200
        tracks = resp.json()
        assert len(tracks) == 1
        assert tracks[0]["title"] == "Second Track"


    def test_generate_smart_playlist_and_use_playlist_scope():
        library_id, lib_info = _import_m3u_library()

        resp = client.post(
            f"/api/library/{library_id}/generate_playlist",
            params={"target_minutes": 5, "keyword": "Artist"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["track_count"] >= 1
        playlist_id = data["playlist_id"]

        # list tracks restricted to the new playlist
        resp = client.get(
            f"/api/library/{library_id}/tracks",
            params={"playlist_id": playlist_id},
        )
        assert resp.status_code == 200
        tracks = resp.json()
        assert len(tracks) == data["track_count"]


    def test_path_rewrite_preview_and_apply():
        library_id, _ = _import_m3u_library()

        # Preview rewrite
        payload = {"search": "/path/to", "replace": "/music"}
        resp = client.post(f"/api/library/{library_id}/preview_rewrite_paths", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["affected_tracks"] == 2
        assert data["total_tracks"] == 2
        assert data["examples"]
        ex = data["examples"][0]
        assert "/path/to" in ex["old_path"]
        assert "/music" in ex["new_path"]

        # Apply rewrite
        resp = client.post(f"/api/library/{library_id}/apply_rewrite_paths", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["changed_tracks"] == 2

        # Verify tracks now show new path
        resp = client.get(f"/api/library/{library_id}/tracks")
        tracks = resp.json()
        for t in tracks:
            assert "/music" in (t["file_path"] or "")


    def test_export_formats_from_m3u():
        library_id, _ = _import_m3u_library()

        # M3U
        resp = client.post(
            f"/api/library/{library_id}/export",
            params={"format": "m3u"},
        )
        assert resp.status_code == 200
        assert resp.content.startswith(b"#EXTM3U")

        # Serato CSV
        resp = client.post(
            f"/api/library/{library_id}/export",
            params={"format": "serato"},
        )
        assert resp.status_code == 200
        text = resp.content.decode()
        assert "Artist,Title,File,Key,BPM,Year" in text

        # Rekordbox XML
        resp = client.post(
            f"/api/library/{library_id}/export",
            params={"format": "rekordbox"},
        )
        assert resp.status_code == 200
        xml = resp.content.decode()
        assert "<DJ_PLAYLISTS" in xml
        assert "<COLLECTION" in xml

        # Traktor NML
        resp = client.post(
            f"/api/library/{library_id}/export",
            params={"format": "traktor"},
        )
        assert resp.status_code == 200
        xml = resp.content.decode()
        assert "<NML" in xml
        assert "<COLLECTION" in xml


    def test_import_rekordbox_xml_detection_and_playlist():
        rb_xml = """<?xml version="1.0" encoding="UTF-8"?>
<DJ_PLAYLISTS Version="1.0">
  <COLLECTION>
    <TRACK TrackID="1" Name="RB Track" Artist="RB Artist" Location="file://localhost/C:/Music/rb_track.mp3" AverageBpm="128.0" Year="2010" TotalTime="300" Tonality="8A" />
  </COLLECTION>
  <PLAYLISTS>
    <NODE Name="ROOT" Type="0">
      <NODE Name="RB Playlist" Type="1">
        <TRACK Key="1" />
      </NODE>
    </NODE>
  </PLAYLISTS>
</DJ_PLAYLISTS>
"""
        files = {"file": ("rekordbox.xml", rb_xml, "application/xml")}
        resp = client.post("/api/import", files=files)
        assert resp.status_code == 200
        data = resp.json()
        assert data["source_format"] == "rekordbox_xml"
        assert data["track_count"] == 1
        assert data["playlist_count"] == 1


    def test_import_serato_csv_detection():
        csv_content = "Title,Artist,File,Key,BPM,Year\n" \
                      "CSV Track,CSV Artist,/music/csv_track.mp3,8A,126,2015\n"
        files = {"file": ("serato.csv", csv_content, "text/csv")}
        resp = client.post("/api/import", files=files)
        assert resp.status_code == 200
        data = resp.json()
        assert data["source_format"] == "serato_csv"
        assert data["track_count"] == 1


    def test_import_traktor_nml_detection():
        nml = """<NML VERSION="19">
  <COLLECTION>
    <ENTRY TITLE="NML Track" ARTIST="NML Artist">
      <INFO BPM="130.0" MUSICAL_KEY="9A" RELEASE_DATE="2012-01-01" />
      <LOCATION DIR="/music/" FILE="nml_track.mp3" />
    </ENTRY>
  </COLLECTION>
  <PLAYLISTS>
    <NODE NAME="ROOT" TYPE="FOLDER">
      <NODE NAME="Main" TYPE="PLAYLIST">
        <ENTRY KEY="1" />
      </NODE>
    </NODE>
  </PLAYLISTS>
</NML>
"""
        files = {"file": ("collection.nml", nml, "application/xml")}
        resp = client.post("/api/import", files=files)
        assert resp.status_code == 200
        data = resp.json()
        assert data["source_format"] == "traktor_nml"
        assert data["track_count"] == 1
        assert data["playlist_count"] >= 1
