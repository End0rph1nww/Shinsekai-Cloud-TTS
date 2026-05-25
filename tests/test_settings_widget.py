import os
from pathlib import Path
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

qtwidgets = pytest.importorskip("PySide6.QtWidgets")
QApplication = qtwidgets.QApplication

from plugins.cloud_tts import state
from plugins.cloud_tts.settings import CloudTtsSettingsWidget


def _app():
    return QApplication.instance() or QApplication([])


def test_settings_widget_uses_per_character_reference_text(monkeypatch, tmp_path):
    monkeypatch.setattr(state, "migrate_package_config_to_data_root", lambda *args, **kwargs: None)
    monkeypatch.setattr(state, "migrate_api_extra_to_plugin_state", lambda *args, **kwargs: None)
    monkeypatch.setattr(state, "current_tts_provider", lambda: state.PROVIDER_SLUG)
    monkeypatch.setattr(state, "get_cloud_extra", lambda: {})
    monkeypatch.setattr(state, "get_qwen_extra", lambda: {})
    monkeypatch.setattr(state, "get_gpt_sovits_extra", lambda: {})
    monkeypatch.setattr(
        state,
        "load_plugin_config",
        lambda *args, **kwargs: {
            "reference_text_map": {"Hanadan": "自定义试听文本"},
        },
    )
    monkeypatch.setattr(
        state,
        "load_characters",
        lambda: [{"name": "Hanadan", "prompt_text": "角色卡参考文本"}],
    )
    monkeypatch.setattr(
        state,
        "find_character",
        lambda name: {"name": "Hanadan", "prompt_text": "角色卡参考文本"}
        if name == "Hanadan"
        else None,
    )
    monkeypatch.setattr(
        CloudTtsSettingsWidget,
        "_refresh_template_characters",
        lambda self: None,
    )

    _app()
    widget = CloudTtsSettingsWidget(tmp_path)

    assert widget.reference_text.text() == "自定义试听文本"
    assert widget._reference_text_for_character(
        {"name": "Hanadan", "prompt_text": "角色卡参考文本"}
    ) == "自定义试听文本"

    widget.reference_text.clear()
    widget._store_current_reference_text()

    assert widget._reference_text_for_character(
        {"name": "Hanadan", "prompt_text": "角色卡参考文本"}
    ) == "角色卡参考文本"


def test_settings_widget_shows_local_clone_demo_button(monkeypatch, tmp_path):
    monkeypatch.setattr(state, "migrate_package_config_to_data_root", lambda *args, **kwargs: None)
    monkeypatch.setattr(state, "migrate_api_extra_to_plugin_state", lambda *args, **kwargs: None)
    monkeypatch.setattr(state, "current_tts_provider", lambda: state.PROVIDER_SLUG)
    monkeypatch.setattr(state, "get_cloud_extra", lambda: {})
    monkeypatch.setattr(state, "get_qwen_extra", lambda: {})
    monkeypatch.setattr(state, "get_gpt_sovits_extra", lambda: {})
    monkeypatch.setattr(state, "load_plugin_config", lambda *args, **kwargs: {})
    monkeypatch.setattr(state, "load_characters", lambda: [])
    monkeypatch.setattr(state, "find_character", lambda name: None)
    monkeypatch.setattr(
        CloudTtsSettingsWidget,
        "_refresh_template_characters",
        lambda self: None,
    )

    _app()
    widget = CloudTtsSettingsWidget(tmp_path)

    widget._set_clone_demo_audio_path(str(tmp_path / "demo.mp3"))

    assert not widget.play_clone_demo_btn.isHidden()
