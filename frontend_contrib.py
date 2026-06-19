"""React 插件页 API 面（PR80+ 宿主）。

`build_api_surface()` 返回 schema 置空的 ``FrontendConfigContribution``：
宿主不渲染表单（同 page_id 的 iframe 页独占渲染），它只承担三件事——
``load_values`` 全量快照、``save_values`` 白名单落盘、actions 工作流通道。
`build_page()` 返回同 page_id 的 ``FrontendPageContribution``（iframe 界面）。

注意：本模块顶层 import 了 PR80+ 才存在的 SDK 类型，旧宿主上 import 会失败。
只能从 ``plugin.py`` 的特性检测分支延迟 import，不得在 plugin.py 顶层 import。

鉴权边界：``api_key`` / ``base_api_url`` 属宿主全局 TTS 设置，本模块对外只暴露
``key_configured`` 布尔，save_values 白名单确保它们永远不会被这里读改。
"""

from __future__ import annotations

import base64
import re
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote

from sdk.types import (
    FrontendConfigAction,
    FrontendConfigContribution,
    FrontendPageContribution,
)

from plugins.cloud_tts import config_service as service
from plugins.cloud_tts import state

PAGE_ID = "cloud_tts"
PAGE_TITLE = "Cloud TTS"
PACKAGE_ROOT = Path(__file__).resolve().parent

PROVIDER_SLUGS = (
    state.PROVIDER_SLUG,
    state.QWEN_PROVIDER_SLUG,
    state.GPT_SOVITS_PROVIDER_SLUG,
)
REFERENCE_AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac"}
MAX_REFERENCE_AUDIO_BYTES = 20 * 1024 * 1024
_SAFE_NAME_RE = re.compile(r"[^0-9A-Za-z一-鿿._-]+")

# save_values 只接受插件域字段；鉴权字段（api_key / base_api_url）不在名单内。
_SAVABLE_BOOL_KEYS = ("auto_prompt_constraint", "protect_translate_tone_tags")
_SAVABLE_TEXT_KEYS = (
    "model",
    "default_voice_id",
    "qwen_language_type",
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
)


def _safe_name(value: str, fallback: str) -> str:
    cleaned = _SAFE_NAME_RE.sub("_", str(value or "").strip()).strip("._-")
    return cleaned[:96] or fallback


def _provider_slug(values: Mapping[str, Any]) -> str:
    slug = str(values.get("provider") or "").strip()
    if slug not in PROVIDER_SLUGS:
        raise ValueError(f"未知的 provider：{slug or '(空)'}")
    return slug


def _character_name(values: Mapping[str, Any]) -> str:
    name = str(values.get("character") or "").strip()
    if not name:
        raise ValueError("character 不能为空")
    return name


def _load_provider_config(plugin_root: Path, slug: str) -> dict[str, Any]:
    cfg = state.load_plugin_config(plugin_root, slug)
    return {k: v for k, v in cfg.items() if v not in (None, "", {}, [])}


def _provider_maps(cfg: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "voice_id_map": service.coerce_voice_id_map(cfg.get("voice_id_map")),
        "voice_id_versions": service.coerce_voice_id_versions(cfg.get("voice_id_versions")),
        "local_reference_audio_map": service.coerce_path_map(
            cfg.get("local_reference_audio_map")
        ),
        "reference_audio_language_map": state.coerce_voice_language_map(
            cfg.get("reference_audio_language_map")
        ),
        "reference_text_map": service.coerce_text_map(cfg.get("reference_text_map")),
    }


def _save_provider_config(
    plugin_root: Path,
    slug: str,
    cfg: dict[str, Any],
) -> None:
    state.suppress_prompt_constraint()
    state.save_plugin_config(plugin_root, cfg, slug)


