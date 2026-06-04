"""Fast (non-integration) unit tests for the page-provenance helper.

These tests exercise ``_extract_page`` in isolation — no Docling, no DB,
no network.  They run under ``uv run pytest -m "not integration"``.
"""
from src.ingest import _extract_page


# ---------------------------------------------------------------------------
# (a) Primary path: doc_items[0].prov[0].page_no → int
# ---------------------------------------------------------------------------

def test_primary_path_page_no():
    """First prov entry's page_no is returned as an int."""
    dl_meta = {
        "doc_items": [
            {"prov": [{"page_no": 3}]},
        ]
    }
    assert _extract_page(dl_meta) == 3


def test_primary_path_page_key_fallback():
    """When page_no is absent but page is present, use page."""
    dl_meta = {
        "doc_items": [
            {"prov": [{"page": 7}]},
        ]
    }
    assert _extract_page(dl_meta) == 7


def test_primary_path_string_int():
    """String integers are coerced to int."""
    dl_meta = {
        "doc_items": [
            {"prov": [{"page_no": "5"}]},
        ]
    }
    assert _extract_page(dl_meta) == 5


# ---------------------------------------------------------------------------
# (b) Fallback: first item lacks prov, a later item has it
# ---------------------------------------------------------------------------

def test_fallback_first_item_empty_prov():
    """First doc_item has empty prov list; second item's prov is used."""
    dl_meta = {
        "doc_items": [
            {"prov": []},
            {"prov": [{"page_no": 2}]},
        ]
    }
    assert _extract_page(dl_meta) == 2


def test_fallback_first_item_missing_prov_key():
    """First doc_item has no prov key at all; second item's prov is used."""
    dl_meta = {
        "doc_items": [
            {},
            {"prov": [{"page_no": 9}]},
        ]
    }
    assert _extract_page(dl_meta) == 9


def test_fallback_first_prov_none_value():
    """First prov entry has page_no=None; fallback finds a later one."""
    dl_meta = {
        "doc_items": [
            {"prov": [{"page_no": None}]},
            {"prov": [{"page_no": 4}]},
        ]
    }
    assert _extract_page(dl_meta) == 4


# ---------------------------------------------------------------------------
# (c) Missing / garbled meta → None
# ---------------------------------------------------------------------------

def test_empty_dict_returns_none():
    assert _extract_page({}) is None


def test_no_doc_items_key_returns_none():
    assert _extract_page({"headings": ["Intro"]}) is None


def test_empty_doc_items_returns_none():
    assert _extract_page({"doc_items": []}) is None


def test_garbled_page_value_returns_none():
    """Non-numeric page value should not raise; returns None."""
    dl_meta = {
        "doc_items": [
            {"prov": [{"page_no": "not-a-number"}]},
        ]
    }
    assert _extract_page(dl_meta) is None


def test_none_meta_treated_as_empty():
    """Passing an empty dict (what .get('dl_meta', {}) returns) → None."""
    assert _extract_page({}) is None
