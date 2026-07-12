"""Тесты словаря локализации."""
from sunthemes import i18n


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
