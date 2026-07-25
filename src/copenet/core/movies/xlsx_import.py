"""Small, dependency-free reader for the watched-movies OOXML workbook.

The source sheet is intentionally treated as append-only input. CopeNet keeps the
original title and ratings and adds TMDB identity in its own local store.
"""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile


_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_EXPECTED_HEADERS = (
    "Title",
    "Initial Rating",
    "Plot",
    "Acting",
    "Pacing",
    "Cinematography",
    "Score",
    "Impact",
    "Final Score",
)
_COMPONENT_KEYS = ("plot", "acting", "pacing", "cinematography", "score", "impact")


class WatchedWorkbookError(ValueError):
    """Raised when a watched workbook cannot be read or has an unexpected shape."""


def import_watched_workbook(path: Path) -> list[dict[str, Any]]:
    source = path.expanduser().resolve()
    if not source.is_file():
        raise WatchedWorkbookError(f"watched workbook not found: {source}")
    try:
        with ZipFile(source) as archive:
            shared_strings = _read_shared_strings(archive)
            sheet_path = _first_sheet_path(archive)
            rows = _read_rows(archive, sheet_path, shared_strings)
    except (BadZipFile, KeyError, ElementTree.ParseError) as exc:
        raise WatchedWorkbookError(f"invalid XLSX workbook: {source}") from exc
    if not rows:
        raise WatchedWorkbookError("watched workbook has no rows")

    headers = tuple(str(rows[0].get(column, "")).strip() for column in "ABCDEFGHI")
    normalized_headers = tuple(value.strip() for value in headers)
    if normalized_headers != _EXPECTED_HEADERS:
        raise WatchedWorkbookError(
            "unexpected watched workbook columns; expected: " + ", ".join(_EXPECTED_HEADERS)
        )

    watched: list[dict[str, Any]] = []
    for sheet_row, raw in enumerate(rows[1:], start=2):
        title = _title_text(raw.get("A"))
        if not title:
            continue
        components = {
            key: _number(raw.get(column))
            for key, column in zip(_COMPONENT_KEYS, "CDEFGH", strict=True)
        }
        complete = all(value is not None for value in components.values())
        watched.append(
            {
                "sourceRow": sheet_row,
                "originalTitle": title,
                "initialRating": _number(raw.get("B")),
                "components": components,
                "finalScore": _number(raw.get("I")) if complete else None,
                "ratingComplete": complete,
            }
        )
    return watched


def _read_shared_strings(archive: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    return ["".join(node.text or "" for node in item.iter(f"{{{_MAIN_NS}}}t")) for item in root]


def _first_sheet_path(archive: ZipFile) -> str:
    workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    sheets = workbook.find(f"{{{_MAIN_NS}}}sheets")
    if sheets is None or not list(sheets):
        raise WatchedWorkbookError("watched workbook has no worksheets")
    relationship_id = list(sheets)[0].attrib[f"{{{_REL_NS}}}id"]
    relationships = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    for relationship in relationships.findall(f"{{{_PACKAGE_REL_NS}}}Relationship"):
        if relationship.attrib.get("Id") != relationship_id:
            continue
        target = relationship.attrib["Target"].lstrip("/")
        return target if target.startswith("xl/") else f"xl/{target}"
    raise WatchedWorkbookError("first worksheet relationship is missing")


def _read_rows(archive: ZipFile, sheet_path: str, shared_strings: list[str]) -> list[dict[str, str]]:
    root = ElementTree.fromstring(archive.read(sheet_path))
    sheet_data = root.find(f".//{{{_MAIN_NS}}}sheetData")
    if sheet_data is None:
        return []
    rows: list[dict[str, str]] = []
    for row in sheet_data.findall(f"{{{_MAIN_NS}}}row"):
        values: dict[str, str] = {}
        for cell in row.findall(f"{{{_MAIN_NS}}}c"):
            reference = cell.attrib.get("r", "")
            match = re.match(r"[A-Z]+", reference)
            if match:
                values[match.group()] = _cell_value(cell, shared_strings)
        rows.append(values)
    return rows


def _cell_value(cell: ElementTree.Element, shared_strings: list[str]) -> str:
    inline = cell.find(f"{{{_MAIN_NS}}}is")
    if inline is not None:
        return "".join(node.text or "" for node in inline.iter(f"{{{_MAIN_NS}}}t"))
    value = cell.find(f"{{{_MAIN_NS}}}v")
    if value is None or value.text is None:
        return ""
    if cell.attrib.get("t") == "s":
        index = int(value.text)
        return shared_strings[index] if 0 <= index < len(shared_strings) else ""
    return value.text


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _title_text(value: Any) -> str:
    text = str(value or "").strip()
    if re.fullmatch(r"\d+\.0", text):
        return text[:-2]
    return text
