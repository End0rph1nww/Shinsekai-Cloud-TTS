from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

import yaml


PROVIDER_SLUG = "minimax-tts"
PLUGIN_ID = "com.shinsekai.minimax_tts"
PLUGIN_ENTRY = "plugins.minimax_tts.plugin:MinimaxTtsPlugin"
PLUGIN_VERSION = "0.2.0"

# API 页面只保留连接凭证，避免和插件设置页重复展示行为参数。
ADAPTER_CONFIG_KEYS = {
    "api_key",
    "base_api_url",
}

# 这些字段由 MiniMax 插件设置页维护，运行时仍会传给 TTS adapter。
PLUGIN_STATE_KEYS = {
    "model",
    "voice_cache_path",
    "language_boost",
    "audio_format",
    "sample_rate",
    "bitrate",
    "channel",
    "speed",
    "vol",
    "pitch",
    "emotion",
    "request_timeout",
    "auto_clone_from_reference",
    "need_noise_reduction",
    "need_volume_normalization",
    "auto_prompt_constraint",
    "paragraph_split_enabled",
}

PROMPT_START = "<<<MINIMAX_TTS_TONE_CONSTRAINT_START>>>"
PROMPT_END = "<<<MINIMAX_TTS_TONE_CONSTRAINT_END>>>"
_PROMPT_CONSTRAINT_SUPPRESS_UNTIL = 0.0
PROMPT_CONSTRAINT = f"""{PROMPT_START}
当模板要求输出 translate 字段时，translate 字段会作为 MiniMax 文生音输入。因此，日语译文可以根据台词情绪，在合适位置加入 MiniMax 支持的语气标签，用于辅助语音表现。
speech 字段必须保持自然简体中文，不出现 (laughs)、(sighs) 等标签。
语气标签只能放在 translate 字段，不要放进 speech 字段。
可用标签包括但不限于：
(laughs)：轻笑、大笑、调侃、开心、得意时使用。
(sighs)：叹气、无奈、担心、疲惫、收束语气时使用。
(breath)：轻呼吸、停顿、靠近感、柔和语气时使用。
(gasps)：惊讶、震惊、突然发现异常时使用。
(crying)：哭腔、委屈、强烈难过时使用。
使用要求：
speech 字段必须保持自然简体中文，不出现 (laughs)、(sighs) 等标签。
标签应放在最能表现情绪的位置。
通常可以放在句首，例如：
(laughs)りょ、先輩。これは華淡の勝ちですね。
也可以放在句中停顿处，例如：
えっと……(sighs)先輩、それは少し危ないかもです。
日常轻松对话可以适当增加 (laughs)、(breath)；
标签不翻译成中文，也不写进旁白。
它只是给 MiniMax TTS 使用的语音控制提示。
轻快调侃、得意、自信：优先使用 (laughs)
惊讶、发现异常、ヤバ 展开：优先使用 (gasps)
担心、提醒风险、需要刹车：优先使用 (sighs)
温柔陪伴、靠近感、语音助手模式：可使用 (breath)
明显委屈、害怕失去连接、强烈情绪：使用 (crying)
{PROMPT_END}"""


def project_root() -> Path:
    cwd = Path.cwd()
    if (cwd / "data" / "config").is_dir():
        return cwd.resolve()
    return Path(__file__).resolve().parents[2]


def project_path(value: str | Path) -> Path:
    p = Path(value)
    if p.is_absolute():
        return p
    return project_root() / p


def api_config_path() -> Path:
    return project_root() / "data" / "config" / "api.yaml"


def characters_config_path() -> Path:
    return project_root() / "data" / "config" / "characters.yaml"


def plugin_manifest_path() -> Path:
    return project_root() / "data" / "config" / "plugins.yaml"


def plugin_package_root() -> Path:
    return Path(__file__).resolve().parent


def plugin_data_root() -> Path:
    return project_root() / "data" / "plugins" / PLUGIN_ID.replace("/", "_")


def legacy_package_voice_store_root() -> Path:
    return plugin_package_root() / "voices"


def voice_store_root() -> Path:
    return plugin_data_root() / "voices"


def voice_defaults_path() -> Path:
    return voice_store_root() / "_defaults.json"


def migrate_legacy_voice_store() -> None:
    legacy = legacy_package_voice_store_root()
    target = voice_store_root()
    if not legacy.is_dir():
        return
    target.mkdir(parents=True, exist_ok=True)
    for src in legacy.glob("*.json"):
        dst = target / src.name
        if not dst.exists():
            dst.write_bytes(src.read_bytes())
    # 旧文件是用户运行数据，迁移时只复制不删除，避免插件升级过程误伤。


