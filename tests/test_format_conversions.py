"""
Tests for format conversions between Rekordbox XML and Traktor NML.
Ensures that conversions preserve all metadata and playlists.
"""

import os
import sys
import io
import zipfile

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.parsers import (
    DEFAULT_DURATION_SECONDS,
    parse_m3u,
    parse_rekordbox_xml,
    parse_traktor_nml,
)
from backend.app.main import _render_export_tracks

client = TestClient(app)


def test_m3u_negative_extinf_duration_defaults():
    m3u_content = b"""#EXTM3U
#EXTINF:-1,Artist - Title
/music/track.mp3
"""

    lib, _ = parse_m3u("test.m3u", m3u_content)

    assert len(lib.tracks) == 1
    assert lib.tracks[0].duration_seconds == DEFAULT_DURATION_SECONDS


def test_rekordbox_import_and_export():
    """Test that importing and exporting Rekordbox XML preserves all data."""
    rekordbox_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<DJ_PLAYLISTS Version="1.0">
  <COLLECTION Entries="2">
    <TRACK TrackID="1" Name="Track One" Artist="Artist One" 
           Location="file://localhost/Music/track1.mp3" 
           AverageBpm="128.00" Year="2020" 
           TotalTime="300" Tonality="8A" />
    <TRACK TrackID="2" Name="Track Two" Artist="Artist Two" 
           Location="file://localhost/Music/track2.mp3" 
           AverageBpm="140.00" Year="2021" 
           TotalTime="240" Tonality="5A" />
  </COLLECTION>
  <PLAYLISTS>
    <NODE Type="0" Name="ROOT">
      <NODE Name="Test Playlist" Type="1">
        <TRACK Key="1"/>
        <TRACK Key="2"/>
      </NODE>
    </NODE>
  </PLAYLISTS>
</DJ_PLAYLISTS>
"""
    
    # Parse original
    lib1, meta1 = parse_rekordbox_xml("test.xml", rekordbox_xml)
    assert len(lib1.tracks) == 2
    assert len(lib1.playlists) == 1
    assert lib1.tracks[0].title == "Track One"
    assert lib1.tracks[0].duration_seconds == 300
    assert lib1.tracks[1].duration_seconds == 240
    
    # Export and re-import
    exported = _render_export_tracks(lib1.tracks, "rekordbox")
    lib2, meta2 = parse_rekordbox_xml("exported.xml", exported.encode())
    
    # Verify data is preserved
    assert len(lib2.tracks) == 2
    assert len(lib2.playlists) == 1
    assert lib2.tracks[0].title == "Track One"
    assert lib2.tracks[0].artist == "Artist One"
    assert lib2.tracks[0].bpm == 128.0
    assert lib2.tracks[0].year == 2020
    assert lib2.tracks[0].key == "8A"
    assert lib2.tracks[0].duration_seconds == 300
    assert lib2.tracks[1].duration_seconds == 240


def test_traktor_import_and_export():
    """Test that importing and exporting Traktor NML preserves all data."""
    traktor_nml = b"""<?xml version="1.0" encoding="UTF-8" standalone="no" ?>
<NML VERSION="19">
  <COLLECTION>
    <ENTRY TITLE="Track One" ARTIST="Artist One">
      <INFO BPM="128.00" MUSICAL_KEY="8A" RELEASE_DATE="2020-01-01" PLAYTIME="300" />
      <LOCATION DIR="/Music/" FILE="track1.mp3" />
    </ENTRY>
    <ENTRY TITLE="Track Two" ARTIST="Artist Two">
      <INFO BPM="140.00" MUSICAL_KEY="5A" RELEASE_DATE="2021-01-01" PLAYTIME="240" />
      <LOCATION DIR="/Music/" FILE="track2.mp3" />
    </ENTRY>
  </COLLECTION>
  <PLAYLISTS>
    <NODE NAME="ROOT" TYPE="FOLDER">
      <NODE NAME="Test Playlist" TYPE="PLAYLIST">
        <ENTRY KEY="/Music/track1.mp3"/>
        <ENTRY KEY="/Music/track2.mp3"/>
      </NODE>
    </NODE>
  </PLAYLISTS>
