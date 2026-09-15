"""
Unit tests for ExtendScript syntax compliance, ES3 compatibility, and bundling.
"""

import os
import re
import pytest
from extendscript import (
    get_json2_source,
    get_dom_helpers_source,
    build_bundled_script,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_all_jsx_files():
    """Locate all JSX files in the repository."""
    jsx_files = []
    for root, _, files in os.walk(REPO_ROOT):
        # Ignore virtualenv or cache
        if ".venv" in root or "__pycache__" in root or "tests" in root:
            continue
        for file in files:
            if file.endswith(".jsx"):
                jsx_files.append(os.path.join(root, file))
    return jsx_files


def strip_comments_and_strings(content: str) -> str:
    """Strip JS comments and string literals to test keywords."""
    # Remove block comments
    no_block_comments = re.sub(r"/\*[\s\S]*?\*/", "", content)
    # Remove line comments
    no_line_comments = re.sub(r"//.*", "", no_block_comments)
    # Remove strings
    no_double_strings = re.sub(r'"(?:\\.|[^"\\])*"', '""', no_line_comments)
    no_single_strings = re.sub(r"'(?:\\.|[^'\\])*'", "''", no_double_strings)
    return no_single_strings


def test_no_es6_syntax_in_jsx_files():
    """
    Strict ES3 Verification: Ensure no 'let', 'const', or arrow functions '=>'
    are used in any JSX file.
    """
    jsx_files = get_all_jsx_files()
    assert len(jsx_files) >= 4, f"Expected at least 4 JSX files, found {len(jsx_files)}"

    for jsx_path in jsx_files:
        filename = os.path.basename(jsx_path)
        with open(jsx_path, "r", encoding="utf-8") as f:
            content = f.read()

        code_only = strip_comments_and_strings(content)

        # Check for let
        let_match = re.search(r"\blet\s+[a-zA-Z_$]", code_only)
        assert let_match is None, f"ES6 'let' keyword found in {filename}: {let_match.group(0) if let_match else ''}"

        # Check for const
        const_match = re.search(r"\bconst\s+[a-zA-Z_$]", code_only)
        assert const_match is None, f"ES6 'const' keyword found in {filename}: {const_match.group(0) if const_match else ''}"

        # Check for arrow function
        arrow_match = re.search(r"\)\s*=>", code_only)
        assert arrow_match is None, f"ES6 arrow function '=>' found in {filename}"

        # Check for template literals (backticks)
        backtick_match = re.search(r"`", code_only)
        assert backtick_match is None, f"ES6 template literal backtick found in {filename}"


def test_match_names_usage():
    """Verify that JSX templates use language-invariant match names."""
    dom_helpers = get_dom_helpers_source()
    assert "ADBE Transform Group" in dom_helpers
    assert "ADBE Position" in dom_helpers
    assert "ADBE Mask Parade" in dom_helpers
    assert "ADBE Mask Shape" in dom_helpers
    assert "ADBE Root Vectors Group" in dom_helpers


def test_build_bundled_script():
    """Verify script bundling prepends json2 and dom_helpers."""
    user_code = "return 1 + 1;"
    bundled = build_bundled_script(user_code, include_dom_helpers=True)

    assert "JSON.stringify" in bundled
    assert "AEDomHelpers" in bundled
    assert "return 1 + 1;" in bundled
