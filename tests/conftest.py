"""Keep test configuration and hook subprocesses away from user state."""

import pytest


@pytest.fixture(autouse=True)
def isolated_user_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("APPDATA", str(home / "AppData" / "Roaming"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.delenv("CLAUDE_PLUGIN_OPTION_STYLE", raising=False)
    monkeypatch.delenv("CLAUDE_PLUGIN_OPTION_NICKNAME", raising=False)