</NML>
"""
    
    # Parse original
    lib1, meta1 = parse_traktor_nml("test.nml", traktor_nml)
    assert len(lib1.tracks) == 2
    assert len(lib1.playlists) == 1
    assert lib1.tracks[0].title == "Track One"
    assert lib1.tracks[0].duration_seconds == 300
    assert lib1.tracks[1].duration_seconds == 240
    
    # Export and re-import
    exported = _render_export_tracks(lib1.tracks, "traktor")
    lib2, meta2 = parse_traktor_nml("exported.nml", exported.encode())
    
    # Verify data is preserved
    assert len(lib2.tracks) == 2
    assert len(lib2.playlists) == 1
    assert lib2.tracks[0].title == "Track One"
    assert lib2.tracks[0].artist == "Artist One"
    assert lib2.tracks[0].bpm == 128.0
    assert lib2.tracks[0].year == 2020
    assert lib2.tracks[0].key == "8A"
    assert lib2.tracks[0].duration_seconds == 300
    assert lib2.tracks[1].duration_seconds == 240


def test_rekordbox_to_traktor_conversion():
    """Test conversion from Rekordbox XML to Traktor NML."""
    rekordbox_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<DJ_PLAYLISTS Version="1.0">
  <COLLECTION Entries="2">
    <TRACK TrackID="1" Name="Track One" Artist="Artist One" 
           Location="file://localhost/Music/track1.mp3" 
           AverageBpm="128.00" Year="2020" 
           TotalTime="300" Tonality="8A" />
    <TRACK TrackID="2" Name="Track Two" Artist="Artist Two" 
           Location="file://localhost/Music/track2.mp3" 
           AverageBpm="140.00" Year="2021" 
           TotalTime="240" Tonality="5A" />
  </COLLECTION>
  <PLAYLISTS>
    <NODE Type="0" Name="ROOT">
      <NODE Name="My Playlist" Type="1">
        <TRACK Key="1"/>
        <TRACK Key="2"/>
      </NODE>
    </NODE>
  </PLAYLISTS>
</DJ_PLAYLISTS>
"""
    
    # Parse Rekordbox
    lib_rb, _ = parse_rekordbox_xml("test.xml", rekordbox_xml)
    
    # Convert to Traktor
    traktor_output = _render_export_tracks(lib_rb.tracks, "traktor")
    lib_tr, _ = parse_traktor_nml("exported.nml", traktor_output.encode())
    
    # Verify conversion preserves data
    assert len(lib_tr.tracks) == 2
    assert len(lib_tr.playlists) == 1
    assert lib_tr.tracks[0].title == "Track One"
    assert lib_tr.tracks[0].artist == "Artist One"
    assert lib_tr.tracks[0].bpm == 128.0
    assert lib_tr.tracks[0].year == 2020
    assert lib_tr.tracks[0].key == "8A"
    assert lib_tr.tracks[0].duration_seconds == 300
    assert lib_tr.tracks[1].duration_seconds == 240


