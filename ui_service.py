from __future__ import annotations

import ast
import json
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import quote

from plugins.cloud_tts import state
from plugins.cloud_tts.adapter import CloudTTSAdapter, VALID_MODELS
from plugins.cloud_tts.gpt_sovits_adapter import GPTSoVITSApiAdapter
from plugins.cloud_tts.qwen_adapter import QwenTTSAdapter


IMPORTED_VOICE_BUCKET = "__imported__"
IMPORTED_VOICE_LABEL = "导入音色"
VOICE_ID_EXPORT_EXCLUDED_KEYS = {
    "voices",
    "voice_id_versions",
    "voice_id_map",
    "character_name",
    "character",
    "name",
    "selected_voice_id",
    "type",
    "imported_from",
    "reference_audio_path",
    "local_reference_audio_path",
    "ref_audio_path",
    "demo_audio_path",
    "last_clone_demo_audio_path",
}

PROVIDER_OPTIONS = (
    {
        "value": state.PROVIDER_SLUG,
        "label": "MiniMax TTS",
        "description": "MiniMax 语音复刻、语气标签保护和提示词模板。",
    },
    {
        "value": state.QWEN_PROVIDER_SLUG,
        "label": "Qwen3 TTS",
        "description": "DashScope / 百炼声音复刻，按合成语言绑定 voice_id。",
    },
    {
        "value": state.GPT_SOVITS_PROVIDER_SLUG,
        "label": "GPT SoVITS Cloud",
        "description": "使用服务器参考音频与 GPT/SoVITS 权重路径。",
    },
)

GSV_PROFILE_KEYS = {
    "ref_audio_path",
    "gpt_weights_path",
    "sovits_weights_path",
    "prompt_text",
    "prompt_lang",
    "text_lang",
}

GSV_STATE_KEYS = {
    "gpt_sovits_character_profiles",
    "gpt_sovits_text_split_method",
    "gpt_sovits_media_type",
    "gpt_sovits_streaming_mode",
    "gpt_sovits_batch_size",
    "gpt_sovits_batch_threshold",
    "gpt_sovits_split_bucket",
    "gpt_sovits_fragment_interval",
    "gpt_sovits_seed",
    "gpt_sovits_parallel_infer",
    "gpt_sovits_repetition_penalty",
    "gpt_sovits_top_k",
    "gpt_sovits_top_p",
    "gpt_sovits_temperature",
    "gpt_sovits_sample_steps",
    "gpt_sovits_super_sampling",
}

PERSISTED_DRAFT_KEYS = {
    "model",
    "default_voice_id",
    "voice_id_map",
    "voice_id_versions",
    "local_reference_audio_map",
    "reference_audio_language_map",
    "reference_text_map",
    "auto_prompt_constraint",
    "protect_translate_tone_tags",
    "qwen_language_type",
    "language_type",
    *GSV_STATE_KEYS,
}


def load_values(plugin_root: Path) -> dict[str, Any]:
    """Return the full JSON-safe state used by the standalone iframe page."""
    return load_snapshot(plugin_root, provider=_current_edit_provider())


def save_values(plugin_root: Path, values: Mapping[str, Any]) -> None:
    """Persist ordinary field edits from the iframe config endpoint."""
    provider = _provider_from_payload(values)
    draft = _draft_from_payload(plugin_root, provider, values)
    _save_draft(plugin_root, provider, draft)


def run_action(plugin_root: Path, action_id: str, values: Mapping[str, Any]) -> dict[str, Any]:
    """Run a plugin UI action and return a refreshed page snapshot when useful."""
    action = str(action_id or "").strip()
    if action == "switch_provider":
        return _action_switch_provider(plugin_root, values)
    if action == "import_voice_ids":
        return _action_import_voice_ids(plugin_root, values)
    if action == "export_voice_id":
        return _action_export_voice_id(plugin_root, values)
    if action == "upload_voice":
        return _action_upload_voice(plugin_root, values)
    if action == "select_template":
        return _action_select_template(plugin_root, values)
    if action == "save_template":
        return _action_save_template(plugin_root, values)
    if action == "reset_template":
        return _action_reset_template(plugin_root, values)
    if action == "create_template":
        return _action_create_template(plugin_root, values)
    if action == "delete_template":
        return _action_delete_template(plugin_root, values)
    raise ValueError(f"unknown Cloud TTS action: {action_id}")


def load_snapshot(
    plugin_root: Path,
    *,
    provider: str | None = None,
    current_character: str | None = None,
    template_character: str | None = None,
    template_version: str | None = None,
    status: str = "",
) -> dict[str, Any]:
    provider_slug = _normalize_provider(provider)
    draft = _load_provider_values(plugin_root, provider_slug)
    characters = _character_options()
    selected_character = _valid_character_name(current_character, characters)
    if not selected_character and characters:
        selected_character = str(characters[0].get("name") or "")
    template = _template_snapshot(
        characters,
        character_name=template_character,
        version_id=template_version,
    )
    snapshot = {
        "pageId": "cloud_tts",
        "pluginId": state.PLUGIN_ID,
        "provider": provider_slug,
        "providerLabel": provider_label(provider_slug),
        "providers": list(PROVIDER_OPTIONS),
        "providerVisibility": {
            "isMiniMax": provider_slug == state.PROVIDER_SLUG,
            "isQwen": provider_slug == state.QWEN_PROVIDER_SLUG,
            "isGptSovits": provider_slug == state.GPT_SOVITS_PROVIDER_SLUG,
        },
        "modelOptions": [{"label": item, "value": item} for item in _provider_model_options(provider_slug)],
        "qwenLanguageOptions": [
            {"label": label, "value": value}
            for value, label in state.QWEN_LANGUAGE_TYPES
        ],
        "gsvMediaTypes": [{"label": item, "value": item} for item in state.GPT_SOVITS_MEDIA_TYPES],
        "gsvLanguageOptions": [
            {"label": label, "value": value}
            for value, label in state.GPT_SOVITS_LANGUAGE_OPTIONS
        ],
        "voiceLanguageOptions": [
            {"label": label, "value": value}
            for value, label in state.VOICE_LANGUAGE_OPTIONS
        ],
        "promptLanguageOptions": [
            {"label": label, "value": value}
            for value, label in state.PROMPT_LANGUAGE_OPTIONS
        ],
        "defaultVoiceOptions": _default_voice_options(provider_slug, draft),
        "characters": characters,
        "currentCharacter": selected_character,
        "selectedCharacter": _selected_character_snapshot(provider_slug, draft, selected_character),
        "cloneDemoHistory": _load_clone_demo_history(plugin_root),
        "draft": draft,
        "template": template,
        "status": status,
        "updatedAt": int(time.time()),
    }
    return _json_safe(snapshot)