def _provider_block(plugin_root: Path, slug: str) -> dict[str, Any]:
    cfg = _load_provider_config(plugin_root, slug)
    extra = service.get_provider_extra(slug)
    models = service.provider_model_options(slug)
    maps = _provider_maps(cfg)
    block: dict[str, Any] = {
        "slug": slug,
        "label": service.provider_label(slug),
        "models": list(models),
        "model": service.valid_choice(
            extra.get("model") or cfg.get("model"),
            models,
            service.provider_default_model(slug),
        ),
        "key_configured": bool(str(extra.get("api_key") or "").strip()),
        "auto_prompt_constraint": service.as_bool(cfg.get("auto_prompt_constraint"), False),
        "protect_translate_tone_tags": service.as_bool(
            cfg.get("protect_translate_tone_tags"), True
        ),
        **maps,
        "voice_options": [
            {"label": label, "voice_id": voice_id}
            for label, voice_id in service.all_voice_options(
                maps["voice_id_map"], maps["voice_id_versions"]
            )
        ],
    }
    if not service.is_gpt_sovits_provider(slug):
        block["default_voice_id"] = str(
            extra.get("default_voice_id") or cfg.get("default_voice_id") or ""
        )
    if service.is_qwen_provider(slug):
        block["language_type"] = str(
            extra.get("language_type") or cfg.get("qwen_language_type") or "Chinese"
        )
    if service.is_gpt_sovits_provider(slug):
        gsv = service.gpt_sovits_state_from_config(cfg)
        gsv.setdefault("gpt_sovits_text_split_method", "cut5")
        gsv.setdefault("gpt_sovits_media_type", "wav")
        gsv.setdefault("gpt_sovits_sample_steps", "32")
        gsv["gpt_sovits_super_sampling"] = service.as_bool(
            gsv.get("gpt_sovits_super_sampling"), False
        )
        gsv["gpt_sovits_character_profiles"] = service.coerce_gpt_sovits_profiles(
            cfg.get("gpt_sovits_character_profiles")
        )
        block["gpt_sovits"] = gsv
    return block


def _default_edit_provider() -> str:
    current = state.current_tts_provider()
    if state.is_gpt_sovits_provider(current):
        return state.GPT_SOVITS_PROVIDER_SLUG
    if state.is_qwen_tts_provider(current):
        return state.QWEN_PROVIDER_SLUG
    return state.PROVIDER_SLUG


def _load_values(plugin_root: Path) -> dict[str, Any]:
    state.migrate_package_config_to_data_root()
    state.migrate_api_extra_to_plugin_state(plugin_root)
    return {
        "provider": _default_edit_provider(),
        "providers": [_provider_block(plugin_root, slug) for slug in PROVIDER_SLUGS],
        "characters": [
            {
                "name": str(char.get("name") or "").strip(),
                "prompt_text": str(char.get("prompt_text") or "").strip(),
            }
            for char in state.load_characters()
            if str(char.get("name") or "").strip()
        ],
        "prompt_languages": [
            {"code": code, "label": label} for code, label in state.PROMPT_LANGUAGE_OPTIONS
        ],
    }


def _save_values(plugin_root: Path, values: Mapping[str, Any]) -> None:
    slug = _provider_slug(values)
    cfg = state.load_plugin_config(plugin_root, slug)
    merged = dict(cfg)
    for key in _SAVABLE_BOOL_KEYS:
        if key in values:
            merged[key] = service.as_bool(values.get(key), bool(merged.get(key)))
    for key in _SAVABLE_TEXT_KEYS:
        if key in values:
            merged[key] = str(values.get(key) or "").strip()
    if "gpt_sovits_super_sampling" in values:
        merged["gpt_sovits_super_sampling"] = service.as_bool(
            values.get("gpt_sovits_super_sampling"), False
        )
    if "model" in merged:
        merged["model"] = service.valid_choice(
            merged.get("model"),
            service.provider_model_options(slug),
            service.provider_default_model(slug),
        )
    _save_provider_config(plugin_root, slug, merged)

    provider_extra = {"model": str(merged.get("model") or "")}
    if not service.is_gpt_sovits_provider(slug):
        provider_extra["default_voice_id"] = str(merged.get("default_voice_id") or "")
    if service.is_qwen_provider(slug):
        provider_extra["language_type"] = str(
            merged.get("qwen_language_type") or "Chinese"
        )
    service.set_provider_extra(slug, provider_extra)
    try:
        from plugins.cloud_tts import prompt_hook

        prompt_hook.sync_frontend_template_session()
    except Exception:
        pass


