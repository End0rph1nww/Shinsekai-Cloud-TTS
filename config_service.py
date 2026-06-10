"""UI 无关的配置与音色数据服务层。

`settings.py`（Qt 设置页）与后续 React 插件页共用的唯一逻辑真相源。
本模块只依赖 `state` 与 adapter 常量，不得 import 任何 Qt / 浏览器概念。

音色数据采用「调用方持有字典、本模块原地修改」的约定：
`voice_id_map` / `voice_id_versions` 由 UI 层持有引用并传入，导入与版本
管理函数直接在传入的字典上修改，调用方无需接收返回值再回写。
"""

from __future__ import annotations

import ast
import json
import time
from pathlib import Path
from typing import Any

from plugins.cloud_tts import state
from plugins.cloud_tts.adapter import VALID_MODELS

IMPORTED_VOICE_BUCKET = "__imported__"
IMPORTED_VOICE_LABEL = "导入音色"
MINIMAX_DEFAULT_MODEL = "speech-2.8-hd"
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


# ----------------------------------------------------------------------
# 基础规整
# ----------------------------------------------------------------------


def valid_choice(value: Any, valid: tuple[str, ...], default: str) -> str:
    item = str(value or "").strip()
    if item in valid:
        return item
    lowered = item.lower()
    for candidate in valid:
        if candidate.lower() == lowered:
            return candidate
    return default


def as_bool(value: Any, default: bool) -> bool:
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


def _parse_loose_dict(value: Any) -> Any:
    """旧配置可能把 dict 存成 JSON 或 repr 字符串，宽松解析后原样返回。"""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            try:
                return ast.literal_eval(value)
            except Exception:
                return {}
    return value


def coerce_voice_id_map(value: Any) -> dict[str, str]:
    value = _parse_loose_dict(value)
    if not isinstance(value, dict):
        return {}
    out: dict[str, str] = {}
    for key, item in value.items():
        name = str(key or "").strip()
        vid = str(item or "").strip()
        if name and vid:
            out[name] = vid
    return out


def coerce_path_map(value: Any) -> dict[str, str]:
    value = _parse_loose_dict(value)
    if not isinstance(value, dict):
        return {}
    out: dict[str, str] = {}
    for key, item in value.items():
        name = str(key or "").strip()
        path = str(item or "").strip()
        if name and path:
            out[name] = path
    return out


def coerce_text_map(value: Any) -> dict[str, str]:
    value = _parse_loose_dict(value)
    if not isinstance(value, dict):
        return {}
    out: dict[str, str] = {}
    for key, item in value.items():
        name = str(key or "").strip()
        text = str(item or "").strip()
        if name and text:
            out[name] = text
    return out


def coerce_voice_id_versions(value: Any) -> dict[str, list[dict[str, Any]]]:
    value = _parse_loose_dict(value)
    if not isinstance(value, dict):
        return {}
    out: dict[str, list[dict[str, Any]]] = {}
    for key, items in value.items():
        name = str(key or "").strip()
        if not name:
            continue
        raw_items = items if isinstance(items, list) else [items]
        seen: set[str] = set()
        versions: list[dict[str, Any]] = []
        for item in raw_items:
            if isinstance(item, dict):
                rec = dict(item)
                voice_id = str(rec.get("voice_id") or rec.get("id") or "").strip()
            else:
                rec = {}
                voice_id = str(item or "").strip()
            if not voice_id or voice_id in seen:
                continue
            rec["voice_id"] = voice_id
            rec.setdefault("created_at", 0)
            versions.append(rec)
            seen.add(voice_id)
        if versions:
            out[name] = versions
    return out


def coerce_gpt_sovits_profiles(value: Any) -> dict[str, dict[str, str]]:
    value = _parse_loose_dict(value)
    if not isinstance(value, dict):
        return {}
    out: dict[str, dict[str, str]] = {}
    keys = {
        "ref_audio_path",
        "gpt_weights_path",
        "sovits_weights_path",
        "prompt_text",
        "prompt_lang",
        "text_lang",
    }
    for key, item in value.items():
        name = str(key or "").strip()
        if not name or not isinstance(item, dict):
            continue
        profile = {}
        for field in keys:
            text_value = str(item.get(field) or "").strip()
            if text_value:
                profile[field] = text_value
        if profile:
            out[name] = profile
    return out


