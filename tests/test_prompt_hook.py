from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from frontend_bridge_core import handler, templates
from plugins.cloud_tts import prompt_hook, state


def _generated_system() -> str:
    return 'Rules for Hanadan\n{"character_name": "Hanadan", "speech": "hello"}'


def _enable_constraint(monkeypatch) -> None:
    monkeypatch.setattr(state, "current_tts_provider", lambda: state.PROVIDER_SLUG)
    monkeypatch.setattr(state, "plugin_manifest_enabled", lambda: True)
    monkeypatch.setattr(state, "prompt_constraint_enabled", lambda: True)
    monkeypatch.setattr(state, "current_system_voice_language", lambda: "zh")
    monkeypatch.setattr(
        state,
        "get_character_constraint_text",
        lambda character_name, voice_language: f"tone guard for {character_name} in {voice_language}",
    )


def test_frontend_generate_hook_injects_prompt_constraint(monkeypatch):
    _enable_constraint(monkeypatch)

    def original_generate(_bridge_state, payload):
        scenario = str(payload.get("scenario") or "")
        system = _generated_system()
        return {
            "content": f"{scenario}\n\n{system}",
            "id": "",
            "name": "generated",
            "path": "",
            "scenario": scenario,
            "system": system,
            "updatedAt": "",
        }

    prompt_hook.uninstall()
    monkeypatch.setattr(templates, "_generate_template_summary", original_generate)
    monkeypatch.setattr(handler, "_generate_template_summary", original_generate)
    try:
        prompt_hook._patch_frontend_bridge_templates()

        row = handler._generate_template_summary(
            object(),
            {"characters": ["Hanadan"], "scenario": "Scene"},
        )
    finally:
        prompt_hook.uninstall()

    assert state.CONSTRAINT_START in row["system"]
    assert "tone guard for Hanadan in zh" in row["system"]
    assert row["content"].startswith(f"Scene\n\n{state.CONSTRAINT_START}")


def test_frontend_generate_hook_uses_payload_voice_language(monkeypatch):
    _enable_constraint(monkeypatch)

    def original_generate(_bridge_state, payload):
        scenario = str(payload.get("scenario") or "")
        system = _generated_system()
        return {
            "content": f"{scenario}\n\n{system}",
            "id": "",
            "name": "generated",
            "path": "",
            "scenario": scenario,
            "system": system,
            "updatedAt": "",
        }

    prompt_hook.uninstall()
    monkeypatch.setattr(templates, "_generate_template_summary", original_generate)
    monkeypatch.setattr(handler, "_generate_template_summary", original_generate)
    try:
        prompt_hook._patch_frontend_bridge_templates()

        row = handler._generate_template_summary(
            object(),
            {"characters": ["Hanadan"], "scenario": "Scene", "voiceLanguage": "en"},
        )
    finally:
        prompt_hook.uninstall()

    assert "tone guard for Hanadan in en" in row["system"]


def test_frontend_load_session_hook_returns_synced_system(monkeypatch):
    _enable_constraint(monkeypatch)

    def original_load(_bridge_state):
        return {
            "scenario": "Scene",
            "selectedCharacters": ["Hanadan"],
            "system": _generated_system(),
            "voiceLanguage": "en",
        }

    prompt_hook.uninstall()
    monkeypatch.setattr(templates, "_load_template_session_payload", original_load)
    monkeypatch.setattr(handler, "_load_template_session_payload", original_load)
    try:
        prompt_hook._patch_frontend_bridge_templates()

        row = handler._load_template_session_payload(object())
    finally:
        prompt_hook.uninstall()

    assert state.CONSTRAINT_START in row["system"]
    assert "tone guard for Hanadan in en" in row["system"]


def test_frontend_save_session_hook_persists_synced_system(monkeypatch):
    _enable_constraint(monkeypatch)
    captured = {}

    def original_save(_bridge_state, payload):
        captured.update(payload)
        return dict(payload)

    prompt_hook.uninstall()
    monkeypatch.setattr(templates, "_save_template_session_payload", original_save)
    monkeypatch.setattr(handler, "_save_template_session_payload", original_save)
    try:
        prompt_hook._patch_frontend_bridge_templates()

        handler._save_template_session_payload(
            object(),
            {
                "scenario": "Scene",
                "selectedCharacters": ["Hanadan"],
                "system": _generated_system(),
                "voiceLanguage": "en",
            },
        )
    finally:
        prompt_hook.uninstall()

    assert state.CONSTRAINT_START in captured["system"]
    assert "tone guard for Hanadan in en" in captured["system"]
