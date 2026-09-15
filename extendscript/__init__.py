"""
ExtendScript asset loader and bundle manager.
Reads and caches JSX files from disk for injection into After Effects.
"""

import os
from functools import lru_cache

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))


@lru_cache(maxsize=4)
def get_json2_source() -> str:
    """Read json2.jsx ES3 polyfill source."""
    path = os.path.join(_CURRENT_DIR, "json2.jsx")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


@lru_cache(maxsize=4)
def get_dom_helpers_source() -> str:
    """Read dom_helpers.jsx source."""
    path = os.path.join(_CURRENT_DIR, "dom_helpers.jsx")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def build_bundled_script(script_body: str, include_dom_helpers: bool = True) -> str:
    """
    Bundle script_body with json2.jsx and optionally dom_helpers.jsx.
    """
    parts = [get_json2_source()]
    if include_dom_helpers:
        parts.append(get_dom_helpers_source())
    parts.append(script_body)
    return "\n\n".join(parts)
