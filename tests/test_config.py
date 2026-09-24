import yaml

from sportsbar import config


def test_first_run_writes_defaults(config_dir):
    cfg = config.load_config()
    assert (config_dir / "config.yaml").exists()
    assert cfg == config.DEFAULT_CONFIG
    assert (config_dir / "cache").is_dir()


def test_returned_config_is_independent_of_defaults(config_dir):
    for _ in range(2):  # first run (no file) and a normal load
        cfg = config.load_config()
        cfg["notifications"]["scoring_plays"] = True
        cfg["quick_links"].append({"name": "x", "url": "y"})
        assert config.DEFAULT_CONFIG["notifications"]["scoring_plays"] is False
        assert len(config.DEFAULT_CONFIG["quick_links"]) == 6


def test_user_values_merge_over_defaults(config_dir):
    (config_dir / "config.yaml").write_text(yaml.safe_dump({
        "odds_api_key": "abc",
        "notifications": {"final_score": False},
        "quick_links": [{"name": "Mine", "url": "https://example.com"}],
    }))
    cfg = config.load_config()
    assert cfg["odds_api_key"] == "abc"
    assert cfg["notifications"] == {"final_score": False}
    assert cfg["show_weather"] is True  # default filled in
    # The User's Guide link is always re-added at the top
    assert cfg["quick_links"][0]["name"] == "User's Guide"
    assert cfg["quick_links"][1]["name"] == "Mine"


def test_malformed_sections_fall_back_to_defaults(config_dir):
    (config_dir / "config.yaml").write_text(yaml.safe_dump({
        "notifications": "yes please", "quick_links": "nope",
    }))
    cfg = config.load_config()
    assert cfg["notifications"] == config.DEFAULT_CONFIG["notifications"]
    assert cfg["quick_links"] == config.DEFAULT_CONFIG["quick_links"]


def test_empty_config_file(config_dir):
    (config_dir / "config.yaml").write_text("")
    assert config.load_config() == config.DEFAULT_CONFIG


def test_cache_round_trip(config_dir):
    assert config.read_cache("missing") == {}
    config.write_cache("schedule", {"games": [1, 2]})
    assert config.read_cache("schedule") == {"games": [1, 2]}


def test_corrupt_cache_reads_empty(config_dir):
    config.ensure_paths()
    (config_dir / "cache" / "bad.json").write_text("{not json")
    assert config.read_cache("bad") == {}