def read_yaml(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return default
    return default if raw is None else raw


def write_yaml(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def load_api_config() -> dict[str, Any]:
    raw = read_yaml(api_config_path(), {})
    return raw if isinstance(raw, dict) else {}


def save_api_config(data: dict[str, Any]) -> None:
    write_yaml(api_config_path(), data)


def get_minimax_extra() -> dict[str, Any]:
    data = load_api_config()
    all_extra = data.get("tts_extra_configs")
    if not isinstance(all_extra, dict):
        return {}
    cur = all_extra.get(PROVIDER_SLUG)
    return dict(cur) if isinstance(cur, dict) else {}


def set_minimax_extra(extra: dict[str, Any]) -> None:
    data = load_api_config()
    all_extra = data.get("tts_extra_configs")
    if not isinstance(all_extra, dict):
        all_extra = {}
    merged = adapter_config_from_values(dict(all_extra.get(PROVIDER_SLUG) or {}))
    merged.update(adapter_config_from_values(extra))
    all_extra[PROVIDER_SLUG] = merged
    data["tts_extra_configs"] = all_extra
    save_api_config(data)


def adapter_config_from_values(values: dict[str, Any]) -> dict[str, Any]:
    """抽取官方 adapter extra 配置，供 api.yaml 持久化。"""
    return {k: values[k] for k in ADAPTER_CONFIG_KEYS if k in values}


def plugin_state_from_values(values: dict[str, Any]) -> dict[str, Any]:
    """只保留插件私有状态，避免把 API key 等 adapter 参数写进插件源码区。"""
    return {k: values[k] for k in PLUGIN_STATE_KEYS if k in values}


def migrate_api_extra_to_plugin_state(plugin_root: Path | None = None) -> None:
    """把旧版 api.yaml 中的行为参数迁回插件数据目录，只留下 API 凭证。"""
    extra = get_minimax_extra()
    state_values = plugin_state_from_values(extra)
    api_values = adapter_config_from_values(extra)
    if not state_values:
        if extra != api_values:
            set_minimax_extra(api_values)
        return
    root = plugin_root or plugin_data_root()
    current = _read_json(root / "config.json", {})
    current_cfg = dict(current) if isinstance(current, dict) else {}
    merged = dict(state_values)
    merged.update(
        {k: v for k, v in current_cfg.items() if v not in (None, "", {}, [])}
    )
    _write_plugin_config_file(root, plugin_state_from_values(merged))
    set_minimax_extra(api_values)


def set_tts_provider(provider: str) -> None:
    data = load_api_config()
    data["tts_provider"] = provider
    save_api_config(data)


def current_tts_provider() -> str:
    data = load_api_config()
    return str(data.get("tts_provider") or "").strip()


def clear_minimax_tts_provider_if_selected() -> bool:
    """插件被禁用时，避免主菜单保留一个下一次无法注册的 MiniMax TTS 引擎。"""
    data = load_api_config()
    if str(data.get("tts_provider") or "").strip().lower() == PROVIDER_SLUG:
        data["tts_provider"] = "none"
        save_api_config(data)
        return True
    return False


def remove_minimax_extra() -> None:
    data = load_api_config()
    all_extra = data.get("tts_extra_configs")
    if isinstance(all_extra, dict):
        all_extra.pop(PROVIDER_SLUG, None)
        data["tts_extra_configs"] = all_extra
        save_api_config(data)


def _read_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default
    return raw


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _voice_file_stem(character_name: str) -> str:
    name = (character_name or "").strip()
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    safe = safe.strip("._-")[:48]
    if not safe:
        safe = "character"
    return f"{safe}_{short_hash(name, 10)}"


def voice_file_path(character_name: str) -> Path:
    return voice_store_root() / f"{_voice_file_stem(character_name)}.json"


def _normalize_voice_record(item: Any) -> dict[str, Any] | None:
    if isinstance(item, dict):
        rec = dict(item)
        voice_id = str(rec.get("voice_id") or rec.get("id") or "").strip()
    else:
        rec = {}
        voice_id = str(item or "").strip()
    if not voice_id:
        return None
    rec["voice_id"] = voice_id
    rec.setdefault("created_at", 0)
    return rec


def _voice_stores_from_config(cfg: dict[str, Any]) -> dict[str, dict[str, Any]]:
    stores: dict[str, dict[str, Any]] = {}
    raw_map = cfg.get("voice_id_map")
    raw_versions = cfg.get("voice_id_versions")
    if not isinstance(raw_map, dict):
        raw_map = {}
    if not isinstance(raw_versions, dict):
        raw_versions = {}
    for name, voice_id in raw_map.items():
        character_name = str(name or "").strip()
        vid = str(voice_id or "").strip()
        if not character_name or not vid:
            continue
        stores.setdefault(
            character_name,
            {
                "character_name": character_name,
                "selected_voice_id": vid,
                "voices": [],
            },
        )
    for name, items in raw_versions.items():
        character_name = str(name or "").strip()
        if not character_name:
            continue
        raw_items = items if isinstance(items, list) else [items]
        store = stores.setdefault(
            character_name,
            {
                "character_name": character_name,
                "selected_voice_id": "",
                "voices": [],
            },
        )
        seen = {
            str(rec.get("voice_id") or "").strip()
            for rec in store.get("voices", [])
            if isinstance(rec, dict)
        }
        for item in raw_items:
            rec = _normalize_voice_record(item)
            if not rec:
                continue
            vid = str(rec["voice_id"])
            if vid in seen:
                continue
            store.setdefault("voices", []).append(rec)
            seen.add(vid)
    for store in stores.values():
        selected = str(store.get("selected_voice_id") or "").strip()
        if selected and not any(
            str(rec.get("voice_id") or "").strip() == selected
            for rec in store.get("voices", [])
            if isinstance(rec, dict)
        ):
            store.setdefault("voices", []).append(
                {
                    "voice_id": selected,
                    "source": "selected",
                    "created_at": 0,
                }
            )
    return stores


def load_voice_stores() -> dict[str, dict[str, Any]]:
    migrate_legacy_voice_store()
    root = voice_store_root()
    stores: dict[str, dict[str, Any]] = {}
    if not root.is_dir():
        return stores
    for path in sorted(root.glob("*.json")):
        raw = _read_json(path, {})
        if not isinstance(raw, dict):
            continue
        character_name = str(raw.get("character_name") or "").strip()
        if not character_name:
            continue
        voices: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in raw.get("voices") or []:
            rec = _normalize_voice_record(item)
            if not rec:
                continue
            vid = str(rec["voice_id"])
            if vid in seen:
                continue
            voices.append(rec)
            seen.add(vid)
        selected = str(raw.get("selected_voice_id") or "").strip()
        if not selected and voices:
            selected = str(voices[-1].get("voice_id") or "").strip()
        stores[character_name] = {
            "character_name": character_name,
            "selected_voice_id": selected,
            "voices": voices,
            "updated_at": int(raw.get("updated_at") or 0),
        }
    return stores


def load_voice_defaults() -> dict[str, Any]:
    migrate_legacy_voice_store()
    raw = _read_json(voice_defaults_path(), {})
    return dict(raw) if isinstance(raw, dict) else {}


def save_voice_defaults(default_voice_id: str | None) -> None:
    voice_id = str(default_voice_id or "").strip()
    path = voice_defaults_path()
    if not voice_id:
        if path.exists():
            path.unlink()
        return
    _write_json(path, {"default_voice_id": voice_id})


def voice_config_from_files() -> tuple[dict[str, str], dict[str, list[dict[str, Any]]]]:
    stores = load_voice_stores()
    voice_map: dict[str, str] = {}
    versions: dict[str, list[dict[str, Any]]] = {}
    for name, store in stores.items():
        selected = str(store.get("selected_voice_id") or "").strip()
        voices = [dict(rec) for rec in store.get("voices", []) if isinstance(rec, dict)]
        if selected:
            voice_map[name] = selected
        if voices:
            versions[name] = voices
    return voice_map, versions


def save_voice_config_to_files(
    voice_id_map: dict[str, str] | None,
    voice_id_versions: dict[str, Any] | None,
) -> None:
    cfg = {
        "voice_id_map": voice_id_map or {},
        "voice_id_versions": voice_id_versions or {},
    }
    stores = _voice_stores_from_config(cfg)
    for character_name, store in stores.items():
        store["updated_at"] = int(time.time())
        _write_json(voice_file_path(character_name), store)


def upsert_voice_record(
    character_name: str,
    voice_id: str,
    record: dict[str, Any] | None = None,
    *,
    selected: bool = True,
) -> None:
    name = (character_name or "").strip()
    vid = (voice_id or "").strip()
    if not name or not vid:
        return
    path = voice_file_path(name)
    raw = _read_json(path, {})
    if not isinstance(raw, dict):
        raw = {}
    voices = []
    seen: set[str] = set()
    for item in raw.get("voices") or []:
        rec = _normalize_voice_record(item)
        if not rec:
            continue
        cur = str(rec["voice_id"])
        if cur in seen:
            continue
        voices.append(rec)
        seen.add(cur)
    if vid not in seen:
        rec = dict(record or {})
        rec["voice_id"] = vid
        rec.setdefault("created_at", int(time.time()))
        voices.append(rec)
    raw["character_name"] = name
    raw["voices"] = voices
    if selected:
        raw["selected_voice_id"] = vid
    else:
        raw.setdefault("selected_voice_id", vid)
    raw["updated_at"] = int(time.time())
    _write_json(path, raw)


def _strip_voice_config(data: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(data)
    for key in (
        "voice_id_map",
        "voice_id_versions",
        "voice_map",
        "voice_id",
        "voice_id_prefix",
        "default_voice_id",
    ):
        cleaned.pop(key, None)
    return cleaned


def _write_plugin_config_file(plugin_root: Path, data: dict[str, Any]) -> None:
    plugin_root.mkdir(parents=True, exist_ok=True)
    _write_json(plugin_root / "config.json", data)


def _merge_voice_files_into_config(data: dict[str, Any]) -> dict[str, Any]:
    merged = dict(data)
    raw_default_voice_id = str(merged.get("default_voice_id") or "").strip()
    voice_map, versions = voice_config_from_files()
    defaults = load_voice_defaults()
    if raw_default_voice_id and "default_voice_id" not in defaults:
        save_voice_defaults(raw_default_voice_id)
        defaults = load_voice_defaults()
    old_stores = _voice_stores_from_config(merged)
    if old_stores:
        old_map: dict[str, str] = {}
        old_versions: dict[str, list[dict[str, Any]]] = {}
        for name, store in old_stores.items():
            selected = str(store.get("selected_voice_id") or "").strip()
            voices = [dict(rec) for rec in store.get("voices", []) if isinstance(rec, dict)]
            if selected and name not in voice_map:
                old_map[name] = selected
            if voices and name not in versions:
                old_versions[name] = voices
        if old_map or old_versions:
            save_voice_config_to_files(
                {**old_map, **voice_map},
                {**old_versions, **versions},
            )
            voice_map, versions = voice_config_from_files()
    merged = _strip_voice_config(merged)
    if voice_map:
        merged["voice_id_map"] = voice_map
    if versions:
        merged["voice_id_versions"] = versions
    default_voice_id = str(defaults.get("default_voice_id") or "").strip()
    if default_voice_id:
        merged["default_voice_id"] = default_voice_id
    return merged


def load_plugin_config(plugin_root: Path) -> dict[str, Any]:
    roots = [plugin_root, plugin_data_root(), plugin_package_root()]
    seen: set[Path] = set()
    paths: list[Path] = []
    for root in roots:
        try:
            path = (root / "config.json").resolve()
        except OSError:
            path = root / "config.json"
        if path not in seen:
            paths.append(path)
            seen.add(path)
    for path in paths:
        if not path.is_file():
            continue
        raw = _read_json(path, {})
        if isinstance(raw, dict):
            return _merge_voice_files_into_config(raw)
    return {}


def load_plugin_base_config() -> dict[str, Any]:
    for root in (plugin_data_root(), plugin_package_root()):
        raw = _read_json(root / "config.json", {})
        if isinstance(raw, dict):
            return dict(raw)
    return {}


def _bool_config_value(value: Any, default: bool) -> bool:
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


def save_plugin_config(plugin_root: Path, data: dict[str, Any]) -> None:
    voice_map = data.get("voice_id_map")
    voice_versions = data.get("voice_id_versions")
    save_voice_defaults(str(data.get("default_voice_id") or ""))
    if isinstance(voice_map, dict) or isinstance(voice_versions, dict):
        save_voice_config_to_files(
            voice_map if isinstance(voice_map, dict) else {},
            voice_versions if isinstance(voice_versions, dict) else {},
        )
    _write_plugin_config_file(plugin_root, plugin_state_from_values(data))


def migrate_package_config_to_data_root() -> None:
    src = plugin_package_root() / "config.json"
    dst_root = plugin_data_root()
    dst = dst_root / "config.json"
    if not src.is_file():
        return
    src_cfg = load_plugin_config(plugin_package_root())
    if not src_cfg:
        return
    dst_cfg: dict[str, Any] = {}
    if dst.is_file():
        try:
            raw = json.loads(dst.read_text(encoding="utf-8"))
        except Exception:
            raw = {}
        if isinstance(raw, dict):
            dst_cfg = raw
    merged = dict(src_cfg)
    merged.update({k: v for k, v in dst_cfg.items() if v not in (None, "", {}, [])})
    adapter_extra = adapter_config_from_values(merged)
    if adapter_extra:
        set_minimax_extra(adapter_extra)
    save_plugin_config(dst_root, merged)


def load_runtime_plugin_config() -> dict[str, Any]:
    migrate_package_config_to_data_root()
    migrate_api_extra_to_plugin_state()
    return load_plugin_config(plugin_data_root())


def load_characters() -> list[dict[str, Any]]:
    raw = read_yaml(characters_config_path(), [])
    if not isinstance(raw, list):
        return []
    return [dict(item) for item in raw if isinstance(item, dict)]


def find_character(name: str) -> dict[str, Any] | None:
    target = (name or "").strip().lower()
    for item in load_characters():
        if str(item.get("name", "")).strip().lower() == target:
            return item
    return None


def resolve_reference_audio(character: dict[str, Any]) -> Path | None:
    raw = str(character.get("refer_audio_path") or "").strip()
    if not raw:
        return None
    return project_path(raw).resolve()


def remove_prompt_constraint_text(text: str) -> str:
    src = text or ""
    pattern = re.compile(
        rf"{re.escape(PROMPT_START)}.*?{re.escape(PROMPT_END)}[ \t]*(?:\r?\n)*",
        re.DOTALL,
    )
    return pattern.sub("", src).lstrip("\r\n")


def add_prompt_constraint_text(text: str) -> str:
    base = remove_prompt_constraint_text(text)
    if base:
        base = base.lstrip("\r\n")
        return f"{PROMPT_CONSTRAINT}\n\n{base}"
    return f"{PROMPT_CONSTRAINT}\n"


def sync_prompt_constraint_text(text: str, *, active: bool) -> str:
    """按主 TTS 选择同步 MiniMax 语气约束，只触碰约束块本身。"""
    if active:
        return add_prompt_constraint_text(text)
    return remove_prompt_constraint_text(text)


def suppress_prompt_constraint(seconds: float = 3.0) -> None:
    """插件设置页保存期间短暂抑制模板 hook，避免 UI 刷新误注入系统提示词。"""
    global _PROMPT_CONSTRAINT_SUPPRESS_UNTIL
    until = time.monotonic() + max(0.1, float(seconds or 0.0))
    _PROMPT_CONSTRAINT_SUPPRESS_UNTIL = max(_PROMPT_CONSTRAINT_SUPPRESS_UNTIL, until)


def prompt_constraint_suppressed() -> bool:
    return time.monotonic() < _PROMPT_CONSTRAINT_SUPPRESS_UNTIL


def prompt_constraint_enabled() -> bool:
    cfg = load_plugin_base_config()
    if "auto_prompt_constraint" in cfg:
        return bool(cfg.get("auto_prompt_constraint"))
    return True


def prompt_constraint_active() -> bool:
    """只有插件启用且主 TTS 已选择 MiniMax 时，才向模板注入语气约束。"""
    if prompt_constraint_suppressed():
        return False
    if not plugin_manifest_enabled():
        return False
    if current_tts_provider().lower() != PROVIDER_SLUG:
        return False
    return prompt_constraint_enabled()


def paragraph_split_enabled() -> bool:
    cfg = load_plugin_base_config()
    return _bool_config_value(cfg.get("paragraph_split_enabled"), True)


def paragraph_split_active() -> bool:
    """Paragraph handler 随插件启用而生效，不强制要求主 TTS 已切到 MiniMax。"""
    if not plugin_manifest_enabled():
        return False
    return paragraph_split_enabled()


def plugin_manifest_enabled() -> bool:
    raw = read_yaml(plugin_manifest_path(), [])
    if not isinstance(raw, list):
        return True
    found = False
    for item in raw:
        if not isinstance(item, dict):
            continue
        entry = str(item.get("entry") or "").strip()
        if entry == PLUGIN_ENTRY:
            found = True
            return bool(item.get("enabled", True))
    return True if not found else False


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def short_hash(text: str, size: int = 16) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:size]
