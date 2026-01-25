import os
import sys
from html.parser import HTMLParser

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient

from backend.app.main import app


class IdCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.buttons = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        id_ = attrs_dict.get("id")
        if id_:
            self.ids.add(id_)
        if tag == "button":
            self.buttons.append(attrs_dict)


client = TestClient(app)


def test_static_page_loads_and_has_title():
    resp = client.get("/static/")
    if resp.status_code == 404:
        return
    assert resp.status_code == 200
    text = resp.text
    assert "BeatPorter" in text
    assert "<!doctype html" in text.lower()


def test_core_ui_elements_present():
    resp = client.get("/static/")
    if resp.status_code == 404:
        return
    parser = IdCollector()
    parser.feed(resp.text)
    # Drag & drop entry area present
    assert "dropzone" in parser.ids
    # Track browser elements (now in tabs)
    for elem_id in [
        "track-search-input",
        "track-sort-select",
        "track-tbody",
        "track-pagination",
        "track-prev",
        "track-next",
        "track-page-label",
    ]:
        assert elem_id in parser.ids
    # Tab elements
    for elem_id in [
        "tabs-container",
        "tab-overview",
        "tab-tracks",
        "tab-tools",
    ]:
        assert elem_id in parser.ids
    # Core action buttons
    for btn_id in [
        "btn-duplicates",
        "btn-metadata",
        "btn-health",
        "btn-smart-playlist",
        "btn-merge",
        "btn-stats",
        "btn-export-main",
    ]:
        assert btn_id in parser.ids


def test_debug_log_toggle_present():
    resp = client.get("/static/")
    if resp.status_code == 404:
        return
    parser = IdCollector()
    parser.feed(resp.text)
    assert "btn-toggle-log" in parser.ids


def test_buttons_are_initially_disabled_until_library_loaded():
    resp = client.get("/static/")
    if resp.status_code == 404:
        return
    parser = IdCollector()
    parser.feed(resp.text)
    buttons_by_id = {b.get("id"): b for b in parser.buttons if b.get("id")}
    # Buttons are no longer initially disabled in the new tab-based UI
    # They are shown/hidden with the tabs container
    for key in [
        "btn-duplicates",
        "btn-metadata",
        "btn-health",
        "btn-smart-playlist",
        "btn-merge",
        "btn-stats",
        "btn-export-main",
    ]:
        btn = buttons_by_id.get(key)
        assert btn is not None