def provider_label(provider: str | None) -> str:
    slug = _normalize_provider(provider)
    if slug == state.QWEN_PROVIDER_SLUG:
        return "Qwen3 TTS"
    if slug == state.GPT_SOVITS_PROVIDER_SLUG:
        return "GPT SoVITS Cloud"
    return "MiniMax TTS"


def _clone_demo_history_path(plugin_root: Path) -> Path:
    return Path(plugin_root) / "clone_demos.json"


def _load_clone_demo_history(plugin_root: Path) -> list[dict[str, Any]]:
    path = _clone_demo_history_path(plugin_root)
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        demo_path = str(item.get("demo_audio_path") or item.get("path") or "").strip()
        if not demo_path:
            continue
        character_name = str(item.get("character_name") or "").strip()
        voice_id = str(item.get("voice_id") or "").strip()
        demo_name = str(item.get("demo_name") or item.get("audition_name") or "").strip()
        version_label = str(item.get("version_label") or "").strip()
        label_parts = [part for part in (character_name, version_label, demo_name or Path(demo_path).name) if part]
        record = {
            "id": str(item.get("id") or state.short_hash(f"{demo_path}:{voice_id}", 14)),
            "provider": str(item.get("provider") or state.PROVIDER_SLUG),
            "character_name": character_name,
            "voice_id": voice_id,
            "version": item.get("version") or 0,
            "version_label": version_label,
            "demo_name": demo_name,
            "demo_audio_path": demo_path,
            "model": str(item.get("model") or ""),
            "created_at": int(item.get("created_at") or 0),
            "label": str(item.get("label") or " / ".join(label_parts) or demo_path),
        }
        out.append(record)
    return sorted(out, key=lambda rec: int(rec.get("created_at") or 0), reverse=True)


def _save_clone_demo_history(plugin_root: Path, records: list[dict[str, Any]]) -> None:
    path = _clone_demo_history_path(plugin_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_safe(records[:80]), ensure_ascii=False, indent=2), encoding="utf-8")


def _voice_version_index(
    versions: dict[str, list[dict[str, Any]]],
    character_name: str,
    voice_id: str,
) -> int:
    for index, item in enumerate(versions.get(character_name, []), start=1):
        if str(item.get("voice_id") or "").strip() == str(voice_id or "").strip():
            return index
    return 0


def _append_clone_demo_record(
    plugin_root: Path,
    *,
    provider: str,
    character_name: str,
    voice_id: str,
    demo_audio_path: str,
    versions: dict[str, list[dict[str, Any]]],
    model: str,
) -> dict[str, Any] | None:
    path = str(demo_audio_path or "").strip()
    if not path:
        return None
    version = _voice_version_index(versions, character_name, voice_id)
    version_label = f"版本 {version}" if version else "版本 ?"
    demo_name = f"{character_name} 试听音色" if character_name else Path(path).stem
    label = f"{character_name or '未命名'} / {version_label} / {demo_name}"
    record = {
        "id": state.short_hash(f"{provider}:{character_name}:{voice_id}:{path}", 14),
        "provider": provider,
        "character_name": character_name,
        "voice_id": voice_id,
        "version": version,
        "version_label": version_label,
        "demo_name": demo_name,
        "demo_audio_path": path,
        "model": model,
        "created_at": int(time.time()),
        "label": label,
    }
    existing = _load_clone_demo_history(plugin_root)
    filtered = [
        item
        for item in existing
        if item.get("id") != record["id"]
        and str(item.get("demo_audio_path") or "") != path
    ]
    _save_clone_demo_history(plugin_root, [record, *filtered])
    return record


def _current_edit_provider() -> str:
    current = state.current_tts_provider()
    if state.is_gpt_sovits_provider(current):
        return state.GPT_SOVITS_PROVIDER_SLUG
    if state.is_qwen_tts_provider(current):
        return state.QWEN_PROVIDER_SLUG
    return state.PROVIDER_SLUG


def _normalize_provider(provider: str | None) -> str:
    value = str(provider or "").strip()
    if state.is_qwen_tts_provider(value):
        return state.QWEN_PROVIDER_SLUG
    if state.is_gpt_sovits_provider(value):
        return state.GPT_SOVITS_PROVIDER_SLUG
    return state.PROVIDER_SLUG


def _provider_from_payload(values: Mapping[str, Any]) -> str:
    return _normalize_provider(
        values.get("provider")
        or values.get("toProvider")
        or values.get("fromProvider")
        or _current_edit_provider()
    )


def _provider_model_options(provider: str) -> tuple[str, ...]:
    if provider == state.QWEN_PROVIDER_SLUG:
        return state.QWEN_MODELS
    if provider == state.GPT_SOVITS_PROVIDER_SLUG:
        return state.GPT_SOVITS_MODELS
    return VALID_MODELS


def _provider_default_model(provider: str) -> str:
    if provider == state.QWEN_PROVIDER_SLUG:
        return state.QWEN_DEFAULT_MODEL
    if provider == state.GPT_SOVITS_PROVIDER_SLUG:
        return state.GPT_SOVITS_DEFAULT_MODEL
    return "speech-2.8-hd"


def _provider_extra(provider: str) -> dict[str, Any]:
    if provider == state.QWEN_PROVIDER_SLUG:
        return state.get_qwen_extra()
    if provider == state.GPT_SOVITS_PROVIDER_SLUG:
        return state.get_gpt_sovits_extra()
    return state.get_cloud_extra()


def _save_provider_extra(provider: str, values: dict[str, Any]) -> None:
    if provider == state.QWEN_PROVIDER_SLUG:
        state.set_qwen_extra(values)
    elif provider == state.GPT_SOVITS_PROVIDER_SLUG:
        state.set_gpt_sovits_extra(values)
    else:
        state.set_cloud_extra(values)


def _load_provider_values(plugin_root: Path, provider: str) -> dict[str, Any]:
    state.migrate_package_config_to_data_root()
    state.migrate_api_extra_to_plugin_state(plugin_root)
    cfg = state.load_plugin_config(plugin_root, provider)
    extra = _provider_extra(provider)
    values = {k: v for k, v in cfg.items() if v not in (None, "", {}, [])}
    values.update(extra)
    model = _valid_choice(
        values.get("model"),
        _provider_model_options(provider),
        _provider_default_model(provider),
    )
    voice_id_map = _coerce_voice_id_map(values.get("voice_id_map"))
    voice_id_versions = _coerce_voice_id_versions(values.get("voice_id_versions"))
    qwen_language = str(values.get("qwen_language_type") or values.get("language_type") or "Chinese")
    draft = {
        "model": model,
        "default_voice_id": "" if provider == state.GPT_SOVITS_PROVIDER_SLUG else str(values.get("default_voice_id") or ""),
        "voice_id_map": voice_id_map,
        "voice_id_versions": voice_id_versions,
        "local_reference_audio_map": _coerce_path_map(values.get("local_reference_audio_map")),
        "reference_audio_language_map": state.coerce_voice_language_map(
            values.get("reference_audio_language_map")
        ),
        "reference_text_map": _coerce_text_map(values.get("reference_text_map")),
        "auto_prompt_constraint": _as_bool(values.get("auto_prompt_constraint"), False),
        "protect_translate_tone_tags": _as_bool(values.get("protect_translate_tone_tags"), True),
        "qwen_language_type": qwen_language,
        "language_type": qwen_language,
        "gpt_sovits_character_profiles": _coerce_gpt_sovits_profiles(
            values.get("gpt_sovits_character_profiles")
        ),
        "gpt_sovits_text_split_method": str(values.get("gpt_sovits_text_split_method") or "cut5"),
        "gpt_sovits_media_type": _valid_choice(
            values.get("gpt_sovits_media_type"),
            state.GPT_SOVITS_MEDIA_TYPES,
            "wav",
        ),
        "gpt_sovits_sample_steps": str(values.get("gpt_sovits_sample_steps") or "32"),
        "gpt_sovits_super_sampling": _as_bool(values.get("gpt_sovits_super_sampling"), False),
    }
    for key in GSV_STATE_KEYS:
        if key in draft:
            continue
        if key in values:
            draft[key] = values[key]
    return _normalize_draft_maps(draft, provider)