# ----------------------------------------------------------------------
# Actions
# ----------------------------------------------------------------------


def _character_row(
    plugin_root: Path,
    slug: str,
    character_name: str,
    *,
    cfg: Mapping[str, Any] | None = None,
    character: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = cfg if cfg is not None else _load_provider_config(plugin_root, slug)
    maps = _provider_maps(cfg)
    profiles = service.coerce_gpt_sovits_profiles(cfg.get("gpt_sovits_character_profiles"))
    char = dict(character) if character is not None else state.find_character(character_name) or {"name": character_name}
    card_reference = state.resolve_reference_audio(char)
    return {
        "name": character_name,
        "voice_id": maps["voice_id_map"].get(character_name, ""),
        "versions": maps["voice_id_versions"].get(character_name, []),
        "reference_audio": maps["local_reference_audio_map"].get(character_name, ""),
        "reference_text": maps["reference_text_map"].get(character_name, ""),
        "reference_language": service.reference_audio_language_for_name(
            character_name, maps["reference_audio_language_map"]
        ),
        "card_reference_audio": str(card_reference) if card_reference else "",
        "prompt_text": str(char.get("prompt_text") or "").strip(),
        "gpt_sovits_profile": profiles.get(character_name, {}),
    }


def _action_list_characters(plugin_root: Path, values: Mapping[str, Any]) -> dict[str, Any]:
    slug = _provider_slug(values)
    cfg = _load_provider_config(plugin_root, slug)
    rows = [
        _character_row(
            plugin_root,
            slug,
            str(char.get("name") or "").strip(),
            cfg=cfg,
            character=char,
        )
        for char in state.load_characters()
        if str(char.get("name") or "").strip()
    ]
    return {"characters": rows, "provider": slug}


def _action_bind_voice(plugin_root: Path, values: Mapping[str, Any]) -> dict[str, Any]:
    slug = _provider_slug(values)
    name = _character_name(values)
    voice_id = str(values.get("voice_id") or "").strip()
    cfg = state.load_plugin_config(plugin_root, slug)
    maps = _provider_maps(cfg)
    if voice_id:
        maps["voice_id_map"][name] = voice_id
        service.ensure_voice_version(
            maps["voice_id_versions"], name, voice_id, source="manual"
        )
    else:
        maps["voice_id_map"].pop(name, None)
    cfg.update(maps)
    _save_provider_config(plugin_root, slug, cfg)
    return {"character": _character_row(plugin_root, slug, name)}


def _store_reference(
    cfg: dict[str, Any],
    name: str,
    *,
    path: str | None = None,
    text: str | None = None,
    language: str | None = None,
) -> None:
    maps = _provider_maps(cfg)
    if path is not None:
        if path:
            maps["local_reference_audio_map"][name] = path
        else:
            maps["local_reference_audio_map"].pop(name, None)
    if text is not None:
        if text.strip():
            maps["reference_text_map"][name] = text.strip()
        else:
            maps["reference_text_map"].pop(name, None)
    if language is not None:
        code = state.normalize_voice_language_code(language)
        if code == "auto":
            maps["reference_audio_language_map"].pop(name, None)
        else:
            maps["reference_audio_language_map"][name] = code
    cfg.update(maps)


def _action_upload_reference(plugin_root: Path, values: Mapping[str, Any]) -> dict[str, Any]:
    slug = _provider_slug(values)
    name = _character_name(values)
    filename = str(values.get("filename") or "").strip()
    suffix = Path(filename).suffix.lower()
    if suffix not in REFERENCE_AUDIO_EXTS:
        raise ValueError(
            f"不支持的音频格式：{suffix or '(无扩展名)'}；支持 {' '.join(sorted(REFERENCE_AUDIO_EXTS))}"
        )
    content_b64 = str(values.get("content_base64") or "")
    try:
        content = base64.b64decode(content_b64, validate=True)
    except Exception as exc:
        raise ValueError(f"音频内容解码失败：{exc}") from exc
    if not content:
        raise ValueError("音频内容为空")
    if len(content) > MAX_REFERENCE_AUDIO_BYTES:
        raise ValueError(
            f"音频超过 {MAX_REFERENCE_AUDIO_BYTES // (1024 * 1024)}MB 上限，请压缩后重试"
        )

    target_dir = state.plugin_data_root() / "reference_audio" / _safe_name(name, "character")
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / (_safe_name(Path(filename).stem, "reference") + suffix)
    target.write_bytes(content)

    cfg = state.load_plugin_config(plugin_root, slug)
    _store_reference(
        cfg,
        name,
        path=str(target),
        text=str(values.get("text")) if "text" in values else None,
        language=str(values.get("language")) if "language" in values else None,
    )
    _save_provider_config(plugin_root, slug, cfg)
    return {"path": str(target), "character": _character_row(plugin_root, slug, name)}


def _action_clear_reference(plugin_root: Path, values: Mapping[str, Any]) -> dict[str, Any]:
    slug = _provider_slug(values)
    name = _character_name(values)
    cfg = state.load_plugin_config(plugin_root, slug)
    _store_reference(cfg, name, path="")
    _save_provider_config(plugin_root, slug, cfg)
    return {"character": _character_row(plugin_root, slug, name)}


def _build_adapter(plugin_root: Path, slug: str):
    cfg = state.load_plugin_config(plugin_root, slug)
    adapter_values = dict(cfg)
    adapter_values.update(service.get_provider_extra(slug))
    adapter_values["use_runtime_config"] = False
    if service.is_qwen_provider(slug):
        from plugins.cloud_tts.qwen_adapter import QwenTTSAdapter

        return QwenTTSAdapter(**adapter_values)
    if service.is_gpt_sovits_provider(slug):
        from plugins.cloud_tts.gpt_sovits_adapter import GPTSoVITSApiAdapter

        return GPTSoVITSApiAdapter(**adapter_values)
    from plugins.cloud_tts.adapter import CloudTTSAdapter

    return CloudTTSAdapter(**adapter_values)


def _media_url(path: str) -> str:
    cleaned = str(path or "").strip()
    if not cleaned:
        return ""
    return f"/api/media?path={quote(cleaned, safe='')}"


def _action_clone_voice(plugin_root: Path, values: Mapping[str, Any]) -> dict[str, Any]:
    slug = _provider_slug(values)
    if service.is_gpt_sovits_provider(slug):
        raise ValueError(
            "GPT SoVITS Cloud 使用服务器已有音频和模型路径，请直接保存当前角色的 GSV profile。"
        )
    name = _character_name(values)
    char = state.find_character(name)
    if not char:
        raise ValueError(f"角色不存在：{name}")
    extra = service.get_provider_extra(slug)
    if not str(extra.get("api_key") or "").strip():
        raise ValueError(
            f"请先在宿主 API 设定页为 {service.provider_label(slug)} 填写 API KEY。"
        )

    cfg = state.load_plugin_config(plugin_root, slug)
    maps = _provider_maps(cfg)
    path, source_label = service.reference_audio_for_upload(
        char, maps["local_reference_audio_map"]
    )
    if not path or not path.is_file():
        raise ValueError("请先为该角色上传一个本地参考音频。")

    adapter = _build_adapter(plugin_root, slug)
    model = str(extra.get("model") or cfg.get("model") or "")
    if service.is_qwen_provider(slug):
        voice_id = adapter.create_cloned_voice_from_file(
            path,
            character_name=name,
            voice_name=name,
            target_model=model,
        )
    else:
        voice_id = adapter.create_cloned_voice_from_file(
            path,
            character_name=name,
            prompt_text=service.reference_text_for_character(
                char, maps["reference_text_map"]
            ),
            reference_audio_language=service.reference_audio_language_for_name(
                name, maps["reference_audio_language_map"]
            ),
        )

    service.ensure_voice_version(
        maps["voice_id_versions"],
        name,
        voice_id,
        source="local_upload" if source_label.startswith("本地") else "upload",
        model=model,
        reference_audio_path=str(path),
        reference_audio_source=source_label,
        reference_audio_language=service.reference_audio_language_for_name(
            name, maps["reference_audio_language_map"]
        ),
    )
    maps["voice_id_map"][name] = voice_id
    cfg.update(maps)
    _save_provider_config(plugin_root, slug, cfg)

    demo_path = str(getattr(adapter, "last_clone_demo_audio_path", "") or "").strip()
    return {
        "voice_id": voice_id,
        "demo_path": demo_path,
        "demo_url": _media_url(demo_path),
        "character": _character_row(plugin_root, slug, name),
    }


def _action_export_voice(plugin_root: Path, values: Mapping[str, Any]) -> dict[str, Any]:
    slug = _provider_slug(values)
    name = _character_name(values)
    cfg = _load_provider_config(plugin_root, slug)
    maps = _provider_maps(cfg)
    voice_id = str(values.get("voice_id") or "").strip() or maps["voice_id_map"].get(name, "")
    extra = service.get_provider_extra(slug)
    payload = service.voice_export_payload(
        name,
        voice_id,
        maps["voice_id_versions"],
        provider_slug=slug,
        model=str(extra.get("model") or cfg.get("model") or ""),
    )
    if not payload:
        raise ValueError(f"角色 {name} 没有可导出的 voice_id。")
    return {
        "payload": payload,
        "filename": service.voice_export_default_path(payload).name,
    }


def _action_import_voice(plugin_root: Path, values: Mapping[str, Any]) -> dict[str, Any]:
    slug = _provider_slug(values)
    payload = values.get("payload")
    if not isinstance(payload, (dict, list)):
        raise ValueError("payload 必须是导出的 JSON 对象或数组")
    source_name = _safe_name(str(values.get("source_name") or ""), "import") + ".json"
    current_character = str(values.get("character") or "").strip()

    cfg = state.load_plugin_config(plugin_root, slug)
    maps = _provider_maps(cfg)
    imported, default_voice_id = service.import_voice_payload(
        maps["voice_id_map"],
        maps["voice_id_versions"],
        payload,
        Path(source_name),
        current_character=current_character,
    )
    service.ensure_versions_from_selected_map(
        maps["voice_id_map"], maps["voice_id_versions"]
    )
    cfg.update(maps)
    if default_voice_id and not service.is_gpt_sovits_provider(slug):
        cfg["default_voice_id"] = str(cfg.get("default_voice_id") or "") or default_voice_id
    _save_provider_config(plugin_root, slug, cfg)
    return {
        "imported": imported,
        "default_voice_id": default_voice_id,
        "provider": slug,
    }


def _action_save_gpt_sovits_profile(
    plugin_root: Path, values: Mapping[str, Any]
) -> dict[str, Any]:
    slug = state.GPT_SOVITS_PROVIDER_SLUG
    name = _character_name(values)
    raw_profile = values.get("profile")
    if not isinstance(raw_profile, dict):
        raise ValueError("profile 必须是对象")
    cfg = state.load_plugin_config(plugin_root, slug)
    profiles = service.coerce_gpt_sovits_profiles(cfg.get("gpt_sovits_character_profiles"))
    cleaned = service.coerce_gpt_sovits_profiles({name: raw_profile})
    if name in cleaned:
        profiles[name] = cleaned[name]
    else:
        profiles.pop(name, None)
    cfg["gpt_sovits_character_profiles"] = profiles
    _save_provider_config(plugin_root, slug, cfg)
    return {"character": _character_row(plugin_root, slug, name)}


def _constraint_store_payload(character_name: str) -> dict[str, Any]:
    store = state.load_character_constraints(character_name)
    versions = []
    for code, label in state.PROMPT_LANGUAGE_OPTIONS:
        vid = state.DEFAULT_PROMPT_VERSION_IDS[code]
        vdata = store.get("versions", {}).get(vid, {})
        versions.append(
            {
                "version_id": vid,
                "language": code,
                "language_label": label,
                "name": str(vdata.get("name", "") or ""),
                "constraint_text": str(vdata.get("constraint_text", "") or ""),
                "source": str(vdata.get("source", "") or ""),
            }
        )
    return {
        "character": character_name,
        "selected_version": str(store.get("selected_version") or ""),
        "versions": versions,
    }


def _action_get_constraints(plugin_root: Path, values: Mapping[str, Any]) -> dict[str, Any]:
    _ = plugin_root
    return _constraint_store_payload(_character_name(values))


def _action_save_constraints(plugin_root: Path, values: Mapping[str, Any]) -> dict[str, Any]:
    _ = plugin_root
    name = _character_name(values)
    vid = str(values.get("version_id") or "").strip()
    if vid not in set(state.DEFAULT_PROMPT_VERSION_IDS.values()):
        raise ValueError(f"未知的模板语言版本：{vid or '(空)'}")
    text = str(values.get("text") or "").strip()
    if not text:
        raise ValueError("约束内容不能为空")
    version_name = str(values.get("name") or "").strip()
    language = state._prompt_language_from_version_id(vid)

    if name == "默认模板":
        state.upsert_constraint_version(
            name, vid, text, name=version_name, source="default", language=language
        )
        synced = state.propagate_default_template(text, language=language)
    else:
        state.upsert_constraint_version(
            name, vid, text, name=version_name, source="manual", language=language
        )
        synced = 0
    state.select_constraint_version(name, vid)
    result = _constraint_store_payload(name)
    result["synced_characters"] = synced
    return result


# ----------------------------------------------------------------------
# 贡献构建
# ----------------------------------------------------------------------


def _make_action(
    plugin_root: Path,
    action_id: str,
    label: str,
    handler,
    *,
    description: str = "",
    variant: str = "ghost",
    confirm: str = "",
    order: float = 100.0,
) -> FrontendConfigAction:
    def run(values: Mapping[str, Any]) -> Mapping[str, Any] | None:
        return handler(plugin_root, values or {})

    return FrontendConfigAction(
        id=action_id,
        label=label,
        description=description,
        variant=variant,
        confirm=confirm,
        order=order,
        run=run,
    )


def build_api_surface(plugin_root: Path) -> FrontendConfigContribution:
    return FrontendConfigContribution(
        page_id=PAGE_ID,
        title=PAGE_TITLE,
        description=(
            "MiniMax / Qwen3 / GPT-SoVITS Cloud 语音合成：每角色音色绑定、"
            "参考音频克隆、语气约束模板。API KEY 在宿主 API 设定页配置。"
        ),
        schema=[],
        load_values=lambda: _load_values(plugin_root),
        save_values=lambda values: _save_values(plugin_root, values or {}),
        order=41.0,
        actions=[
            _make_action(plugin_root, "list_characters", "刷新角色列表", _action_list_characters, order=10),
            _make_action(plugin_root, "bind_voice", "绑定音色", _action_bind_voice, order=20),
            _make_action(plugin_root, "upload_reference", "上传参考音频", _action_upload_reference, order=30),
            _make_action(
                plugin_root,
                "clear_reference",
                "清除参考音频",
                _action_clear_reference,
                variant="danger",
                confirm="确定清除当前角色的本地参考音频？",
                order=40,
            ),
            _make_action(
                plugin_root,
                "clone_voice",
                "克隆音色",
                _action_clone_voice,
                description="上传参考音频到云端创建 voice_id，并下载试听 demo",
                variant="primary",
                order=50,
            ),
            _make_action(plugin_root, "export_voice", "导出 voice_id", _action_export_voice, order=60),
            _make_action(
                plugin_root,
                "import_voice",
                "导入 voice_id",
                _action_import_voice,
                variant="danger",
                confirm="导入会合并 voice_id 记录并可能更新当前绑定，确定继续？",
                order=70,
            ),
            _make_action(
                plugin_root,
                "save_gpt_sovits_profile",
                "保存 GSV Profile",
                _action_save_gpt_sovits_profile,
                order=80,
            ),
            _make_action(plugin_root, "get_constraints", "读取语气约束", _action_get_constraints, order=90),
            _make_action(plugin_root, "save_constraints", "保存语气约束", _action_save_constraints, order=95),
        ],
    )


def build_page(plugin_root: Path) -> FrontendPageContribution:
    _ = plugin_root
    return FrontendPageContribution(
        page_id=PAGE_ID,
        title=PAGE_TITLE,
        entry=str(PACKAGE_ROOT / "frontend" / "index.html"),
        description="Cloud TTS 音色工作台",
        order=41.0,
    )
