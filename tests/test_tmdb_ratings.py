import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tmdb_ratings import (
    _clean_title_for_search,
    pick_best_tmdb_search_result,
    score_tmdb_title_match,
)


def test_score_prefers_matching_title_over_popularity_noise():
    q = "Pillion"
    low_pop = {
        "id": 2,
        "title": "Pillion",
        "original_title": "Pillion",
        "popularity": 0.5,
    }
    high_pop = {
        "id": 1,
        "title": "Some Other Film",
        "original_title": "Otro",
        "popularity": 99.0,
    }
    assert score_tmdb_title_match(q, low_pop) > score_tmdb_title_match(q, high_pop)


def test_pick_best_chooses_similar_title_not_most_popular():
    q = "Pillion"
    results = [
        {
            "id": 1,
            "title": "Blockbuster",
            "original_title": "Blockbuster",
            "popularity": 100.0,
        },
        {
            "id": 2,
            "title": "Pillion",
            "original_title": "Pillion",
            "popularity": 1.0,
        },
    ]
    best = pick_best_tmdb_search_result(q, results)
    assert best is not None
    assert best["id"] == 2


def test_clean_title_strips_trailing_doblada_esp_without_parentheses():
    t = _clean_title_for_search("Little Amélie Doblada ESP")
    assert "doblada" not in t.casefold()
    assert t.strip().casefold().startswith("little")


def test_clean_title_strips_trailing_vose_without_parentheses():
    assert _clean_title_for_search("El agente secreto VOSE").strip().casefold() == (
        "el agente secreto"
    )
    assert _clean_title_for_search("Cumbres borrascosas VOSE").strip().casefold() == (
        "cumbres borrascosas"
    )


def test_spanish_title_matches_original_english():
    q = "El arquitecto"
    r = {
        "id": 3,
        "title": "El arquitecto",
        "original_title": "The Architect",
        "popularity": 2.0,
    }
    assert score_tmdb_title_match(q, r) >= 0.5