def test_traktor_to_rekordbox_conversion():
    """Test conversion from Traktor NML to Rekordbox XML."""
    traktor_nml = b"""<?xml version="1.0" encoding="UTF-8" standalone="no" ?>
<NML VERSION="19">
  <COLLECTION>
    <ENTRY TITLE="Track One" ARTIST="Artist One">
      <INFO BPM="128.00" MUSICAL_KEY="8A" RELEASE_DATE="2020-01-01" PLAYTIME="300" />
      <LOCATION DIR="/Music/" FILE="track1.mp3" />
    </ENTRY>
    <ENTRY TITLE="Track Two" ARTIST="Artist Two">
      <INFO BPM="140.00" MUSICAL_KEY="5A" RELEASE_DATE="2021-01-01" PLAYTIME="240" />
      <LOCATION DIR="/Music/" FILE="track2.mp3" />
    </ENTRY>
  </COLLECTION>
  <PLAYLISTS>
    <NODE NAME="ROOT" TYPE="FOLDER">
      <NODE NAME="My Playlist" TYPE="PLAYLIST">
        <ENTRY KEY="/Music/track1.mp3"/>
        <ENTRY KEY="/Music/track2.mp3"/>
      </NODE>
    </NODE>
  </PLAYLISTS>
</NML>
"""
    
    # Parse Traktor
    lib_tr, _ = parse_traktor_nml("test.nml", traktor_nml)
    
    # Convert to Rekordbox
    rekordbox_output = _render_export_tracks(lib_tr.tracks, "rekordbox")
    lib_rb, _ = parse_rekordbox_xml("exported.xml", rekordbox_output.encode())
    
    # Verify conversion preserves data
    assert len(lib_rb.tracks) == 2
    assert len(lib_rb.playlists) == 1
    assert lib_rb.tracks[0].title == "Track One"
    assert lib_rb.tracks[0].artist == "Artist One"
    assert lib_rb.tracks[0].bpm == 128.0
    assert lib_rb.tracks[0].year == 2020
    assert lib_rb.tracks[0].key == "8A"
    assert lib_rb.tracks[0].duration_seconds == 300
    assert lib_rb.tracks[1].duration_seconds == 240


def test_rekordbox_to_traktor_to_rekordbox_roundtrip():
    """Test full round-trip: Rekordbox -> Traktor -> Rekordbox."""
    rekordbox_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<DJ_PLAYLISTS Version="1.0">
  <COLLECTION Entries="2">
    <TRACK TrackID="1" Name="Track One" Artist="Artist One" 
           Location="file://localhost/Music/track1.mp3" 
           AverageBpm="128.00" Year="2020" 
           TotalTime="300" Tonality="8A" />
    <TRACK TrackID="2" Name="Track Two" Artist="Artist Two" 
           Location="file://localhost/Music/track2.mp3" 
           AverageBpm="140.00" Year="2021" 
           TotalTime="240" Tonality="5A" />
  </COLLECTION>
  <PLAYLISTS>
    <NODE Type="0" Name="ROOT">
      <NODE Name="My Playlist" Type="1">
        <TRACK Key="1"/>
        <TRACK Key="2"/>
      </NODE>
    </NODE>
  </PLAYLISTS>
</DJ_PLAYLISTS>
"""
    
    # Parse original Rekordbox
    lib1, _ = parse_rekordbox_xml("test.xml", rekordbox_xml)
    
    # Convert to Traktor
    traktor_output = _render_export_tracks(lib1.tracks, "traktor")
    lib2, _ = parse_traktor_nml("exported.nml", traktor_output.encode())
    
    # Convert back to Rekordbox
    rekordbox_output = _render_export_tracks(lib2.tracks, "rekordbox")
    lib3, _ = parse_rekordbox_xml("re-exported.xml", rekordbox_output.encode())
    
    # Verify all data is preserved through round-trip
    assert len(lib3.tracks) == 2
    assert len(lib3.playlists) == 1
    assert lib1.tracks[0].title == lib3.tracks[0].title
    assert lib1.tracks[0].artist == lib3.tracks[0].artist
    assert lib1.tracks[0].bpm == lib3.tracks[0].bpm
    assert lib1.tracks[0].year == lib3.tracks[0].year
    assert lib1.tracks[0].key == lib3.tracks[0].key
    assert lib1.tracks[0].duration_seconds == lib3.tracks[0].duration_seconds
    assert lib1.tracks[1].duration_seconds == lib3.tracks[1].duration_seconds


def test_traktor_to_rekordbox_to_traktor_roundtrip():
    """Test full round-trip: Traktor -> Rekordbox -> Traktor."""
    traktor_nml = b"""<?xml version="1.0" encoding="UTF-8" standalone="no" ?>
