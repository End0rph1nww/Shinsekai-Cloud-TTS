from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from sdk.register import PluginCapabilityRegistry
from plugins.cloud_tts import state, ui_service
from plugins.cloud_tts.plugin import CloudTtsPlugin


def _constraint_store(name: str) -> dict[str, Any]:
    versions = {}
    for language, version_id in state.DEFAULT_PROMPT_VERSION_IDS.items():
        versions[version_id] = {
            "name": f"{language} template",
            "constraint_text": f"text:{language}",
            "language": language,
            "source": "default",
            "sort_order": 10,
        }
    return {
        "character_name": name,
        "selected_version": state.DEFAULT_PROMPT_VERSION_IDS["zh"],
        "versions": versions,
    }


@pytest.fixture
def service_env(monkeypatch, tmp_path):
    configs: dict[str, dict[str, Any]] = {
        state.PROVIDER_SLUG: {},
        state.QWEN_PROVIDER_SLUG: {},
        state.GPT_SOVITS_PROVIDER_SLUG: {},
    }
    saved: list[tuple[str, dict[str, Any]]] = []
    extras: dict[str, dict[str, Any]] = {
        state.PROVIDER_SLUG: {"model": "speech-2.8-hd"},
        state.QWEN_PROVIDER_SLUG: {"model": state.QWEN_DEFAULT_MODEL},
        state.GPT_SOVITS_PROVIDER_SLUG: {"model": state.GPT_SOVITS_DEFAULT_MODEL},
    }
    stores: dict[str, dict[str, Any]] = {}
    propagated: list[tuple[str, str]] = []
    characters = [
        {"name": "Hanadan", "prompt_text": "角色卡参考文本"},
        {"name": "Mika"},
    ]

    monkeypatch.setattr(state, "project_root", lambda: tmp_path)
    monkeypatch.setattr(state, "migrate_package_config_to_data_root", lambda *a, **k: None)
    monkeypatch.setattr(state, "migrate_api_extra_to_plugin_state", lambda *a, **k: None)
    monkeypatch.setattr(state, "current_tts_provider", lambda: state.PROVIDER_SLUG)
    monkeypatch.setattr(state, "current_system_voice_language", lambda: "zh")
    monkeypatch.setattr(state, "get_cloud_extra", lambda: dict(extras[state.PROVIDER_SLUG]))
    monkeypatch.setattr(state, "get_qwen_extra", lambda: dict(extras[state.QWEN_PROVIDER_SLUG]))
    monkeypatch.setattr(
        state,
        "get_gpt_sovits_extra",
        lambda: dict(extras[state.GPT_SOVITS_PROVIDER_SLUG]),
    )
    monkeypatch.setattr(
        state,
        "set_cloud_extra",
        lambda values: extras[state.PROVIDER_SLUG].update(dict(values)),
    )
    monkeypatch.setattr(
        state,
        "set_qwen_extra",
        lambda values: extras[state.QWEN_PROVIDER_SLUG].update(dict(values)),
    )
    monkeypatch.setattr(
        state,
        "set_gpt_sovits_extra",
        lambda values: extras[state.GPT_SOVITS_PROVIDER_SLUG].update(dict(values)),
    )
    monkeypatch.setattr(
        state,
        "load_plugin_config",
        lambda _root, provider_slug=state.PROVIDER_SLUG: dict(configs[provider_slug]),
    )

    def save_plugin_config(_root, data, provider_slug=state.PROVIDER_SLUG):
        configs[provider_slug] = dict(data)
        saved.append((provider_slug, dict(data)))

    monkeypatch.setattr(state, "save_plugin_config", save_plugin_config)
    monkeypatch.setattr(state, "load_characters", lambda: list(characters))
    monkeypatch.setattr(
        state,
        "find_character",
        lambda name: next(
            (item for item in characters if item["name"].lower() == str(name).lower()),
            None,
        ),
    )
    monkeypatch.setattr(state, "resolve_reference_audio", lambda _char: None)
    monkeypatch.setattr(state, "suppress_prompt_constraint", lambda *a, **k: None)

    def load_character_constraints(name):
        stores.setdefault(name, _constraint_store(name))
        return stores[name]

    def list_constraint_versions(name):
        store = load_character_constraints(name)
        return [(key, dict(value)) for key, value in store["versions"].items()]

    def select_constraint_version(name, version_id):
        store = load_character_constraints(name)
        if version_id not in store["versions"]:
            return False
        store["selected_version"] = version_id
        return True

    def upsert_constraint_version(character_name, version_id, text, **kwargs):
        store = load_character_constraints(character_name)
        version_id = version_id or "v_custom"
        store["versions"][version_id] = {
            "name": kwargs.get("name", ""),
            "constraint_text": text,
            "source": kwargs.get("source", "manual"),
            "language": kwargs.get("language", "zh"),
        }
        store["selected_version"] = version_id
        return store, version_id

    def remove_constraint_version(name, version_id):
        store = load_character_constraints(name)
        if version_id not in store["versions"] or len(store["versions"]) <= 1:
            return False
        del store["versions"][version_id]
        store["selected_version"] = next(iter(store["versions"]))
        return True

    def propagate_default_template(text, language=None):
        propagated.append((text, language or ""))
        return 2

    monkeypatch.setattr(state, "load_character_constraints", load_character_constraints)
    monkeypatch.setattr(state, "list_constraint_versions", list_constraint_versions)
    monkeypatch.setattr(state, "select_constraint_version", select_constraint_version)
    monkeypatch.setattr(state, "upsert_constraint_version", upsert_constraint_version)
    monkeypatch.setattr(state, "remove_constraint_version", remove_constraint_version)
    monkeypatch.setattr(state, "propagate_default_template", propagate_default_template)
    monkeypatch.setattr(
        state,
        "build_default_constraint_text",
        lambda language="auto": f"default:{language}",
    )
    monkeypatch.setattr(
        state,
        "get_default_template_text",
        lambda language="zh": f"default-template:{language}",
    )

    return {
        "root": tmp_path / "plugin-root",
        "configs": configs,
        "saved": saved,
        "extras": extras,
        "stores": stores,
        "propagated": propagated,
    }


