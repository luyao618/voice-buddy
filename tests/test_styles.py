from voice_buddy.styles import load_style, list_styles, STYLES_DIR


def test_styles_dir_exists():
    assert STYLES_DIR.is_dir()


def test_list_styles_returns_seven():
    styles = list_styles()
    assert len(styles) == 7
    ids = {s["id"] for s in styles}
    assert ids == {"cute-girl", "elegant-lady", "warm-boy", "secretary", "steward", "cyber-girl", "kawaii"}


def test_load_style_cute_girl():
    style = load_style("cute-girl")
    assert style["id"] == "cute-girl"
    assert style["name"] == "CC"
    assert style["language"] == "zh-CN"
    assert style["tts"]["voice"] == "zh-CN-XiaoyiNeural"
    assert style["tts"]["rate"] == "+10%"
    assert style["tts"]["pitch"] == "+5Hz"
    assert style["default_nickname"] == "Master"
    assert style["agent"] == "voice-buddy-cute-girl"


def test_load_style_elegant_lady():
    style = load_style("elegant-lady")
    assert style["id"] == "elegant-lady"
    assert style["language"] == "zh-CN"
    assert style["tts"]["voice"] == "zh-CN-XiaoxiaoNeural"


def test_load_style_warm_boy():
    style = load_style("warm-boy")
    assert style["id"] == "warm-boy"
    assert style["tts"]["voice"] == "zh-CN-YunxiNeural"
    assert style["tts"]["pitch"] == "-2Hz"


def test_load_style_secretary():
    style = load_style("secretary")
    assert style["id"] == "secretary"
    assert style["language"] == "en-US"
    assert style["tts"]["voice"] == "en-US-JennyNeural"
    assert style["default_nickname"] == "Boss"


def test_load_style_kawaii():
    style = load_style("kawaii")
    assert style["id"] == "kawaii"
    assert style["language"] == "ja-JP"
    assert style["tts"]["voice"] == "ja-JP-NanamiNeural"
    assert style["default_nickname"] == "Senpai"


def test_load_style_unknown_returns_none():
    style = load_style("nonexistent")
    assert style is None


def test_load_style_steward():
    style = load_style("steward")
    assert style["id"] == "steward"
    assert style["language"] == "en-GB"
    assert style["tts"]["voice"] == "en-GB-RyanNeural"
    assert style["default_nickname"] == "Sir"
    assert style["agent"] == "voice-buddy-steward"


def test_load_style_cyber_girl():
    style = load_style("cyber-girl")
    assert style["id"] == "cyber-girl"
    assert style["language"] == "en-GB"
    assert style["tts"]["voice"] == "en-GB-SoniaNeural"
    assert style["tts"]["rate"] == "-5%"
    assert style["tts"]["pitch"] == "-3Hz"
    assert style["default_nickname"] == "Commander"
    assert style["agent"] == "voice-buddy-cyber-girl"
