import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from utils import film_title_dedupe_key, normalize_title


def test_normalize_strips_vose():
    assert "your name" in normalize_title("Your Name (VOSE)")


def test_normalize_removes_accents_for_compare():
    a = normalize_title("Águilas de El Cairo")
    b = normalize_title("aguilas de el cairo")
    assert a == b


def test_film_title_dedupe_key_merges_vose_variants():
    a = film_title_dedupe_key("Your Name (VOSE)")
    b = film_title_dedupe_key("Your name VOSE")
    assert a == b


def test_film_title_dedupe_key_merges_doblada():
    a = film_title_dedupe_key("Little Amélie Doblada ESP")
    b = film_title_dedupe_key("Little Amélie")
    assert a == b


def test_film_title_dedupe_key_merges_vose_atmos():
    a = film_title_dedupe_key("Proyecto Salvación")
    b = film_title_dedupe_key("Proyecto Salvación (VOSE) (ATMOS)")
    c = film_title_dedupe_key("Proyecto Salvación (VOSE)")
    assert a == b == c


def test_film_title_dedupe_key_merges_phenomena_caps_and_proyeccion():
    pheno = "PROYECTO SALVACION (Proyección en Dolby Atmos y VOSE)"
    other = "Proyecto Salvación"
    assert film_title_dedupe_key(pheno) == film_title_dedupe_key(other)
    pad = "EL PADRINO (Proyección en 4K y VOSE)"
    assert film_title_dedupe_key(pad) == film_title_dedupe_key("El Padrino")


def test_global_top_display_title_strips_proyeccion():
    from utils import global_top_display_title

    t = global_top_display_title("EL PADRINO (Proyección en 4K y VOSE)")
    assert "Proyección" not in t and "proyección" not in t.lower()
    assert "PADRINO" in t or "Padrino" in t