def test_frontend_page_registration(service_env):
    registry = PluginCapabilityRegistry()

    CloudTtsPlugin().initialize(registry, service_env["root"], host=None)

    pages = registry.frontend_page_contributions
    configs = registry.frontend_config_contributions
    assert [page.page_id for page in pages] == ["cloud_tts"]
    assert pages[0].entry.replace("\\", "/").endswith("frontend/index.html")
    assert configs[0].page_id == "cloud_tts"
    assert {action.id for action in configs[0].actions} >= {
        "list_characters",
        "bind_voice",
        "upload_reference",
        "clone_voice",
        "export_voice",
        "import_voice",
    }


def test_switch_provider_saves_old_draft_and_loads_new_snapshot(service_env):
    env = service_env
    env["configs"][state.QWEN_PROVIDER_SLUG] = {"voice_id_map": {"Hanadan": "qwen-old"}}
    payload = {
        "provider": state.PROVIDER_SLUG,
        "toProvider": state.QWEN_PROVIDER_SLUG,
        "currentCharacter": "Hanadan",
        "draft": {
            "model": "speech-2.8-hd",
            "default_voice_id": "mini-default",
            "voice_id_map": {"Hanadan": "mini-1"},
            "voice_id_versions": {},
        },
    }

    result = ui_service.run_action(env["root"], "switch_provider", payload)

    assert env["saved"][-1][0] == state.PROVIDER_SLUG
    assert env["saved"][-1][1]["voice_id_map"] == {"Hanadan": "mini-1"}
    assert result["values"]["provider"] == state.QWEN_PROVIDER_SLUG
    assert result["values"]["draft"]["voice_id_map"] == {"Hanadan": "qwen-old"}


def test_save_values_persists_qwen_language_extra(service_env):
    env = service_env

    ui_service.save_values(
        env["root"],
        {
            "provider": state.QWEN_PROVIDER_SLUG,
            "draft": {
                "model": state.QWEN_DEFAULT_MODEL,
                "qwen_language_type": "Japanese",
                "voice_id_map": {"Hanadan": "qwen-1"},
                "voice_id_versions": {},
            },
        },
    )

    assert env["saved"][-1][0] == state.QWEN_PROVIDER_SLUG
    assert env["extras"][state.QWEN_PROVIDER_SLUG]["language_type"] == "Japanese"


def test_qwen_snapshot_filters_minimax_voice_records(service_env):
    env = service_env
    env["configs"][state.QWEN_PROVIDER_SLUG] = {
        "default_voice_id": "mini-voice",
        "voice_id_map": {"Hanadan": "mini-voice"},
        "voice_id_versions": {
            "Hanadan": [
                {
                    "voice_id": "mini-voice",
                    "provider": state.PROVIDER_SLUG,
                    "source": "import",
                }
            ]
        },
    }

    snapshot = ui_service.load_snapshot(
        env["root"],
        provider=state.QWEN_PROVIDER_SLUG,
        current_character="Hanadan",
    )

    assert snapshot["draft"]["default_voice_id"] == ""
    assert snapshot["draft"]["voice_id_map"] == {}
    assert snapshot["draft"]["voice_id_versions"] == {}
    assert snapshot["selectedCharacter"]["voiceId"] == ""


