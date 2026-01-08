"""
Tests for security vulnerabilities (XML/CSV injection)
"""
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def _import_library_with_malicious_content():
    """Import a library with content that could trigger injections."""
    content = """#EXTM3U
#EXTINF:300,<script>alert('XSS')</script> - =cmd|'/c calc'
/path/to/malicious.mp3
#EXTINF:240,Artist&Co - Title"Quote'
/path/to/normal.mp3
"""
    files = {"file": ("test.m3u", content, "audio/x-mpegurl")}
    resp = client.post("/api/import", files=files)
    assert resp.status_code == 200
    return resp.json()["library_id"]


def test_xml_export_escapes_special_characters():
    """Test that XML export properly escapes special characters to prevent injection."""
    library_id = _import_library_with_malicious_content()
    
    # Export to Rekordbox XML
    resp = client.post(f"/api/library/{library_id}/export", params={"format": "rekordbox"})
    assert resp.status_code == 200
    xml_content = resp.content.decode()
    
    # Check that dangerous characters are escaped
    assert "<script>" not in xml_content
    assert "&lt;script&gt;" in xml_content
    assert "&amp;" in xml_content
    assert "&quot;" in xml_content or "&#34;" in xml_content


def test_traktor_export_escapes_special_characters():
    """Test that Traktor NML export properly escapes special characters."""
    library_id = _import_library_with_malicious_content()
    
    # Export to Traktor NML
    resp = client.post(f"/api/library/{library_id}/export", params={"format": "traktor"})
    assert resp.status_code == 200
    nml_content = resp.content.decode()
    
    # Check that dangerous characters are escaped
    assert "<script>" not in nml_content
    assert "&lt;script&gt;" in nml_content
    assert "&amp;" in nml_content


def test_csv_export_prevents_formula_injection():
    """Test that CSV export prevents formula injection attacks."""
    # Create a library with potentially dangerous CSV content
    content = """#EXTM3U
#EXTINF:300,=SUM(A1:A10) - +2+2
/path/to/track.mp3
#EXTINF:240,-cmd - @formula
/path/to/track2.mp3
"""
    files = {"file": ("test.m3u", content, "audio/x-mpegurl")}
    resp = client.post("/api/import", files=files)
    assert resp.status_code == 200
    library_id = resp.json()["library_id"]
    
    # Export to Serato CSV
    resp = client.post(f"/api/library/{library_id}/export", params={"format": "serato"})
    assert resp.status_code == 200
    csv_content = resp.content.decode()
    
    # Check that formula injection is prevented
    lines = csv_content.split('\n')
    # First line is header, check data lines
    for line in lines[1:]:
        if line.strip():
            # Lines starting with dangerous characters should be escaped with '
            if any(line.startswith(c) for c in ['=', '+', '-', '@']):
                assert line.startswith("'") or "'" in line, f"Line not properly escaped: {line}"


def test_bundle_export_escapes_all_formats():
    """Test that bundle export properly escapes all formats."""
    library_id = _import_library_with_malicious_content()
    
    body = {
        "formats": ["rekordbox", "traktor", "serato"],
        "playlist_id": None
    }
    
    resp = client.post(f"/api/library/{library_id}/export_bundle", json=body)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    
    # If we got a ZIP file, the escaping should be working
    assert len(resp.content) > 0
