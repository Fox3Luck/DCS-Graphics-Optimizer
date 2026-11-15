"""Languages: English is the source, other languages are tables (dcstune/lang_*.py)."""
import json
import re
from pathlib import Path

import pytest

from dcstune import i18n, rate, report as R
from dcstune.lang_tr import TR
from dcstune.optionslua import Options
from test_core import FIX, INFO
from test_ui import served  # noqa: F401  (fixture)

PAGE = (Path(i18n.__file__).parent / "ui.html").read_text(encoding="utf-8")
HOLES = re.compile(r"\{n?\d\}")


@pytest.fixture
def turkish(monkeypatch):
    monkeypatch.setenv("DCSTUNE_LANG", "tr")


def test_every_translation_keeps_the_parts_that_vary():
    for key, value in TR.items():
        assert value.strip(), key
        if not key.startswith("ui."):
            assert set(HOLES.findall(key)) == set(HOLES.findall(value)), key


def test_page_texts_and_table_agree():
    marked = set(re.findall(r'data-t(?:-title|-placeholder)?="([^"]+)"', PAGE))
    assert marked == {k[3:] for k in TR if k.startswith("ui.")}
    # every sentence the page's script builds has a translation
    for literal in re.findall(r'\bT\((?:[\w.]+ \? )?("(?:[^"\\]|\\.)*")', PAGE):
        assert json.loads(literal) in TR, literal
    for a, b in re.findall(r'\bT\([\w.]+ \? ("(?:[^"\\]|\\.)*") : ("(?:[^"\\]|\\.)*")', PAGE):
        assert json.loads(a) in TR and json.loads(b) in TR, (a, b)


def test_english_is_left_exactly_as_written():
    text = "Holds about 123 FPS in the worst moments (measured) against a 120 FPS goal."
    assert i18n.tr(text) == text and i18n.tr_deep({"a": [text]}) == {"a": [text]}
    assert i18n.page_strings() == "{}"


def test_sentences_with_numbers_and_names(turkish):
    assert i18n.tr("Holds about 123 FPS in the worst moments (measured) against a 120 FPS goal.") == \
        "En kötü anlarda yaklaşık 123 FPS'i koruyor (ölçüldü); hedef 120 FPS."
    assert i18n.tr("  Measuring Shadows = High...") == "  Ölçülüyor: Gölgeler (Shadows) = Yüksek..."     # log lines keep their indent
    assert i18n.tr("Testing candidate 2 (DLAA (native))...") == "2. aday test ediliyor (DLAA (tam çözünürlük))..."
    assert i18n.tr("Applied. Your previous settings are kept as options.lua.dcstune-backup-1.") == \
        "Uygulandı. Önceki ayarlarınız options.lua.dcstune-backup-1 adıyla saklanıyor."
    # no translation yet, a folder, a number: unchanged
    for same in ("A sentence nobody translated.", r"C:\Users\Jose\Saved Games\DCS", "16 GB", ""):
        assert i18n.tr(same) == same


def test_answers_are_translated_but_data_is_not(turkish):
    got = i18n.tr_deep({"state": "running", "profile": "High", "severity": "good", "error": "A test is already running.",
                        "hardware": [{"label": "Graphics card", "value": "unknown"}], "n": 3, "ok": True,
                        "report": {"kind": "Thorough test"}})
    assert got == {"state": "running", "profile": "High", "severity": "good", "error": "Zaten bir test çalışıyor.",
                   "hardware": [{"label": "Ekran kartı", "value": "bilinmiyor"}], "n": 3, "ok": True,
                   "report": {"kind": "Thorough test"}}


def test_scorecard_and_report_have_no_english_left(turkish):
    flat = rate.flat_options(Options.load(FIX / "options.DCS.lua"))
    machine = rate.rate_machine(INFO)
    fit = rate.rate_settings(INFO, flat, machine)
    for text in machine["reasons"] + [f["text"] for f in fit["findings"]] + [fit["basis"]]:
        assert i18n.tr(text) != text, text
    radar = i18n.tr_deep(rate.radar(INFO, machine, fit))
    assert [r["label"] for r in radar] == [
        "Ekran kartı", "İşlemci", "Ekran belleği (VRAM)", "Bellek (RAM)", "Akıcılık", "Görüntü kalitesi"]
    rep = {"before": fit, "kind": "Thorough test", "duration_min": 37, "runs": 10, "target_fps": 120,
           "mode_label": "Balanced", "before_result": {"p1_low_fps": 100.0, "avg_fps": 150.0, "vram_peak_mb": 9000},
           "hardware": rate.hardware_summary(INFO, flat), "machine": machine}
    html = R.page(rep)
    assert '<html lang="tr">' in html and "Kapsamlı test" in html and "37 dakika" in html
    assert "Hedef: en kötü anlarda 120 FPS" in html and "(Dengeli)" in html
    assert "Bu araç bunu değiştirmez" in R.fragment(dict(rep, before=dict(fit, findings=[
        {"severity": "warn", "text": "Anti-aliasing is off; edges and distant aircraft shimmer.", "untouched": True}])))
    for english in ("Your settings", "Worst moments", "Graphics card", "Measured in DCS", "minutes", "Frame rates were"):
        assert english not in html, english


def test_window_switches_language(served, monkeypatch):
    app, call, _ = served
    monkeypatch.delenv("DCSTUNE_LANG")
    page = call("/?t=" + app.token)[1].decode("utf-8")
    assert '<html lang="en">' in page and "STRINGS = {};" in page
    assert call("/api/language", {"lang": "xx"})[0] == 400
    assert json.loads(call("/api/language", {"lang": "tr"})[1])["lang"] == "tr"
    page = call("/?t=" + app.token)[1].decode("utf-8")
    assert '<html lang="tr">' in page and "Bu ayarları uygula" in page
    sc = json.loads(call("/api/scorecard")[1])
    assert sc["hardware"][0]["label"] == "Ekran kartı" and sc["settings"]["basis"] == "tahmini"
    assert json.loads(call("/api/apply", {})[1])["error"] == "Henüz uygulanacak bir öneri yok."
    monkeypatch.setattr(i18n, "_current", None)            # the choice is remembered for the next start
    assert i18n.lang() == "tr"
    call("/api/language", {"lang": "en"})
    assert json.loads(call("/api/scorecard")[1])["hardware"][0]["label"] == "Graphics card"


def test_starts_in_english_until_the_player_picks(monkeypatch):
    monkeypatch.delenv("DCSTUNE_LANG")
    assert i18n.lang() == "en"
    assert i18n.set_lang("tr") == "tr"
    monkeypatch.setattr(i18n, "_current", None)      # a later start reads the saved choice
    assert i18n.lang() == "tr"