def test_import_voice_json_skips_mismatched_provider(service_env, tmp_path):
    env = service_env
    source = tmp_path / "minimax-voice.json"
    source.write_text(
        json.dumps(
            {
                "type": "cloud_tts.voice_id",
                "provider": state.PROVIDER_SLUG,
                "character_name": "Hanadan",
                "voice_id": "mini-voice",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = ui_service.run_action(
        env["root"],
        "import_voice_ids",
        {
            "provider": state.QWEN_PROVIDER_SLUG,
            "currentCharacter": "Hanadan",
            "paths": [str(source)],
            "draft": {"voice_id_map": {}, "voice_id_versions": {}},
        },
    )

    assert result["imported"] == 0
    assert env["saved"][-1][0] == state.QWEN_PROVIDER_SLUG
    assert env["saved"][-1][1]["voice_id_map"] == {}
    assert env["saved"][-1][1]["voice_id_versions"] == {}


def test_import_voice_json_matches_current_character(service_env, tmp_path):
    env = service_env
    source = tmp_path / "voice.json"
    source.write_text(
        json.dumps(
            {
                "type": "cloud_tts.voice_id",
                "character_name": "Other",
                "voice_id": "voice-imported",
                "model": "speech-2.8-hd",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = ui_service.run_action(
        env["root"],
        "import_voice_ids",
        {
            "provider": state.PROVIDER_SLUG,
            "currentCharacter": "Hanadan",
            "paths": [str(source)],
            "draft": {"voice_id_map": {}, "voice_id_versions": {}},
        },
    )

    assert result["imported"] == 1
    saved = env["saved"][-1][1]
    assert saved["voice_id_map"]["Hanadan"] == "voice-imported"
    assert saved["voice_id_versions"]["Hanadan"][0]["imported_character_name"] == "Other"


def test_export_voice_json_writes_payload(service_env):
    env = service_env

    result = ui_service.run_action(
        env["root"],
        "export_voice_id",
        {
            "provider": state.PROVIDER_SLUG,
            "currentCharacter": "Hanadan",
            "draft": {
                "model": "speech-2.8-hd",
                "voice_id_map": {"Hanadan": "voice-1"},
                "voice_id_versions": {
                    "Hanadan": [{"voice_id": "voice-1", "source": "local_upload"}]
                },
            },
        },
    )

    path = Path(result["path"])
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["type"] == "cloud_tts.voice_id"
    assert payload["provider"] == state.PROVIDER_SLUG
    assert payload["character_name"] == "Hanadan"
    assert payload["voice_id"] == "voice-1"
    assert result["downloadUrl"].startswith("/api/download?path=")


def test_template_save_and_reset(service_env):
    env = service_env

    saved = ui_service.run_action(
        env["root"],
        "save_template",
        {
            "provider": state.PROVIDER_SLUG,
            "template": {
                "characterName": "默认模板",
                "versionId": state.DEFAULT_PROMPT_VERSION_IDS["zh"],
                "versionName": "中文模板",
                "constraintText": "new-template",
            },
        },
    )
    reset = ui_service.run_action(
        env["root"],
        "reset_template",
        {
            "provider": state.PROVIDER_SLUG,
            "template": {
                "characterName": "默认模板",
                "versionId": state.DEFAULT_PROMPT_VERSION_IDS["zh"],
                "versionName": "中文模板",
            },
        },
    )

    assert "已保存默认模板" in saved["status"]
    assert env["propagated"][0] == ("new-template", "zh")
    assert "已重置默认模板" in reset["status"]
    assert env["propagated"][-1] == ("default:zh", "zh")


def test_gpt_sovits_server_paths_are_saved_without_local_validation(service_env):
    env = service_env

    ui_service.save_values(
        env["root"],
        {
            "provider": state.GPT_SOVITS_PROVIDER_SLUG,
            "currentCharacter": "Hanadan",
            "draft": {
                "model": state.GPT_SOVITS_DEFAULT_MODEL,
                "gpt_sovits_character_profiles": {
                    "Hanadan": {
                        "ref_audio_path": "/server/missing.wav",
                        "gpt_weights_path": "/server/missing.ckpt",
                        "sovits_weights_path": "/server/missing.pth",
                        "prompt_text": "参考文本",
                        "prompt_lang": "ja",
                        "text_lang": "ja",
                    }
                },
            },
        },
    )

    profile = env["saved"][-1][1]["gpt_sovits_character_profiles"]["Hanadan"]
    assert profile["ref_audio_path"] == "/server/missing.wav"
    assert env["extras"][state.GPT_SOVITS_PROVIDER_SLUG]["model"] == state.GPT_SOVITS_DEFAULT_MODEL
