"""Тесты конфига и пресетов городов."""
import json
import logging
import logging.handlers

from sunthemes import config, i18n


def test_every_city_has_i18n_key():
    for city_id in config.CITIES:
        assert f"city.{city_id}" in i18n.STRINGS, city_id
    assert "city.custom" in i18n.STRINGS


def test_legacy_names_map_to_known_cities():
    for legacy, city_id in config.LEGACY_CITY_NAMES.items():
        assert city_id in config.CITIES, f"{legacy} -> {city_id}"


def test_resolve_city_id_modern_and_legacy_and_unknown():
    assert config.resolve_city_id({"city": "moscow"}) == "moscow"
    assert config.resolve_city_id({"city": "Москва"}) == "moscow"
    # неизвестный город (например, «Истра» из старого конфига) → свои координаты
    assert config.resolve_city_id({"city": "Истра"}) == "custom"
    assert config.resolve_city_id({}) == "custom"


def test_load_config_merges_defaults(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"mode": "time"}), encoding="utf-8")
    monkeypatch.setattr(config, "CONFIG_PATH", cfg_file)
    cfg = config.load_config()
    assert cfg["mode"] == "time"                       # из файла
    assert cfg["city"] == config.DEFAULT_CONFIG["city"]  # из дефолта


def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.json"
    monkeypatch.setattr(config, "CONFIG_PATH", cfg_file)
    cfg = dict(config.DEFAULT_CONFIG, lat=51.5)
    config.save_config(cfg)
    assert config.load_config()["lat"] == 51.5


def test_setup_logging_rotates(tmp_path, monkeypatch):
    """Лог должен ротироваться по размеру, а не расти бесконечно."""
    log_file = tmp_path / "t.log"
    monkeypatch.setattr(config, "APP_DIR", tmp_path)
    monkeypatch.setattr(config, "LOG_PATH", log_file)
    monkeypatch.setattr(config, "LOG_MAX_BYTES", 200)
    handler = config.setup_logging()
    try:
        assert isinstance(handler, logging.handlers.RotatingFileHandler)
        assert handler.maxBytes == 200
        assert handler.backupCount == config.LOG_BACKUPS
        logger = logging.getLogger("sunthemes")
        for _ in range(30):
            logger.info("x" * 40)
        assert log_file.exists()
        # при 30 записях по ~40 байт и лимите 200 байт бэкап обязан появиться
        assert (tmp_path / "t.log.1").exists()
    finally:
        logging.getLogger().removeHandler(handler)
        handler.close()
