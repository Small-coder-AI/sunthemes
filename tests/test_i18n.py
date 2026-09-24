"""Тесты словаря локализации."""
import re
import string
from pathlib import Path

from sunthemes import i18n

SRC = Path(i18n.__file__).parent


def test_all_keys_have_both_languages_nonempty():
    for key, variants in i18n.STRINGS.items():
        assert set(variants) == {"ru", "en"}, f"key {key}"
        assert variants["ru"].strip(), f"empty ru for {key}"
        assert variants["en"].strip(), f"empty en for {key}"


def test_tr_switches_language():
    i18n.set_language("ru")
    assert i18n.tr("theme.light") == "Светлая"
    i18n.set_language("en")
    assert i18n.tr("theme.light") == "Light"


def test_tr_formats_placeholders():
    i18n.set_language("en")
    assert "boom" in i18n.tr("sun.calc_error", error="boom")


def test_unknown_language_falls_back_to_en():
    i18n.set_language("de")
    assert i18n.get_language() == "en"


def test_every_key_used_in_code_exists():
    """tr("ключ") с несуществующим ключом падает только в рантайме — ловим здесь."""
    used = set()
    for path in SRC.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        used |= set(re.findall(r"""\btr\(\s*["']([\w.]+)["']""", text))
        # ключи, переданные хелперам построения UI: action("tray.open", …) и т. п.
        used |= set(re.findall(
            r"""\b(?:action|row|_theme_button)\([^)]*?["']((?:tray|sun|btn)\.[\w.]+)["']""",
            text))
    missing = sorted(k for k in used if k not in i18n.STRINGS)
    assert not missing, missing
    assert len(used) > 40        # регулярка действительно что-то нашла


def test_placeholders_match_between_languages():
    def fields(s):
        return {f for _, f, _, _ in string.Formatter().parse(s) if f}

    for key, variants in i18n.STRINGS.items():
        assert fields(variants["ru"]) == fields(variants["en"]), key