def _save_draft(plugin_root: Path, provider: str, draft: dict[str, Any]) -> None:
    state.suppress_prompt_constraint()
    normalized = _normalize_draft_maps(dict(draft), provider)
    state.save_plugin_config(plugin_root, normalized, provider)
    provider_extra = {"model": str(normalized.get("model") or _provider_default_model(provider))}
    if provider != state.GPT_SOVITS_PROVIDER_SLUG:
        provider_extra["default_voice_id"] = str(normalized.get("default_voice_id") or "")
    if provider == state.QWEN_PROVIDER_SLUG:
        provider_extra["language_type"] = str(
            normalized.get("qwen_language_type")
            or normalized.get("language_type")
            or "Chinese"
        )
    _save_provider_extra(provider, provider_extra)


def _draft_from_payload(
    plugin_root: Path,
    provider: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    existing = _load_provider_values(plugin_root, provider)
    raw = payload.get("draft")
    if not isinstance(raw, Mapping):
        raw = payload.get("values")
    if not isinstance(raw, Mapping):
        raw = {k: payload[k] for k in PERSISTED_DRAFT_KEYS if k in payload}
    draft = dict(existing)
    for key, value in dict(raw).items():
        if key in PERSISTED_DRAFT_KEYS:
            draft[key] = value
    current_character = _payload_current_character(payload)
    selected = payload.get("selectedCharacter")
    if isinstance(selected, Mapping):
        _apply_selected_character_payload(provider, draft, current_character, selected)
    return _normalize_draft_maps(draft, provider)


def _normalize_draft_maps(draft: dict[str, Any], provider: str | None = None) -> dict[str, Any]:
    draft["voice_id_map"] = _coerce_voice_id_map(draft.get("voice_id_map"))
    draft["voice_id_versions"] = _coerce_voice_id_versions(draft.get("voice_id_versions"))
    if provider:
        _filter_voice_data_for_provider(provider, draft)
    _ensure_versions_from_selected_map(draft["voice_id_map"], draft["voice_id_versions"])
    draft["local_reference_audio_map"] = _coerce_path_map(draft.get("local_reference_audio_map"))
    draft["reference_audio_language_map"] = state.coerce_voice_language_map(
        draft.get("reference_audio_language_map")
    )
    draft["reference_text_map"] = _coerce_text_map(draft.get("reference_text_map"))
    draft["gpt_sovits_character_profiles"] = _coerce_gpt_sovits_profiles(
        draft.get("gpt_sovits_character_profiles")
    )
    draft["auto_prompt_constraint"] = _as_bool(draft.get("auto_prompt_constraint"), False)
    draft["protect_translate_tone_tags"] = _as_bool(
        draft.get("protect_translate_tone_tags"),
        True,
    )
    draft["gpt_sovits_super_sampling"] = _as_bool(draft.get("gpt_sovits_super_sampling"), False)
    draft["model"] = str(draft.get("model") or "")
    draft["default_voice_id"] = str(draft.get("default_voice_id") or "").strip()
    qwen_language = str(draft.get("qwen_language_type") or draft.get("language_type") or "Chinese")
    draft["qwen_language_type"] = qwen_language
    draft["language_type"] = qwen_language
    return draft


def _explicit_provider_slug(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if state.is_qwen_tts_provider(raw):
        return state.QWEN_PROVIDER_SLUG
    if state.is_gpt_sovits_provider(raw):
        return state.GPT_SOVITS_PROVIDER_SLUG
    if state.is_cloud_tts_provider(raw):
        return state.PROVIDER_SLUG
    return ""


def _voice_record_matches_provider(provider: str, record: Mapping[str, Any]) -> bool:
    explicit = _explicit_provider_slug(record.get("provider"))
    return not explicit or explicit == provider


def _voice_payload_matches_provider(provider: str, payload: Mapping[str, Any]) -> bool:
    explicit = _explicit_provider_slug(payload.get("provider"))
    return not explicit or explicit == provider


def _filter_voice_data_for_provider(provider: str, draft: dict[str, Any]) -> None:
    if provider == state.GPT_SOVITS_PROVIDER_SLUG:
        draft["default_voice_id"] = ""
        draft["voice_id_map"] = {}
        draft["voice_id_versions"] = {}
        return

    versions = _coerce_voice_id_versions(draft.get("voice_id_versions"))
    filtered_versions: dict[str, list[dict[str, Any]]] = {}
    matching_ids_by_name: dict[str, set[str]] = {}
    mismatched_ids: set[str] = set()
    for name, records in versions.items():
        kept: list[dict[str, Any]] = []
        matching_ids: set[str] = set()
        for rec in records:
            voice_id = str(rec.get("voice_id") or "").strip()
            if not voice_id:
                continue
            if _voice_record_matches_provider(provider, rec):
                kept.append(dict(rec))
                matching_ids.add(voice_id)
            else:
                mismatched_ids.add(voice_id)
        if kept:
            filtered_versions[name] = kept
            matching_ids_by_name[name] = matching_ids

    voice_map = _coerce_voice_id_map(draft.get("voice_id_map"))
    filtered_map: dict[str, str] = {}
    for name, voice_id in voice_map.items():
        if voice_id in mismatched_ids and voice_id not in matching_ids_by_name.get(name, set()):
            continue
        filtered_map[name] = voice_id

    default_voice_id = str(draft.get("default_voice_id") or "").strip()
    if default_voice_id in mismatched_ids and not any(
        default_voice_id in ids for ids in matching_ids_by_name.values()
    ):
        default_voice_id = ""

    draft["voice_id_versions"] = filtered_versions
    draft["voice_id_map"] = filtered_map
    draft["default_voice_id"] = default_voice_id


def _apply_selected_character_payload(
    provider: str,
    draft: dict[str, Any],
    current_character: str,
    selected: Mapping[str, Any],
) -> None:
    name = str(selected.get("name") or current_character or "").strip()
    if not name:
        return
    if provider == state.GPT_SOVITS_PROVIDER_SLUG:
        profile_raw = selected.get("gptSovitsProfile")
        if isinstance(profile_raw, Mapping):
            profile = _coerce_gpt_sovits_profile(profile_raw)
            profiles = _coerce_gpt_sovits_profiles(draft.get("gpt_sovits_character_profiles"))
            if profile:
                profiles[name] = profile
            else:
                profiles.pop(name, None)
            draft["gpt_sovits_character_profiles"] = profiles
        return

    voice_id = str(selected.get("voiceId") or "").strip()
    voice_map = _coerce_voice_id_map(draft.get("voice_id_map"))
    versions = _coerce_voice_id_versions(draft.get("voice_id_versions"))
    if voice_id:
        voice_map[name] = voice_id
        _ensure_voice_version(versions, name, voice_id, source="manual")
    else:
        voice_map.pop(name, None)
    draft["voice_id_map"] = voice_map
    draft["voice_id_versions"] = versions

    local_audio = str(selected.get("localReferenceAudio") or "").strip()
    local_map = _coerce_path_map(draft.get("local_reference_audio_map"))
    if local_audio:
        local_map[name] = local_audio
    else:
        local_map.pop(name, None)
    draft["local_reference_audio_map"] = local_map

    language = state.normalize_voice_language_code(selected.get("referenceAudioLanguage"))
    language_map = state.coerce_voice_language_map(draft.get("reference_audio_language_map"))
    if language == "auto":
        language_map.pop(name, None)
    else:
        language_map[name] = language
    draft["reference_audio_language_map"] = language_map

    reference_text = str(selected.get("referenceText") or "").strip()
    text_map = _coerce_text_map(draft.get("reference_text_map"))
    if reference_text:
        text_map[name] = reference_text
    else:
        text_map.pop(name, None)
    draft["reference_text_map"] = text_map


def _character_options() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in state.load_characters():
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        ref_audio = state.resolve_reference_audio(item)
        out.append(
            {
                "name": name,
                "label": name,
                "cardReferenceAudioPath": str(ref_audio) if ref_audio else "",
                "hasCardReferenceAudio": bool(ref_audio),
            }
        )
    return out


def _valid_character_name(value: str | None, characters: list[dict[str, Any]]) -> str:
    target = str(value or "").strip()
    if not target:
        return ""
    for item in characters:
        name = str(item.get("name") or "").strip()
        if name == target:
            return name
    return ""


def _payload_current_character(payload: Mapping[str, Any]) -> str:
    selected = payload.get("selectedCharacter")
    if isinstance(selected, Mapping):
        value = str(selected.get("name") or "").strip()
        if value:
            return value
    return str(payload.get("currentCharacter") or "").strip()


def _selected_character_snapshot(provider: str, draft: dict[str, Any], character_name: str) -> dict[str, Any]:
    name = str(character_name or "").strip()
    character = state.find_character(name) if name else None
    ref_audio = state.resolve_reference_audio(character) if character else None
    if provider == state.GPT_SOVITS_PROVIDER_SLUG:
        profile = _coerce_gpt_sovits_profiles(
            draft.get("gpt_sovits_character_profiles")
        ).get(name, {})
        return {
            "name": name,
            "cardReferenceAudioPath": str(ref_audio) if ref_audio else "",
            "gptSovitsProfile": dict(profile),
            "voiceOptions": [],
        }
    voice_id_map = _coerce_voice_id_map(draft.get("voice_id_map"))
    return {
        "name": name,
        "cardReferenceAudioPath": str(ref_audio) if ref_audio else "",
        "voiceId": voice_id_map.get(name, ""),
        "voiceOptions": _character_voice_options(draft, name),
        "localReferenceAudio": _coerce_path_map(draft.get("local_reference_audio_map")).get(name, ""),
        "referenceAudioLanguage": state.normalize_voice_language_code(
            state.coerce_voice_language_map(draft.get("reference_audio_language_map")).get(name, "auto")
        ),
        "referenceText": _coerce_text_map(draft.get("reference_text_map")).get(name, ""),
    }


def _default_voice_options(provider: str, draft: dict[str, Any]) -> list[dict[str, str]]:
    if provider == state.GPT_SOVITS_PROVIDER_SLUG:
        return []
    return [{"label": "不固定", "value": ""}, *_all_voice_options(draft)]


def _all_voice_options(draft: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    versions = _coerce_voice_id_versions(draft.get("voice_id_versions"))
    for name, records in versions.items():
        clean_name = str(name or "").strip()
        bucket_label_name = IMPORTED_VOICE_LABEL if clean_name == IMPORTED_VOICE_BUCKET else clean_name
        for idx, rec in enumerate(records, start=1):
            voice_id = str(rec.get("voice_id") or "").strip()
            if not voice_id or voice_id in seen:
                continue
            display_name = str(rec.get("imported_character_name") or "").strip()
            label_name = display_name or bucket_label_name
            out.append({"label": f"{label_name} / 版本 {idx} / {voice_id}", "value": voice_id})
            seen.add(voice_id)
    for name, voice_id in _coerce_voice_id_map(draft.get("voice_id_map")).items():
        if voice_id and voice_id not in seen:
            label_name = IMPORTED_VOICE_LABEL if name == IMPORTED_VOICE_BUCKET else name
            out.append({"label": f"{label_name} / 当前 / {voice_id}", "value": voice_id})
            seen.add(voice_id)
    return out


def _character_voice_options(draft: dict[str, Any], character_name: str) -> list[dict[str, str]]:
    name = str(character_name or "").strip()
    options = [{"label": "使用默认保底 voice_id", "value": ""}]
    selected = _coerce_voice_id_map(draft.get("voice_id_map")).get(name, "")
    versions = _coerce_voice_id_versions(draft.get("voice_id_versions")).get(name, [])
    seen = {""}
    for idx, rec in enumerate(versions, start=1):
        voice_id = str(rec.get("voice_id") or "").strip()
        if not voice_id:
            continue
        display_name = str(rec.get("imported_character_name") or "").strip()
        label_name = display_name or name
        label = (
            f"{label_name} / 版本 {idx} / {voice_id}"
        )
        options.append({"label": label, "value": voice_id})
        seen.add(voice_id)
    if selected and selected not in seen:
        options.append({"label": f"手动 / {selected}", "value": selected})
    return options


def _template_snapshot(
    characters: list[dict[str, Any]],
    *,
    character_name: str | None,
    version_id: str | None,
) -> dict[str, Any]:
    character_names = ["默认模板"]
    character_names.extend(
        str(item.get("name") or "").strip()
        for item in characters
        if str(item.get("name") or "").strip() and str(item.get("name") or "").strip() != "默认模板"
    )
    name = str(character_name or "").strip()
    if name not in character_names:
        name = "默认模板"
    store = state.load_character_constraints(name)
    versions = _template_version_options(name)
    valid_version_ids = {item["value"] for item in versions}
    selected = str(version_id or "").strip()
    if selected not in valid_version_ids:
        selected = str(store.get("selected_version") or "").strip()
    if selected not in valid_version_ids:
        selected = state.DEFAULT_PROMPT_VERSION_IDS.get(
            state._normalize_prompt_language(state.current_system_voice_language()) or state.DEFAULT_PROMPT_LANGUAGE,
            state.DEFAULT_PROMPT_VERSION_IDS[state.DEFAULT_PROMPT_LANGUAGE],
        )
    if selected not in valid_version_ids and versions:
        selected = versions[0]["value"]
    record = dict(store.get("versions", {}).get(selected, {}) or {})
    return {
        "characterName": name,
        "characterOptions": [{"label": item, "value": item} for item in character_names],
        "versionId": selected,
        "versionOptions": versions,
        "versionName": str(record.get("name") or ""),
        "constraintText": str(record.get("constraint_text") or ""),
        "source": str(record.get("source") or ""),
        "language": (
            state._normalize_prompt_language(record.get("language"))
            or state._prompt_language_from_version_id(selected)
            or state.DEFAULT_PROMPT_LANGUAGE
        ),
        "isDefaultTemplate": name == "默认模板",
    }


def _template_version_options(character_name: str) -> list[dict[str, str]]:
    language_labels = dict(state.PROMPT_LANGUAGE_OPTIONS)
    out: list[dict[str, str]] = []
    for version_id, record in state.list_constraint_versions(character_name):
        language = (
            state._normalize_prompt_language(record.get("language"))
            or state._prompt_language_from_version_id(version_id)
            or ""
        )
        version_name = str(record.get("name") or "").strip()
        if language and version_id == state.DEFAULT_PROMPT_VERSION_IDS.get(language):
            label_base = language_labels.get(language, language)
            label = f"{label_base} / {version_name}" if version_name else label_base
        else:
            label = f"{version_id} / {version_name}" if version_name else version_id
        out.append({"label": label, "value": version_id})
    return out


def _action_switch_provider(plugin_root: Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    from_provider = _normalize_provider(payload.get("fromProvider") or payload.get("provider"))
    to_provider = _normalize_provider(payload.get("toProvider"))
    save_payload = dict(payload)
    save_payload["provider"] = from_provider
    draft = _draft_from_payload(plugin_root, from_provider, save_payload)
    _save_draft(plugin_root, from_provider, draft)
    snapshot = load_snapshot(
        plugin_root,
        provider=to_provider,
        current_character=_payload_current_character(payload),
        template_character=_template_payload(payload).get("characterName"),
        template_version=_template_payload(payload).get("versionId"),
        status=f"已切换到 {provider_label(to_provider)} 配置视图。",
    )
    return {"values": snapshot, "status": snapshot["status"]}


def _action_import_voice_ids(plugin_root: Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    provider = _provider_from_payload(payload)
    if provider == state.GPT_SOVITS_PROVIDER_SLUG:
        raise ValueError("GPT SoVITS Cloud 使用服务器音频和模型路径，不支持导入本地 voice_id。")
    draft = _draft_from_payload(plugin_root, provider, payload)
    paths = payload.get("paths")
    if isinstance(paths, (str, Path)):
        paths = [paths]
    if not isinstance(paths, list):
        path = payload.get("path")
        paths = [path] if path else []
    imported = 0
    default_voice_id = ""
    errors: list[str] = []
    current_character = _payload_current_character(payload)
    for item in paths:
        source_path = Path(str(item or "")).expanduser()
        if not str(source_path):
            continue
        try:
            raw = json.loads(source_path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"{source_path.name}: {exc}")
            continue
        try:
            count, default_value = _import_voice_payload(
                draft,
                raw,
                source_path,
                current_character,
                provider,
            )
        except Exception as exc:
            errors.append(f"{source_path.name}: {exc}")
            continue
        imported += count
        if default_value:
            default_voice_id = default_value
    if default_voice_id:
        draft["default_voice_id"] = default_voice_id
    _save_draft(plugin_root, provider, draft)
    parts = []
    if imported:
        parts.append(f"已导入 {imported} 个 voice_id")
    if default_voice_id:
        parts.append("已更新默认 voice_id 候选")
    if errors:
        parts.append(f"{len(errors)} 个文件失败")
    status = "，".join(parts) or "没有找到可导入的 voice_id"
    snapshot = load_snapshot(
        plugin_root,
        provider=provider,
        current_character=current_character,
        template_character=_template_payload(payload).get("characterName"),
        template_version=_template_payload(payload).get("versionId"),
        status=status,
    )
    return {"values": snapshot, "imported": imported, "errors": errors, "status": status}


def _action_export_voice_id(plugin_root: Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    provider = _provider_from_payload(payload)
    if provider == state.GPT_SOVITS_PROVIDER_SLUG:
        return {"status": "GPT SoVITS Cloud 不使用本地 voice_id 导出。"}
    draft = _draft_from_payload(plugin_root, provider, payload)
    character_name = _payload_current_character(payload)
    payload_json = _current_voice_export_payload(provider, draft, character_name, payload)
    if not payload_json:
        return {"status": "当前角色没有可导出的 voice_id。"}
    path = _voice_export_default_path(payload_json)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload_json, ensure_ascii=False, indent=2), encoding="utf-8")
    url = f"/api/download?path={quote(str(path), safe='')}"
    status = f"已导出 voice_id：{path}"
    return {"path": str(path), "downloadUrl": url, "status": status, "payload": payload_json}


def _action_upload_voice(plugin_root: Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    provider = _provider_from_payload(payload)
    if provider == state.GPT_SOVITS_PROVIDER_SLUG:
        raise ValueError("GPT SoVITS Cloud 使用服务器已有音频和模型路径；请直接填写当前角色的 GSV 路径。")
    current_character = _payload_current_character(payload)
    character = state.find_character(current_character)
    if not character:
        raise ValueError("没有选中的角色。")
    draft = _draft_from_payload(plugin_root, provider, payload)
    name = str(character.get("name") or "").strip()
    local_path = _coerce_path_map(draft.get("local_reference_audio_map")).get(name, "")
    if not local_path:
        raise ValueError("请先选择一个存在的本地参考音频。")
    path = state.project_path(local_path).resolve()
    if not path.is_file():
        raise ValueError(f"本地参考音频不存在：{path}")
    is_qwen = provider == state.QWEN_PROVIDER_SLUG
    api_extra = state.get_qwen_extra() if is_qwen else state.get_cloud_extra()
    if not str(api_extra.get("api_key") or "").strip():
        label = "Qwen3 TTS" if is_qwen else "MiniMax TTS"
        raise ValueError(f"请先在 API 设定页选择 {label} 并填写 API KEY。")
    adapter_values = dict(draft)
    adapter_values.update(api_extra)
    adapter_values["use_runtime_config"] = False
    if is_qwen:
        adapter = QwenTTSAdapter(**adapter_values)
        voice_id = adapter.create_cloned_voice_from_file(
            path,
            character_name=name,
            voice_name=name,
            target_model=str(draft.get("model") or ""),
        )
    else:
        adapter = CloudTTSAdapter(**adapter_values)
        voice_id = adapter.create_cloned_voice_from_file(
            path,
            character_name=name,
            prompt_text=_reference_text_for_character(draft, character),
            reference_audio_language=_reference_audio_language_for_name(draft, name),
        )
    demo_audio_path = str(getattr(adapter, "last_clone_demo_audio_path", "") or "").strip()
    versions = _coerce_voice_id_versions(draft.get("voice_id_versions"))
    _ensure_voice_version(
        versions,
        name,
        voice_id,
        source="local_upload",
        provider=provider,
        provider_label=provider_label(provider),
        model=str(draft.get("model") or ""),
        reference_audio_path=str(path),
        reference_audio_source="本地参考音频",
        reference_audio_language=_reference_audio_language_for_name(draft, name),
    )
    voice_map = _coerce_voice_id_map(draft.get("voice_id_map"))
    voice_map[name] = voice_id
    draft["voice_id_versions"] = versions
    draft["voice_id_map"] = voice_map
    _save_draft(plugin_root, provider, draft)
    demo_record = None
    if provider == state.PROVIDER_SLUG and demo_audio_path:
        demo_record = _append_clone_demo_record(
            plugin_root,
            provider=provider,
            character_name=name,
            voice_id=voice_id,
            demo_audio_path=demo_audio_path,
            versions=versions,
            model=str(draft.get("model") or ""),
        )
    status = f"上传完成，已绑定 {name or '当前角色'} 的 voice_id：{voice_id}"
    if demo_audio_path:
        status += "；试听音频已下载。"
    snapshot = load_snapshot(
        plugin_root,
        provider=provider,
        current_character=name,
        template_character=_template_payload(payload).get("characterName"),
        template_version=_template_payload(payload).get("versionId"),
        status=status,
    )
    return {
        "values": snapshot,
        "voiceId": voice_id,
        "demoAudioPath": demo_audio_path,
        "demoRecord": demo_record or {},
        "status": status,
    }


def _action_select_template(plugin_root: Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    template = _template_payload(payload)
    name = str(template.get("characterName") or "默认模板").strip() or "默认模板"
    version_id = str(template.get("versionId") or "").strip()
    if version_id:
        state.select_constraint_version(name, version_id)
    snapshot = load_snapshot(
        plugin_root,
        provider=_provider_from_payload(payload),
        current_character=_payload_current_character(payload),
        template_character=name,
        template_version=version_id,
        status=f"已切换模板：{name} / {version_id}",
    )
    return {"values": snapshot, "status": snapshot["status"]}


def _action_save_template(plugin_root: Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    template = _template_payload(payload)
    name = str(template.get("characterName") or "").strip()
    version_id = str(template.get("versionId") or "").strip()
    if not name or not version_id:
        raise ValueError("请先选择角色和模板语言。")
    text = str(template.get("constraintText") or "").strip()
    if not text:
        raise ValueError("约束内容不能为空。")
    version_name = str(template.get("versionName") or "").strip()
    language = _template_language(name, version_id)
    if name == "默认模板":
        state.upsert_constraint_version(
            name,
            version_id,
            text,
            name=version_name,
            source="default",
            language=language,
        )
        count = state.propagate_default_template(text, language=language)
        status = f"已保存默认模板。已同步 {count} 个使用默认模板的角色。"
    else:
        state.upsert_constraint_version(
            name,
            version_id,
            text,
            name=version_name,
            source="manual",
            language=language,
        )
        status = f"已保存 {name} 的模板语言 {version_id}。"
    snapshot = load_snapshot(
        plugin_root,
        provider=_provider_from_payload(payload),
        current_character=_payload_current_character(payload),
        template_character=name,
        template_version=version_id,
        status=status,
    )
    return {"values": snapshot, "status": status}


def _action_reset_template(plugin_root: Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    template = _template_payload(payload)
    name = str(template.get("characterName") or "").strip()
    version_id = str(template.get("versionId") or "").strip()
    if not name or not version_id:
        raise ValueError("请先选择要重置的提示词版本。")
    language = _template_language(name, version_id)
    default_text = state.build_default_constraint_text(language)
    version_name = str(template.get("versionName") or "").strip()
    state.upsert_constraint_version(
        name,
        version_id,
        default_text,
        name=version_name,
        source="default",
        language=language,
    )
    if name == "默认模板":
        count = state.propagate_default_template(default_text, language=language)
        status = f"已重置默认模板为原始内容。已同步 {count} 个使用默认模板的角色。"
    else:
        label = dict(state.PROMPT_LANGUAGE_OPTIONS).get(language, language)
        status = f"已重置角色「{name}」的 {label} 模板为原始内容。"
    snapshot = load_snapshot(
        plugin_root,
        provider=_provider_from_payload(payload),
        current_character=_payload_current_character(payload),
        template_character=name,
        template_version=version_id,
        status=status,
    )
    return {"values": snapshot, "status": status}


def _action_create_template(plugin_root: Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    template = _template_payload(payload)
    name = str(template.get("characterName") or "").strip()
    if not name or name == "默认模板":
        raise ValueError("默认模板不支持新建自定义版本。")
    version_id = str(template.get("versionId") or "").strip()
    text = str(template.get("constraintText") or "").strip()
    if not text:
        text = state.get_default_template_text(_template_language(name, version_id))
    language = _template_language(name, version_id)
    version_name = str(template.get("versionName") or "").strip() or "新版本"
    _store, new_version_id = state.upsert_constraint_version(
        name,
        None,
        text,
        name=version_name,
        source="manual",
        language=language,
    )
    status = f"已为 {name} 创建新约束版本。"
    snapshot = load_snapshot(
        plugin_root,
        provider=_provider_from_payload(payload),
        current_character=_payload_current_character(payload),
        template_character=name,
        template_version=new_version_id,
        status=status,
    )
    return {"values": snapshot, "status": status, "versionId": new_version_id}


def _action_delete_template(plugin_root: Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    template = _template_payload(payload)
    name = str(template.get("characterName") or "").strip()
    version_id = str(template.get("versionId") or "").strip()
    if not name or not version_id:
        raise ValueError("请先选择角色和版本。")
    if name == "默认模板":
        raise ValueError("默认模板不支持删除版本。")
    if len(state.list_constraint_versions(name)) <= 1:
        raise ValueError("至少需要保留一个约束版本。")
    if not state.remove_constraint_version(name, version_id):
        raise ValueError("删除失败。")
    status = f"已删除约束版本「{version_id}」。"
    snapshot = load_snapshot(
        plugin_root,
        provider=_provider_from_payload(payload),
        current_character=_payload_current_character(payload),
        template_character=name,
        status=status,
    )
    return {"values": snapshot, "status": status}


def _template_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    template = payload.get("template")
    return dict(template) if isinstance(template, Mapping) else {}


def _template_language(character_name: str, version_id: str) -> str:
    store = state.load_character_constraints(character_name)
    old_version = store.get("versions", {}).get(version_id, {})
    language = old_version.get("language") if isinstance(old_version, dict) else None
    return (
        state._normalize_prompt_language(language)
        or state._prompt_language_from_version_id(version_id)
        or state.DEFAULT_PROMPT_LANGUAGE
    )


def _current_voice_export_payload(
    provider: str,
    draft: dict[str, Any],
    character_name: str,
    payload: Mapping[str, Any],
) -> dict[str, Any] | None:
    name = str(character_name or "").strip()
    selected = payload.get("selectedCharacter")
    voice_id = ""
    if isinstance(selected, Mapping):
        voice_id = str(selected.get("voiceId") or "").strip()
    if not voice_id:
        voice_id = _coerce_voice_id_map(draft.get("voice_id_map")).get(name, "")
    if not voice_id:
        return None
    record: dict[str, Any] = {}
    for item in _coerce_voice_id_versions(draft.get("voice_id_versions")).get(name, []):
        if str(item.get("voice_id") or "").strip() == voice_id:
            record = dict(item)
            break
    export_payload = {
        key: value
        for key, value in record.items()
        if key not in VOICE_ID_EXPORT_EXCLUDED_KEYS and value not in (None, "", [], {})
    }
    export_payload.update(
        {
            "type": "cloud_tts.voice_id",
            "provider": provider,
            "provider_label": provider_label(provider),
            "character_name": name,
            "voice_id": voice_id,
            "model": str(draft.get("model") or export_payload.get("model") or ""),
            "exported_at": int(time.time()),
        }
    )
    return export_payload


def _voice_export_default_path(payload: dict[str, Any]) -> Path:
    name = str(payload.get("character_name") or "voice").strip() or "voice"
    voice_id = str(payload.get("voice_id") or "voice_id").strip() or "voice_id"
    stem = f"{name}_{voice_id}"
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in stem)
    safe = safe.strip("._-")[:96] or "cloud_tts_voice_id"
    return state.project_root() / f"{safe}.json"


def _import_voice_payload(
    draft: dict[str, Any],
    raw: Any,
    source_path: Path,
    current_character: str,
    provider: str,
) -> tuple[int, str]:
    if isinstance(raw, list):
        imported = 0
        default_voice_id = ""
        for item in raw:
            count, default_value = _import_voice_payload(
                draft,
                item,
                source_path,
                current_character,
                provider,
            )
            imported += count
            if default_value:
                default_voice_id = default_value
        return imported, default_voice_id
    if not isinstance(raw, dict):
        return 0, ""
    if not _voice_payload_matches_provider(provider, raw):
        return 0, ""

    imported = 0
    default_voice_id = str(raw.get("default_voice_id") or "").strip()
    if default_voice_id:
        target_character = (
            current_character
            if current_character and state.find_character(current_character)
            else IMPORTED_VOICE_BUCKET
        )
        _bind_imported_voice_record(
            draft,
            target_character,
            default_voice_id,
            {
                "source": "import_default",
                "imported_from": str(source_path),
                "provider": provider,
                "provider_label": provider_label(provider),
            },
            selected=target_character == IMPORTED_VOICE_BUCKET,
        )

    if "voice_id_map" in raw or "voice_id_versions" in raw or "voice_map" in raw:
        imported += _import_voice_config_payload(draft, raw, source_path, current_character, provider)

    character_name = str(
        raw.get("character_name")
        or raw.get("character")
        or raw.get("name")
        or ""
    ).strip()
    if character_name:
        selected = str(raw.get("selected_voice_id") or raw.get("voice_id") or "").strip()
        raw_voices = raw.get("voices") or raw.get("versions") or []
        if selected and not raw_voices:
            raw_voices = [raw]
        target_character, target_mode = _import_voice_target_character(character_name, current_character)
        if selected and not default_voice_id:
            default_voice_id = selected
        counted_voice_ids: set[str] = set()
        for rec in _coerce_voice_records(raw_voices):
            voice_id = str(rec.get("voice_id") or "").strip()
            clean = dict(rec)
            clean.pop("voice_id", None)
            clean.setdefault("source", "import")
            clean["imported_from"] = str(source_path)
            if target_mode != "matched" and character_name != target_character:
                clean["imported_character_name"] = character_name
            clean.setdefault("provider", provider)
            clean.setdefault("provider_label", provider_label(provider))
            _bind_imported_voice_record(
                draft,
                target_character,
                voice_id,
                clean,
                selected=bool(selected and voice_id == selected),
            )
            if voice_id not in counted_voice_ids:
                counted_voice_ids.add(voice_id)
                imported += 1
            if voice_id and not default_voice_id:
                default_voice_id = voice_id
        if selected:
            clean = {"source": "import_selected", "imported_from": str(source_path)}
            if target_mode != "matched" and character_name != target_character:
                clean["imported_character_name"] = character_name
            clean.setdefault("provider", provider)
            clean.setdefault("provider_label", provider_label(provider))
            _bind_imported_voice_record(
                draft,
                target_character,
                selected,
                clean,
                selected=True,
            )
            if selected not in counted_voice_ids:
                imported += 1
        return imported, default_voice_id

    voice_id = str(raw.get("voice_id") or raw.get("id") or "").strip()
    if voice_id and not default_voice_id:
        default_voice_id = voice_id
    if voice_id and current_character and state.find_character(current_character):
        _bind_imported_voice_record(
            draft,
            current_character,
            voice_id,
            {
                "source": "import_manual",
                "imported_from": str(source_path),
                "provider": provider,
                "provider_label": provider_label(provider),
            },
            selected=True,
        )
        imported += 1
    elif voice_id:
        _bind_imported_voice_record(
            draft,
            IMPORTED_VOICE_BUCKET,
            voice_id,
            {
                "source": "import_manual",
                "imported_from": str(source_path),
                "provider": provider,
                "provider_label": provider_label(provider),
            },
            selected=True,
        )
        imported += 1
    return imported, default_voice_id


def _import_voice_config_payload(
    draft: dict[str, Any],
    raw: dict[str, Any],
    source_path: Path,
    current_character: str,
    provider: str,
) -> int:
    imported = 0
    counted_voice_ids: set[tuple[str, str]] = set()
    voice_map = _coerce_voice_id_map(raw.get("voice_id_map") or raw.get("voice_map"))
    for name, voice_id in voice_map.items():
        target_name, target_mode = _import_voice_target_character(name, current_character)
        clean = {
            "source": "import_map",
            "imported_from": str(source_path),
            "provider": provider,
            "provider_label": provider_label(provider),
        }
        if target_mode != "matched" and name != target_name:
            clean["imported_character_name"] = name
        _bind_imported_voice_record(draft, target_name, voice_id, clean, selected=True)
        key = (target_name, voice_id)
        if key not in counted_voice_ids:
            counted_voice_ids.add(key)
            imported += 1
    versions = _coerce_voice_id_versions(raw.get("voice_id_versions"))
    for name, records in versions.items():
        target_name, target_mode = _import_voice_target_character(name, current_character)
        for rec in records:
            voice_id = str(rec.get("voice_id") or "").strip()
            clean = dict(rec)
            clean.pop("voice_id", None)
            if not _voice_payload_matches_provider(provider, clean):
                continue
            clean.setdefault("source", "import_versions")
            clean["imported_from"] = str(source_path)
            clean.setdefault("provider", provider)
            clean.setdefault("provider_label", provider_label(provider))
            if target_mode != "matched" and name != target_name:
                clean["imported_character_name"] = name
            _bind_imported_voice_record(draft, target_name, voice_id, clean, selected=False)
            key = (target_name, voice_id)
            if key not in counted_voice_ids:
                counted_voice_ids.add(key)
                imported += 1
    return imported


def _import_voice_target_character(exported_character_name: str, current_character: str) -> tuple[str, str]:
    exported_name = (exported_character_name or "").strip()
    current_name = (current_character or "").strip()
    if current_name and state.find_character(current_name):
        return current_name, "current"
    if exported_name and state.find_character(exported_name):
        return exported_name, "matched"
    return IMPORTED_VOICE_BUCKET, "imported"


def _bind_imported_voice_record(
    draft: dict[str, Any],
    character_name: str,
    voice_id: str,
    record: dict[str, Any],
    *,
    selected: bool,
) -> int:
    target_name = (character_name or "").strip()
    vid = (voice_id or "").strip()
    if not target_name or not vid:
        return 0
    clean = dict(record)
    for key in {"voice_id", *VOICE_ID_EXPORT_EXCLUDED_KEYS}:
        clean.pop(key, None)
    source = str(clean.pop("source", "import") or "import")
    versions = _coerce_voice_id_versions(draft.get("voice_id_versions"))
    _ensure_voice_version(versions, target_name, vid, source=source, **clean)
    draft["voice_id_versions"] = versions
    if selected:
        voice_map = _coerce_voice_id_map(draft.get("voice_id_map"))
        voice_map[target_name] = vid
        draft["voice_id_map"] = voice_map
    return 1


def _ensure_voice_version(
    versions: dict[str, list[dict[str, Any]]],
    character_name: str,
    voice_id: str,
    *,
    source: str,
    **extra: Any,
) -> None:
    name = (character_name or "").strip()
    vid = (voice_id or "").strip()
    if not name or not vid:
        return
    bucket = versions.setdefault(name, [])
    if any(str(item.get("voice_id") or "").strip() == vid for item in bucket):
        return
    record: dict[str, Any] = {
        "voice_id": vid,
        "source": source,
        "created_at": int(time.time()),
    }
    record.update({key: value for key, value in extra.items() if value not in (None, "")})
    bucket.append(record)


def _ensure_versions_from_selected_map(
    voice_map: dict[str, str],
    versions: dict[str, list[dict[str, Any]]],
) -> None:
    for name, voice_id in list(voice_map.items()):
        _ensure_voice_version(versions, name, voice_id, source="selected")


def _reference_text_for_character(draft: dict[str, Any], character: dict[str, Any]) -> str:
    name = str(character.get("name") or "").strip()
    text = _coerce_text_map(draft.get("reference_text_map")).get(name, "").strip()
    if text:
        return text
    return str(character.get("prompt_text") or "").strip()


def _reference_audio_language_for_name(draft: dict[str, Any], character_name: str) -> str:
    name = (character_name or "").strip()
    if not name:
        return "auto"
    return state.normalize_voice_language_code(
        state.coerce_voice_language_map(draft.get("reference_audio_language_map")).get(name, "auto")
    )


def _valid_choice(value: Any, options: tuple[str, ...], default: str) -> str:
    text = str(value or "").strip()
    return text if text in options else default


def _coerce_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            try:
                value = ast.literal_eval(value)
            except Exception:
                value = {}
    return dict(value) if isinstance(value, Mapping) else {}


def _coerce_voice_id_map(value: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, item in _coerce_mapping(value).items():
        name = str(key or "").strip()
        voice_id = str(item or "").strip()
        if name and voice_id:
            out[name] = voice_id
    return out


def _coerce_path_map(value: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, item in _coerce_mapping(value).items():
        name = str(key or "").strip()
        path = str(item or "").strip()
        if name and path:
            out[name] = path
    return out


def _coerce_text_map(value: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, item in _coerce_mapping(value).items():
        name = str(key or "").strip()
        text = str(item or "").strip()
        if name and text:
            out[name] = text
    return out


def _coerce_voice_id_versions(value: Any) -> dict[str, list[dict[str, Any]]]:
    raw = _coerce_mapping(value)
    out: dict[str, list[dict[str, Any]]] = {}
    for key, items in raw.items():
        name = str(key or "").strip()
        if not name:
            continue
        raw_items = items if isinstance(items, list) else [items]
        seen: set[str] = set()
        versions: list[dict[str, Any]] = []
        for item in raw_items:
            if isinstance(item, Mapping):
                record = dict(item)
                voice_id = str(record.get("voice_id") or record.get("id") or "").strip()
            else:
                record = {}
                voice_id = str(item or "").strip()
            if not voice_id or voice_id in seen:
                continue
            record["voice_id"] = voice_id
            record.setdefault("created_at", 0)
            versions.append(record)
            seen.add(voice_id)
        if versions:
            out[name] = versions
    return out


def _coerce_voice_records(value: Any) -> list[dict[str, Any]]:
    raw_items = value if isinstance(value, list) else [value]
    out: list[dict[str, Any]] = []
    for item in raw_items:
        if isinstance(item, Mapping):
            record = dict(item)
            voice_id = str(record.get("voice_id") or record.get("id") or "").strip()
        else:
            record = {}
            voice_id = str(item or "").strip()
        if not voice_id:
            continue
        record["voice_id"] = voice_id
        out.append(record)
    return out


def _coerce_gpt_sovits_profiles(value: Any) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for key, item in _coerce_mapping(value).items():
        name = str(key or "").strip()
        if not name or not isinstance(item, Mapping):
            continue
        profile = _coerce_gpt_sovits_profile(item)
        if profile:
            out[name] = profile
    return out


def _coerce_gpt_sovits_profile(value: Mapping[str, Any]) -> dict[str, str]:
    profile: dict[str, str] = {}
    for key in GSV_PROFILE_KEYS:
        text = str(value.get(key) or "").strip()
        if text:
            profile[key] = text
    return profile


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
