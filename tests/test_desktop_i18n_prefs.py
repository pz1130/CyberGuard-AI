"""language 作为 UI 偏好持久化——与 theme / font_size 同性质，sidecar 只存不用。"""
import importlib


def test_language_defaults_to_system(tmp_path, monkeypatch):
    monkeypatch.setenv("CYBERGUARD_DATA_DIR", str(tmp_path))
    from apps.desktop.sidecar import ui_prefs

    importlib.reload(ui_prefs)
    assert ui_prefs.get_prefs()["language"] == "system"


def test_language_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("CYBERGUARD_DATA_DIR", str(tmp_path))
    from apps.desktop.sidecar import ui_prefs

    importlib.reload(ui_prefs)
    ui_prefs.set_prefs({"language": "en"})
    assert ui_prefs.get_prefs()["language"] == "en"


def test_language_rejects_unknown_value(tmp_path, monkeypatch):
    monkeypatch.setenv("CYBERGUARD_DATA_DIR", str(tmp_path))
    from apps.desktop.sidecar import ui_prefs

    importlib.reload(ui_prefs)
    ui_prefs.set_prefs({"language": "en"})
    ui_prefs.set_prefs({"language": "klingon"})
    # 白名单外的值必须被忽略，不能写坏已有偏好
    assert ui_prefs.get_prefs()["language"] == "en"