<NML VERSION="19">
  <COLLECTION>
    <ENTRY TITLE="Track One" ARTIST="Artist One">
      <INFO BPM="128.00" MUSICAL_KEY="8A" RELEASE_DATE="2020-01-01" PLAYTIME="300" />
      <LOCATION DIR="/Music/" FILE="track1.mp3" />
    </ENTRY>
    <ENTRY TITLE="Track Two" ARTIST="Artist Two">
      <INFO BPM="140.00" MUSICAL_KEY="5A" RELEASE_DATE="2021-01-01" PLAYTIME="240" />
      <LOCATION DIR="/Music/" FILE="track2.mp3" />
    </ENTRY>
  </COLLECTION>
  <PLAYLISTS>
    <NODE NAME="ROOT" TYPE="FOLDER">
      <NODE NAME="My Playlist" TYPE="PLAYLIST">
        <ENTRY KEY="/Music/track1.mp3"/>
        <ENTRY KEY="/Music/track2.mp3"/>
      </NODE>
    </NODE>
  </PLAYLISTS>
</NML>
"""
    
    # Parse original Traktor
    lib1, _ = parse_traktor_nml("test.nml", traktor_nml)
    
    # Convert to Rekordbox
    rekordbox_output = _render_export_tracks(lib1.tracks, "rekordbox")
    lib2, _ = parse_rekordbox_xml("exported.xml", rekordbox_output.encode())
    
    # Convert back to Traktor
    traktor_output = _render_export_tracks(lib2.tracks, "traktor")
    lib3, _ = parse_traktor_nml("re-exported.nml", traktor_output.encode())
    
    # Verify all data is preserved through round-trip
    assert len(lib3.tracks) == 2
    assert len(lib3.playlists) == 1
    assert lib1.tracks[0].title == lib3.tracks[0].title
    assert lib1.tracks[0].artist == lib3.tracks[0].artist
    assert lib1.tracks[0].bpm == lib3.tracks[0].bpm
    assert lib1.tracks[0].year == lib3.tracks[0].year
    assert lib1.tracks[0].key == lib3.tracks[0].key
    assert lib1.tracks[0].duration_seconds == lib3.tracks[0].duration_seconds
    assert lib1.tracks[1].duration_seconds == lib3.tracks[1].duration_seconds


def test_api_import_rekordbox_and_export_traktor():
    """Test API endpoint for importing Rekordbox and exporting to Traktor."""
    rekordbox_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<DJ_PLAYLISTS Version="1.0">
  <COLLECTION Entries="1">
    <TRACK TrackID="1" Name="Test Track" Artist="Test Artist" 
           Location="file://localhost/Music/test.mp3" 
           AverageBpm="128.00" Year="2020" 
           TotalTime="300" Tonality="8A" />
  </COLLECTION>
  <PLAYLISTS>
    <NODE Type="0" Name="ROOT">
      <NODE Name="Test" Type="1">
        <TRACK Key="1"/>
      </NODE>
    </NODE>
  </PLAYLISTS>
</DJ_PLAYLISTS>
"""
    
    # Import Rekordbox
    files = {"file": ("test.xml", rekordbox_xml, "application/xml")}
    resp = client.post("/api/import", files=files)
    assert resp.status_code == 200
    data = resp.json()
    library_id = data["library_id"]
    assert data["source_format"] == "rekordbox_xml"
    
    # Export to Traktor
    resp = client.post(f"/api/library/{library_id}/export", params={"format": "traktor"})
    assert resp.status_code == 200
    traktor_output = resp.content.decode()
    assert "<NML VERSION=" in traktor_output
    assert "PLAYTIME=" in traktor_output