def coerce_voice_records(value: Any) -> list[dict[str, Any]]:
    raw_items = value if isinstance(value, list) else [value]
    out: list[dict[str, Any]] = []
    for item in raw_items:
        if isinstance(item, dict):
            rec = dict(item)
            voice_id = str(rec.get("voice_id") or rec.get("id") or "").strip()
        else:
            rec = {}
            voice_id = str(item or "").strip()
        if not voice_id:
            continue
        rec["voice_id"] = voice_id
        out.append(rec)
    return out


def gpt_sovits_state_from_config(values: dict[str, Any]) -> dict[str, Any]:
    keys = {
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
    return {k: values[k] for k in keys if k in values}


# ----------------------------------------------------------------------
# Provider 推导与 api.yaml extra 读写
# ----------------------------------------------------------------------


def is_qwen_provider(provider_slug: str) -> bool:
    return provider_slug == state.QWEN_PROVIDER_SLUG


def is_gpt_sovits_provider(provider_slug: str) -> bool:
    return provider_slug == state.GPT_SOVITS_PROVIDER_SLUG


def provider_model_options(provider_slug: str) -> tuple[str, ...]:
    if is_qwen_provider(provider_slug):
        return state.QWEN_MODELS
    if is_gpt_sovits_provider(provider_slug):
        return state.GPT_SOVITS_MODELS
    return VALID_MODELS


def provider_default_model(provider_slug: str) -> str:
    if is_qwen_provider(provider_slug):
        return state.QWEN_DEFAULT_MODEL
    if is_gpt_sovits_provider(provider_slug):
        return state.GPT_SOVITS_DEFAULT_MODEL
    return MINIMAX_DEFAULT_MODEL


def provider_label(provider_slug: str) -> str:
    if is_qwen_provider(provider_slug):
        return "Qwen3 TTS"
    if is_gpt_sovits_provider(provider_slug):
        return "GPT SoVITS Cloud"
    return "MiniMax TTS"


def get_provider_extra(provider_slug: str) -> dict[str, Any]:
    """返回指定 provider 的 api.yaml extra 配置。"""
    if is_qwen_provider(provider_slug):
        return state.get_qwen_extra()
    if is_gpt_sovits_provider(provider_slug):
        return state.get_gpt_sovits_extra()
    return state.get_cloud_extra()


def set_provider_extra(provider_slug: str, values: dict[str, Any]) -> None:
    """保存 model / default_voice_id 等到指定 provider 的 api.yaml extra。"""
    if is_qwen_provider(provider_slug):
        state.set_qwen_extra(values)
    elif is_gpt_sovits_provider(provider_slug):
        state.set_gpt_sovits_extra(values)
    else:
        state.set_cloud_extra(values)


# ----------------------------------------------------------------------
# 参考音频 / 文本查询
# ----------------------------------------------------------------------


def reference_text_for_character(
    char: dict[str, Any],
    reference_text_map: dict[str, str],
) -> str:
    name = str(char.get("name") or "").strip()
    if name:
        text = reference_text_map.get(name, "").strip()
        if text:
            return text
    return str(char.get("prompt_text") or "").strip()


def reference_audio_language_for_name(
    character_name: str,
    reference_audio_language_map: dict[str, str],
) -> str:
    name = (character_name or "").strip()
    if not name:
        return "auto"
    return state.normalize_voice_language_code(
        reference_audio_language_map.get(name, "auto")
    )


def reference_audio_for_upload(
    char: dict[str, Any],
    local_reference_audio_map: dict[str, str],
) -> tuple[Path | None, str]:
    name = str(char.get("name") or "").strip()
    local_path = local_reference_audio_map.get(name, "").strip()
    if local_path:
        return state.project_path(local_path).resolve(), "本地参考音频"
    return None, "本地参考音频"


# ----------------------------------------------------------------------
# 音色版本管理（原地修改调用方传入的字典）
# ----------------------------------------------------------------------


def ensure_voice_version(
    voice_id_versions: dict[str, list[dict[str, Any]]],
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
    versions = voice_id_versions.setdefault(name, [])
    if any(str(item.get("voice_id") or "").strip() == vid for item in versions):
        return
    rec: dict[str, Any] = {
        "voice_id": vid,
        "source": source,
        "created_at": int(time.time()),
    }
    rec.update({k: v for k, v in extra.items() if v not in (None, "")})
    versions.append(rec)


def ensure_versions_from_selected_map(
    voice_id_map: dict[str, str],
    voice_id_versions: dict[str, list[dict[str, Any]]],
) -> None:
    for name, voice_id in list(voice_id_map.items()):
        ensure_voice_version(voice_id_versions, name, voice_id, source="selected")


def all_voice_options(
    voice_id_map: dict[str, str],
    voice_id_versions: dict[str, list[dict[str, Any]]],
) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for name, versions in voice_id_versions.items():
        clean_name = str(name or "").strip()
        bucket_label_name = (
            IMPORTED_VOICE_LABEL if clean_name == IMPORTED_VOICE_BUCKET else clean_name
        )
        for idx, rec in enumerate(versions, start=1):
            voice_id = str(rec.get("voice_id") or "").strip()
            if not voice_id or voice_id in seen:
                continue
            display_name = str(rec.get("imported_character_name") or "").strip()
            label_name = display_name or bucket_label_name
            label = f"{label_name} / 版本 {idx} / {voice_id}"
            out.append((label, voice_id))
            seen.add(voice_id)
    for name, voice_id in voice_id_map.items():
        if voice_id and voice_id not in seen:
            label_name = IMPORTED_VOICE_LABEL if name == IMPORTED_VOICE_BUCKET else name
            out.append((f"{label_name} / 当前 / {voice_id}", voice_id))
            seen.add(voice_id)
    return out


# ----------------------------------------------------------------------
# 音色导出
# ----------------------------------------------------------------------


def voice_export_payload(
    character_name: str,
    voice_id: str,
    voice_id_versions: dict[str, list[dict[str, Any]]],
    *,
    provider_slug: str,
    model: str,
) -> dict[str, Any] | None:
    character_name = (character_name or "").strip()
    voice_id = (voice_id or "").strip()
    if not voice_id:
        return None
    record: dict[str, Any] = {}
    for item in voice_id_versions.get(character_name, []):
        if str(item.get("voice_id") or "").strip() == voice_id:
            record = dict(item)
            break
    payload = {
        key: value
        for key, value in record.items()
        if key not in VOICE_ID_EXPORT_EXCLUDED_KEYS
        and value not in (None, "", [], {})
    }
    payload.update(
        {
            "type": "cloud_tts.voice_id",
            "provider": provider_slug,
            "provider_label": provider_label(provider_slug),
            "character_name": character_name,
            "voice_id": voice_id,
            "model": str(model or payload.get("model") or ""),
            "exported_at": int(time.time()),
        }
    )
    return payload


def voice_export_default_path(payload: dict[str, Any]) -> Path:
    name = str(payload.get("character_name") or "voice").strip() or "voice"
    voice_id = str(payload.get("voice_id") or "voice_id").strip() or "voice_id"
    stem = f"{name}_{voice_id}"
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in stem)
    safe = safe.strip("._-")[:96] or "cloud_tts_voice_id"
    return state.project_root() / f"{safe}.json"


# ----------------------------------------------------------------------
# 音色导入
# ----------------------------------------------------------------------


def import_voice_target_character(
    exported_character_name: str,
    current_character: str,
) -> tuple[str, str]:
    exported_name = (exported_character_name or "").strip()
    current_name = (current_character or "").strip()
    if current_name and state.find_character(current_name):
        return current_name, "current"
    if exported_name and state.find_character(exported_name):
        return exported_name, "matched"
    return IMPORTED_VOICE_BUCKET, "imported"


def bind_imported_voice_record(
    voice_id_map: dict[str, str],
    voice_id_versions: dict[str, list[dict[str, Any]]],
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
    clean.setdefault("source", "import")
    ensure_voice_version(voice_id_versions, target_name, vid, **clean)
    if selected:
        voice_id_map[target_name] = vid
    return 1


def import_voice_payload(
    voice_id_map: dict[str, str],
    voice_id_versions: dict[str, list[dict[str, Any]]],
    raw: Any,
    source_path: Path,
    *,
    current_character: str,
) -> tuple[int, str]:
    if isinstance(raw, list):
        imported = 0
        default_voice_id = ""
        for item in raw:
            count, default_value = import_voice_payload(
                voice_id_map,
                voice_id_versions,
                item,
                source_path,
                current_character=current_character,
            )
            imported += count
            if default_value:
                default_voice_id = default_value
        return imported, default_voice_id
    if not isinstance(raw, dict):
        return 0, ""

    imported = 0
    default_voice_id = str(raw.get("default_voice_id") or "").strip()
    current_character = (current_character or "").strip()
    if default_voice_id:
        target_character = (
            current_character
            if current_character and state.find_character(current_character)
            else IMPORTED_VOICE_BUCKET
        )
        bind_imported_voice_record(
            voice_id_map,
            voice_id_versions,
            target_character,
            default_voice_id,
            {"source": "import_default", "imported_from": str(source_path)},
            selected=target_character == IMPORTED_VOICE_BUCKET,
        )

    if "voice_id_map" in raw or "voice_id_versions" in raw or "voice_map" in raw:
        imported += import_voice_config_payload(
            voice_id_map,
            voice_id_versions,
            raw,
            source_path,
            current_character=current_character,
        )

    character_name = str(
        raw.get("character_name")
        or raw.get("character")
        or raw.get("name")
        or ""
    ).strip()
    if character_name:
        selected = str(
            raw.get("selected_voice_id")
            or raw.get("voice_id")
            or ""
        ).strip()
        raw_voices = raw.get("voices") or raw.get("versions") or []
        if selected and not raw_voices:
            raw_voices = [raw]
        target_character, target_mode = import_voice_target_character(
            character_name, current_character
        )
        if selected and not default_voice_id:
            default_voice_id = selected
        counted_voice_ids: set[str] = set()
        for rec in coerce_voice_records(raw_voices):
            voice_id = str(rec.get("voice_id") or "").strip()
            clean = dict(rec)
            clean.pop("voice_id", None)
            clean.setdefault("source", "import")
            clean["imported_from"] = str(source_path)
            if target_mode != "matched" and character_name != target_character:
                clean["imported_character_name"] = character_name
            bind_imported_voice_record(
                voice_id_map,
                voice_id_versions,
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
            clean = {
                "source": "import_selected",
                "imported_from": str(source_path),
            }
            if target_mode != "matched" and character_name != target_character:
                clean["imported_character_name"] = character_name
            bind_imported_voice_record(
                voice_id_map,
                voice_id_versions,
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
        bind_imported_voice_record(
            voice_id_map,
            voice_id_versions,
            current_character,
            voice_id,
            {"source": "import_manual", "imported_from": str(source_path)},
            selected=True,
        )
        imported += 1
    elif voice_id:
        bind_imported_voice_record(
            voice_id_map,
            voice_id_versions,
            IMPORTED_VOICE_BUCKET,
            voice_id,
            {"source": "import_manual", "imported_from": str(source_path)},
            selected=True,
        )
        imported += 1

    return imported, default_voice_id


def import_voice_config_payload(
    voice_id_map: dict[str, str],
    voice_id_versions: dict[str, list[dict[str, Any]]],
    raw: dict[str, Any],
    source_path: Path,
    *,
    current_character: str,
) -> int:
    imported = 0
    counted_voice_ids: set[tuple[str, str]] = set()
    voice_map = coerce_voice_id_map(raw.get("voice_id_map") or raw.get("voice_map"))
    for name, voice_id in voice_map.items():
        target_name, target_mode = import_voice_target_character(name, current_character)
        clean = {"source": "import_map", "imported_from": str(source_path)}
        if target_mode != "matched" and name != target_name:
            clean["imported_character_name"] = name
        bind_imported_voice_record(
            voice_id_map,
            voice_id_versions,
            target_name,
            voice_id,
            clean,
            selected=True,
        )
        key = (target_name, voice_id)
        if key not in counted_voice_ids:
            counted_voice_ids.add(key)
            imported += 1
    versions = coerce_voice_id_versions(raw.get("voice_id_versions"))
    for name, records in versions.items():
        target_name, target_mode = import_voice_target_character(name, current_character)
        for rec in records:
            voice_id = str(rec.get("voice_id") or "").strip()
            clean = dict(rec)
            clean.pop("voice_id", None)
            clean.setdefault("source", "import_versions")
            clean["imported_from"] = str(source_path)
            if target_mode != "matched" and name != target_name:
                clean["imported_character_name"] = name
            bind_imported_voice_record(
                voice_id_map,
                voice_id_versions,
                target_name,
                voice_id,
                clean,
                selected=False,
            )
            key = (target_name, voice_id)
            if key not in counted_voice_ids:
                counted_voice_ids.add(key)
                imported += 1
    return imported
