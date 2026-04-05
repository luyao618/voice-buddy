from voice_buddy.config import load_config, load_templates


def test_load_config_returns_dict():
    config = load_config()
    assert isinstance(config, dict)
    assert config["character_name"] == "小星"
    assert config["tts"]["voice"] == "zh-CN-XiaoyiNeural"


def test_load_config_has_tts_settings():
    config = load_config()
    tts = config["tts"]
    assert tts["provider"] == "edge-tts"
    assert tts["rate"] == "+10%"
    assert tts["pitch"] == "+5Hz"


def test_load_templates_returns_dict():
    templates = load_templates()
    assert isinstance(templates, dict)
    assert "pretooluse" in templates
    assert "posttooluse" in templates
    assert "posttoolusefailure" in templates
    assert "sessionstart" in templates
    assert "sessionend" in templates


def test_load_templates_has_entries():
    templates = load_templates()
    assert len(templates["pretooluse"]["git_commit"]) >= 1
    assert len(templates["sessionstart"]["default"]) >= 1