def test_api_import_traktor_and_export_rekordbox():
    """Test API endpoint for importing Traktor and exporting to Rekordbox."""
    traktor_nml = b"""<?xml version="1.0" encoding="UTF-8" standalone="no" ?>
<NML VERSION="19">
  <COLLECTION>
    <ENTRY TITLE="Test Track" ARTIST="Test Artist">
      <INFO BPM="128.00" MUSICAL_KEY="8A" RELEASE_DATE="2020-01-01" PLAYTIME="300" />
      <LOCATION DIR="/Music/" FILE="test.mp3" />
    </ENTRY>
  </COLLECTION>
  <PLAYLISTS>
    <NODE NAME="ROOT" TYPE="FOLDER">
      <NODE NAME="Test" TYPE="PLAYLIST">
        <ENTRY KEY="/Music/test.mp3"/>
      </NODE>
    </NODE>
  </PLAYLISTS>
</NML>
"""
    
    # Import Traktor
    files = {"file": ("test.nml", traktor_nml, "application/xml")}
    resp = client.post("/api/import", files=files)
    assert resp.status_code == 200
    data = resp.json()
    library_id = data["library_id"]
    assert data["source_format"] == "traktor_nml"
    
    # Export to Rekordbox
    resp = client.post(f"/api/library/{library_id}/export", params={"format": "rekordbox"})
    assert resp.status_code == 200
    rekordbox_output = resp.content.decode()
    assert "<DJ_PLAYLISTS" in rekordbox_output
    assert "TotalTime=" in rekordbox_output


def test_txt_export_format():
    """Test TXT export format with numbered tracklist."""
    from backend.app.models import Track, Library
    
    # Create a simple library with test tracks
    lib = Library(id="test-lib", name="Test Library")
    track1 = Track(
        id="t1",
        title="First Track",
        artist="Artist One",
        file_path="/music/track1.mp3",
        duration_seconds=300,
    )
    track2 = Track(
        id="t2",
        title="Second Track",
        artist="Artist Two",
        file_path="/music/track2.mp3",
        duration_seconds=240,
    )
    track3 = Track(
        id="t3",
        title="No Artist Track",
        artist="",
        file_path="/music/track3.mp3",
        duration_seconds=180,
    )
    lib.add_track(track1)
    lib.add_track(track2)
    lib.add_track(track3)
    
    # Export to TXT
    txt_output = _render_export_tracks(lib.tracks, "txt")
    
    # Verify format
    lines = txt_output.split("\n")
    assert len(lines) == 3
    assert lines[0] == "1. Artist One - First Track"
    assert lines[1] == "2. Artist Two - Second Track"
    assert lines[2] == "3. No Artist Track"


def test_api_export_txt_format():
    """Test API endpoint for TXT export."""
    m3u_content = b"""#EXTM3U
#EXTINF:300,Artist One - Track One
/music/track1.mp3
#EXTINF:240,Artist Two - Track Two
/music/track2.mp3
"""
    
    # Import M3U
    files = {"file": ("test.m3u", m3u_content, "audio/x-mpegurl")}
    resp = client.post("/api/import", files=files)
    assert resp.status_code == 200
    data = resp.json()
    library_id = data["library_id"]
    
    # Export to TXT
    resp = client.post(f"/api/library/{library_id}/export", params={"format": "txt"})
    assert resp.status_code == 200
    txt_output = resp.content.decode()
    
    # Verify format
    lines = txt_output.strip().split("\n")
    assert len(lines) == 2
    assert "Artist One - Track One" in lines[0]
    assert "Artist Two - Track Two" in lines[1]
    assert lines[0].startswith("1. ")
    assert lines[1].startswith("2. ")


def test_export_bundle_includes_txt():
    """Test that TXT format can be included in export bundle."""
    m3u_content = b"""#EXTM3U
#EXTINF:300,Artist - Track
/music/track.mp3
"""
    
    # Import M3U
    files = {"file": ("test.m3u", m3u_content, "audio/x-mpegurl")}
    resp = client.post("/api/import", files=files)
    assert resp.status_code == 200
    data = resp.json()
    library_id = data["library_id"]
    
    # Export bundle with TXT format
    resp = client.post(
        f"/api/library/{library_id}/export_bundle",
        json={"formats": ["m3u", "txt"]},
    )
    assert resp.status_code == 200
    assert "application/zip" in resp.headers.get("content-type", "")
    
    # Verify ZIP contains TXT file
    buf = io.BytesIO(resp.content)
    with zipfile.ZipFile(buf, "r") as z:
        names = z.namelist()
        assert "library.m3u" in names
        assert "library_tracklist.txt" in names
        
        # Verify TXT content
        txt_content = z.read("library_tracklist.txt").decode()
        assert "Artist - Track" in txt_content
        assert "1. " in txt_content

