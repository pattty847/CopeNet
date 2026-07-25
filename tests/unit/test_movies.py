from pathlib import Path
from zipfile import ZipFile

from copenet.core.movies.matching import match_decision, rank_candidates
from copenet.core.movies.service import MovieLabService, _select_diverse
from copenet.core.movies.store import MovieLabStore
from copenet.core.movies.xlsx_import import import_watched_workbook


def test_watched_xlsx_import_preserves_ratings_and_treats_incomplete_zero_as_unrated(tmp_path: Path) -> None:
    workbook = tmp_path / "watched.xlsx"
    _write_fixture_workbook(workbook)

    watched = import_watched_workbook(workbook)

    assert [item["originalTitle"] for item in watched] == ["Interstellar", "2012"]
    assert watched[0]["sourceRow"] == 2
    assert watched[0]["finalScore"] == 9.5
    assert watched[0]["ratingComplete"] is True
    assert watched[1]["initialRating"] == 7.0
    assert watched[1]["finalScore"] is None
    assert watched[1]["ratingComplete"] is False


def test_matching_accepts_unique_exact_title_but_reviews_ambiguous_exact_titles() -> None:
    exact = rank_candidates(
        "Interstellar",
        [{"id": 157336, "media_type": "movie", "title": "Interstellar", "popularity": 80}],
    )
    assert match_decision("Interstellar", exact)["status"] == "matched"

    ambiguous = rank_candidates(
        "The Game",
        [
            {"id": 2649, "media_type": "movie", "title": "The Game", "release_date": "1997-09-12", "popularity": 40},
            {"id": 123, "media_type": "movie", "title": "The Game", "release_date": "1984-01-01", "popularity": 2},
        ],
    )
    decision = match_decision("The Game", ambiguous)
    assert decision["status"] == "review"
    assert "release year" in decision["reason"]


def test_matching_uses_tv_hint_and_dominant_canonical_exact_result() -> None:
    hannibal = rank_candidates(
        "Hannibal TV Show",
        [
            {"id": 40008, "media_type": "tv", "name": "Hannibal", "popularity": 20},
            {"id": 9740, "media_type": "movie", "title": "Hannibal", "popularity": 2},
        ],
    )
    assert match_decision("Hannibal TV Show", hannibal)["selected"]["mediaType"] == "tv"

    inception = rank_candidates(
        "Inception",
        [
            {"id": 27205, "media_type": "movie", "title": "Inception", "popularity": 40},
            {"id": 1359046, "media_type": "movie", "title": "Inception", "popularity": 0.9},
        ],
    )
    assert match_decision("Inception", inception)["selected"]["tmdbId"] == 27205


def test_movie_report_uses_enriched_genres_and_excludes_unrated_rows(tmp_path: Path) -> None:
    store = MovieLabStore(tmp_path / "movie-lab.json")
    store.replace_watched(
        [
            {
                "sourceRow": 2,
                "originalTitle": "Interstellar",
                "initialRating": 10.0,
                "components": {"plot": 10.0, "acting": 9.0, "pacing": 9.0, "cinematography": 10.0, "score": 10.0, "impact": 10.0},
                "finalScore": 9.6,
                "ratingComplete": True,
            },
            {
                "sourceRow": 3,
                "originalTitle": "Arrival",
                "initialRating": 7.0,
                "components": {"plot": None, "acting": None, "pacing": None, "cinematography": None, "score": None, "impact": None},
                "finalScore": None,
                "ratingComplete": False,
            },
        ],
        source=tmp_path / "watched.xlsx",
    )
    store.save_match(
        2,
        {"status": "matched", "method": "automatic", "selected": {"tmdbId": 157336, "mediaType": "movie"}},
    )
    store.save_catalog_item(
        {"tmdbId": 157336, "mediaType": "movie", "genres": [{"id": 878, "name": "Science Fiction"}]}
    )

    report = MovieLabService(store).report()

    assert report["watched"] == 2
    assert report["fullyRated"] == 1
    assert report["averageFinalScore"] == 9.6
    assert report["genrePerformance"] == [
        {"genre": "Science Fiction", "watched": 1, "averageFinalScore": 9.6}
    ]


def test_recommendation_selection_limits_one_seed_from_dominating_a_lane() -> None:
    ranked = [
        {"title": "A1", "becauseOf": ["A"]},
        {"title": "A2", "becauseOf": ["A"]},
        {"title": "A3", "becauseOf": ["A"]},
        {"title": "B1", "becauseOf": ["B"]},
        {"title": "C1", "becauseOf": ["C"]},
    ]

    selected = _select_diverse(ranked, 4, max_per_primary_seed=2)

    assert [item["title"] for item in selected] == ["A1", "A2", "B1", "C1"]


def _write_fixture_workbook(path: Path) -> None:
    content_types = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>"""
    root_rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""
    workbook = """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets>
</workbook>"""
    workbook_rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>"""
    headers = ["Title", "Initial Rating", "Plot", "Acting", "Pacing", "Cinematography", "Score", "Impact", "Final Score"]
    header_cells = "".join(_inline_cell(f"{chr(65 + index)}1", value) for index, value in enumerate(headers))
    complete = ["Interstellar", 10, 10, 9, 9, 10, 10, 10, 9.5]
    incomplete = ["2012", 7, None, None, None, None, None, None, 0]
    rows = [
        f'<row r="1">{header_cells}</row>',
        f'<row r="2">{"".join(_fixture_cell(f"{chr(65 + index)}2", value) for index, value in enumerate(complete))}</row>',
        f'<row r="3"><c r="A3"><v>2012.0</v></c>{"".join(_fixture_cell(f"{chr(65 + index)}3", value) for index, value in list(enumerate(incomplete))[1:])}</row>',
        '<row r="4"><c r="I4"><v>0</v></c></row>',
    ]
    sheet = f'''<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{"".join(rows)}</sheetData></worksheet>'''
    with ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)


def _fixture_cell(reference: str, value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return _inline_cell(reference, value)
    return f'<c r="{reference}"><v>{value}</v></c>'


def _inline_cell(reference: str, value: str) -> str:
    return f'<c r="{reference}" t="inlineStr"><is><t>{value}</t></is></c>'
