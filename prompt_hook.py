from __future__ import annotations

import json
import sys
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Mapping

from plugins.cloud_tts import state


# 保存原始方法的属性名常量，用于 monkey-patch 时记录被替换前的原始函数
_API_SAVE_ORIGINAL_ATTR = "_cloud_tts_original_api_save"
_API_SAVE_HOOK_ATTR = "_cloud_tts_api_save_hook"
_LEGACY_TEMPLATE_ORIGINAL_ATTR = "_cloud_tts_original_generate_chat_template"
_TEMPLATE_RESTORE_ORIGINAL_ATTR = "_cloud_tts_original_restore_last_launch_session"
_TEMPLATE_RESTORE_HOOK_ATTR = "_cloud_tts_restore_session_hook"
_TEMPLATE_GENERATE_ORIGINAL_ATTR = "_cloud_tts_original_on_generate"
_TEMPLATE_GENERATE_HOOK_ATTR = "_cloud_tts_on_generate_hook"
_TEXT_PROCESSOR_ORIGINAL_ATTR = "_cloud_tts_original_remove_parentheses"
_TEXT_PROCESSOR_HOOK_ATTR = "_cloud_tts_remove_parentheses_hook"
_FRONTEND_GENERATE_ORIGINAL_ATTR = "_cloud_tts_original_frontend_generate_template"
_FRONTEND_GENERATE_HOOK_ATTR = "_cloud_tts_frontend_generate_template_hook"
_FRONTEND_LOAD_SESSION_ORIGINAL_ATTR = "_cloud_tts_original_frontend_load_template_session"
_FRONTEND_LOAD_SESSION_HOOK_ATTR = "_cloud_tts_frontend_load_template_session_hook"
_FRONTEND_SAVE_SESSION_ORIGINAL_ATTR = "_cloud_tts_original_frontend_save_template_session"
_FRONTEND_SAVE_SESSION_HOOK_ATTR = "_cloud_tts_frontend_save_template_session_hook"


def _provider_wants_constraint(provider: str | None) -> bool:
    """判断当前 provider 是否需要注入提示词约束 —— 仅 MiniMax 生效，Qwen 不走这套。"""
    if not state.is_cloud_tts_provider(provider):
        return False
    if not state.plugin_manifest_enabled():
        return False
    return state.prompt_constraint_enabled()


def _selected_template_characters(template_tab: Any) -> list[str]:
    """从模板设置页获取当前选中的角色列表。"""
    getter = getattr(template_tab, "_selected_chars", None)
    if not callable(getter):
        return []
    try:
        raw = getter()
    except Exception:
        return []
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]


def _template_tab_voice_language(template_tab: Any) -> str:
    combo = getattr(template_tab, "voice_lang_combo", None)
    getter = getattr(combo, "currentData", None)
    if callable(getter):
        try:
            value = str(getter() or "").strip()
        except Exception:
            value = ""
        if value:
            return value
    return "auto"


def _looks_like_generated_template(text: str, selected_characters: list[str]) -> bool:
    """判断文本是否看起来像是已生成的模板（包含角色名和 speech 字段），避免对空白或未生成模板误注入。"""
    base = state.remove_prompt_constraint_text(text).strip()
    if not base:
        return False
    if all(name in base for name in selected_characters):
        return True
    return "character_name" in base and "speech" in base


def _unpatch_legacy_template_generator() -> None:
    """卸载旧版 TemplateGenerator.generate_chat_template 的 monkey-patch（兼容历史版本）。"""
    try:
        from llm.template_generator import TemplateGenerator
    except Exception:
        return
    current = TemplateGenerator.generate_chat_template
    original: Callable[..., tuple[str, str]] | None = getattr(
        current,
        _LEGACY_TEMPLATE_ORIGINAL_ATTR,
        None,
    )
    if original is not None:
        TemplateGenerator.generate_chat_template = original


def _template_settings_tab_class() -> type | None:
    """获取 TemplateSettingsTab 类，优先从已加载模块取，不行再 import。"""
    module = sys.modules.get("ui.settings_ui.tabs.template_tab")
    cls = getattr(module, "TemplateSettingsTab", None) if module is not None else None
    if cls is not None:
        return cls
    try:
        from ui.settings_ui.tabs.template_tab import TemplateSettingsTab
    except Exception:
        return None
    return TemplateSettingsTab


def _session_path_from_template_tab(template_tab: Any) -> Path | None:
    """从模板 Tab 实例推导出 session 文件的路径，用于同步注入。"""
    ctx = getattr(template_tab, "_ctx", None)
    template_dir_path = getattr(ctx, "template_dir_path", None)
    candidates: list[Path] = []
    if template_dir_path:
        try:
            from ui.settings_ui.services.template_tab_session import template_session_file

            candidates.append(template_session_file(str(template_dir_path)))
        except Exception:
            pass
        try:
            candidates.append(
                Path(template_dir_path).resolve().parent
                / "config"
                / "template_tab_last_launch.json"
            )
        except OSError:
            pass
    try:
        candidates.append(
            state.project_root()
            / "data"
            / "config"
            / "template_tab_last_launch.json"
        )
    except Exception:
        pass
    for path in candidates:
        if path.is_file():
            return path
    return candidates[0] if candidates else None


def _sync_template_session_file(template_tab: Any, provider: str | None) -> None:
    """将注入/移除约束后的模板文本写回 session 文件，保证下次启动也能读到正确状态。"""
    path = _session_path_from_template_tab(template_tab)
    if path is None or not path.is_file():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(payload, dict):
        return
    old = str(payload.get("system_template_text") or "")
    selected = payload.get("selected_characters")
    selected_characters = (
        [str(item).strip() for item in selected if str(item).strip()]
        if isinstance(selected, list)
        else []
    )
    new = _sync_template_text(
        old,
        provider,
        selected_characters,
        payload.get("voice_lang") or payload.get("voiceLanguage") or "auto",
    )
    if new == old:
        return
    payload["system_template_text"] = new
    try:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        return


def _get_character_constraint_text(
    character_name: str,
    voice_language: Any = "auto",
) -> str | None:
    """获取某个角色在指定语音语言下的提示词约束文本。"""
    language = state.normalize_voice_language_code(voice_language)
    if language == "auto":
        language = state.current_system_voice_language()
    return state.get_character_constraint_text(
        character_name,
        language,
    )


def _sync_template_text(
    text: str,
    provider: str | None,
    selected_characters: list[str],
    voice_language: Any = "auto",
) -> str:
    """核心注入逻辑：根据 provider 和开关状态，决定注入还是移除提示词约束块。"""
    old = text or ""
    if not selected_characters:
        return state.remove_prompt_constraint_text(old)

    wants_constraint = _provider_wants_constraint(provider)
    if not wants_constraint:
        # 条件不满足 → 清除已有约束块
        return state.remove_prompt_constraint_text(old)
    if not _looks_like_generated_template(old, selected_characters):
        # 还未生成模板或模板不完整 → 不注入
        return old

    # 收集所有选中角色的约束文本（按当前语音语言或前端即时选择的语言）
    constraint_texts: list[str] = []
    for name in selected_characters:
        ct = _get_character_constraint_text(name, voice_language)
        if ct:
            constraint_texts.append(ct)

    # 合并多角色约束：单角色直接包裹，多角色加通用 guard 后按角色分列
    constraint_text = state.combine_prompt_constraint_texts(constraint_texts)
    if constraint_text:
        # 把约束块注入到 system prompt 最顶部
        return state.add_prompt_constraint_text(old, constraint_text)

    return state.remove_prompt_constraint_text(old)


def _sync_template_tab(template_tab: Any, provider: str | None) -> None:
    """同步模板 Tab 里的 system_template_text：注入或清除约束块。"""
    field = getattr(template_tab, "template_output", None)
    if (
        field is None
        or not hasattr(field, "toPlainText")
        or not hasattr(field, "setPlainText")
    ):
        return

    old = str(field.toPlainText() or "")
    selected_characters = _selected_template_characters(template_tab)
    new = _sync_template_text(
        old,
        provider,
        selected_characters,
        _template_tab_voice_language(template_tab),
    )
    if new != old:
        field.setPlainText(new)


def _frontend_selected_characters(payload: Mapping[str, Any]) -> list[str]:
    raw = payload.get("characters")
    if raw is None:
        raw = payload.get("selectedCharacters")
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]


def _compose_frontend_template_content(scenario: str, system: str) -> str:
    a = (scenario or "").strip()
    b = (system or "").strip()
    if a and b:
        return f"{a}\n\n{b}"
    return a or b


def _patch_frontend_bridge_templates() -> None:
    """Hook React bridge template APIs so Web settings pages receive tone constraints."""
    try:
        from frontend_bridge_core import handler, templates
    except Exception:
        return

    current_generate = getattr(handler, "_generate_template_summary", None)
    if current_generate is None:
        current_generate = getattr(templates, "_generate_template_summary", None)
    if callable(current_generate) and not getattr(
        current_generate,
        _FRONTEND_GENERATE_HOOK_ATTR,
        False,
    ):

        @wraps(current_generate)
        def wrapped_generate(
            bridge_state: Any,
            payload: dict[str, Any],
            *args: Any,
            **kwargs: Any,
        ) -> Any:
            row = current_generate(bridge_state, payload, *args, **kwargs)
            try:
                if not isinstance(row, dict):
                    return row
                selected_characters = _frontend_selected_characters(payload)
                system_text = str(row.get("system") or "")
                synced = _sync_template_text(
                    system_text,
                    state.current_tts_provider(),
                    selected_characters,
                    payload.get("voiceLanguage") or "auto",
                )
                if synced == system_text:
                    return row
                updated = dict(row)
                updated["system"] = synced
                scenario = str(updated.get("scenario") or payload.get("scenario") or "")
                updated["content"] = _compose_frontend_template_content(scenario, synced)
                return updated
            except Exception:
                return row

        setattr(wrapped_generate, _FRONTEND_GENERATE_HOOK_ATTR, True)
        setattr(wrapped_generate, _FRONTEND_GENERATE_ORIGINAL_ATTR, current_generate)
        handler._generate_template_summary = wrapped_generate
        templates._generate_template_summary = wrapped_generate

    current_load = getattr(handler, "_load_template_session_payload", None)
    if current_load is None:
        current_load = getattr(templates, "_load_template_session_payload", None)
    if callable(current_load) and not getattr(
        current_load,
        _FRONTEND_LOAD_SESSION_HOOK_ATTR,
        False,
    ):

        @wraps(current_load)
        def wrapped_load(bridge_state: Any, *args: Any, **kwargs: Any) -> Any:
            row = current_load(bridge_state, *args, **kwargs)
            try:
                if not isinstance(row, dict):
                    return row
                selected_characters = _frontend_selected_characters(row)
                system_text = str(row.get("system") or "")
                synced = _sync_template_text(
                    system_text,
                    state.current_tts_provider(),
                    selected_characters,
                    row.get("voiceLanguage") or "auto",
                )
                if synced == system_text:
                    return row
                updated = dict(row)
                updated["system"] = synced
                return updated
            except Exception:
                return row

        setattr(wrapped_load, _FRONTEND_LOAD_SESSION_HOOK_ATTR, True)
        setattr(wrapped_load, _FRONTEND_LOAD_SESSION_ORIGINAL_ATTR, current_load)
        handler._load_template_session_payload = wrapped_load
        templates._load_template_session_payload = wrapped_load

    current_save = getattr(handler, "_save_template_session_payload", None)
    if current_save is None:
        current_save = getattr(templates, "_save_template_session_payload", None)
    if callable(current_save) and not getattr(
        current_save,
        _FRONTEND_SAVE_SESSION_HOOK_ATTR,
        False,
    ):

        @wraps(current_save)
        def wrapped_save(
            bridge_state: Any,
            payload: dict[str, Any],
            *args: Any,
            **kwargs: Any,
        ) -> Any:
            try:
                selected_characters = _frontend_selected_characters(payload)
                system_text = str(payload.get("system") or "")
                synced = _sync_template_text(
                    system_text,
                    state.current_tts_provider(),
                    selected_characters,
                    payload.get("voiceLanguage") or "auto",
                )
                if synced != system_text:
                    payload = dict(payload)
                    payload["system"] = synced
            except Exception:
                pass
            return current_save(bridge_state, payload, *args, **kwargs)

        setattr(wrapped_save, _FRONTEND_SAVE_SESSION_HOOK_ATTR, True)
        setattr(wrapped_save, _FRONTEND_SAVE_SESSION_ORIGINAL_ATTR, current_save)
        handler._save_template_session_payload = wrapped_save
        templates._save_template_session_payload = wrapped_save


def _sync_open_template_editor(api_tab: Any, provider: str | None) -> None:
    """API 页保存后同步模板编辑器和 session 文件。"""
    window = api_tab.window() if hasattr(api_tab, "window") else None
    template_tab = getattr(window, "_template", None) if window is not None else None
    if template_tab is None:
        return
    _sync_template_tab(template_tab, provider)
    _sync_template_session_file(template_tab, provider)


def _patch_api_save() -> None:
    """Hook 1: monkey-patch API 设置页的 _on_save，保存后自动同步模板中的约束块。"""
    try:
        from ui.settings_ui.tabs.api_tab import ApiSettingsTab
    except Exception:
        return
    current = ApiSettingsTab._on_save
    if getattr(current, _API_SAVE_HOOK_ATTR, False):
        return  # 已经 patch 过，避免重复包裹

    @wraps(current)
    def wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
        result = current(self, *args, **kwargs)  # 先执行原保存逻辑
        try:
            # 只读 API 页面保存后的真实配置状态，避免页面切换或插件页保存触发注入
            _sync_open_template_editor(self, state.current_tts_provider())
        except Exception:
            return result
        return result

    setattr(wrapped, _API_SAVE_HOOK_ATTR, True)
    setattr(wrapped, _API_SAVE_ORIGINAL_ATTR, current)
    ApiSettingsTab._on_save = wrapped  # 替换


def _patch_template_restore() -> None:
    """Hook 2: monkey-patch 模板页的 restore_last_launch_session，恢复会话后同步约束。"""
    TemplateSettingsTab = _template_settings_tab_class()
    if TemplateSettingsTab is None:
        return
    current = TemplateSettingsTab.restore_last_launch_session
    if getattr(current, _TEMPLATE_RESTORE_HOOK_ATTR, False):
        return

    @wraps(current)
    def wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
        result = current(self, *args, **kwargs)  # 先恢复原会话
        try:
            provider = state.current_tts_provider()
            _sync_template_tab(self, provider)
            _sync_template_session_file(self, provider)
        except Exception:
            return result
        return result

    setattr(wrapped, _TEMPLATE_RESTORE_HOOK_ATTR, True)
    setattr(wrapped, _TEMPLATE_RESTORE_ORIGINAL_ATTR, current)
    TemplateSettingsTab.restore_last_launch_session = wrapped


def _patch_template_generate() -> None:
    """Hook 3: monkey-patch 模板页的 _on_generate，生成新模板后自动同步约束。"""
    TemplateSettingsTab = _template_settings_tab_class()
    if TemplateSettingsTab is None:
        return
    current = TemplateSettingsTab._on_generate
    if getattr(current, _TEMPLATE_GENERATE_HOOK_ATTR, False):
        return

    @wraps(current)
    def wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
        result = current(self, *args, **kwargs)  # 先生成模板
        try:
            _sync_template_tab(self, state.current_tts_provider())
        except Exception:
            return result
        return result

    setattr(wrapped, _TEMPLATE_GENERATE_HOOK_ATTR, True)
    setattr(wrapped, _TEMPLATE_GENERATE_ORIGINAL_ATTR, current)
    TemplateSettingsTab._on_generate = wrapped


def _patch_text_processor() -> None:
    """Hook 4: monkey-patch TextProcessor.remove_parentheses，保护 MiniMax 语气标签不被主程序括号清理删掉。

    原理：
    1. protect_tone_tags: 把 (laughs)、(sighs) 等标签替换为 __CLOUD_TTS_TONE_TAG_0__ 占位符
    2. 原 remove_parentheses 正常执行（占位符不含括号，不会被删）
    3. restore_tone_tags: 占位符还原为真实标签
    """
    try:
        from llm.text_processor import TextProcessor
    except Exception:
        return
    current = TextProcessor.remove_parentheses
    if getattr(current, _TEXT_PROCESSOR_HOOK_ATTR, False):
        return

    @wraps(current)
    def wrapped(self: Any, text: str, *args: Any, **kwargs: Any) -> str:
        if state.translate_tone_tag_protection_active():
            # ① 把 19 种 MiniMax 语气标签替换为无括号占位符
            protected, placeholders = state.protect_tone_tags(text)
            # ② 主程序原方法：删除所有 (xxx) 括号内容（占位符不受影响）
            cleaned = current(self, protected, *args, **kwargs)
            # ③ 占位符还原为真实标签
            return state.restore_tone_tags(cleaned, placeholders)
        return current(self, text, *args, **kwargs)

    setattr(wrapped, _TEXT_PROCESSOR_HOOK_ATTR, True)
    setattr(wrapped, _TEXT_PROCESSOR_ORIGINAL_ATTR, current)
    TextProcessor.remove_parentheses = wrapped


def install() -> None:
    """插件启用时安装所有 monkey-patch。按依赖顺序执行。"""
    _unpatch_legacy_template_generator()  # 先清理旧版 hook
    _patch_api_save()                     # Hook 1: API 保存后注入约束
    _patch_template_restore()             # Hook 2: 模板恢复后注入约束
    _patch_template_generate()            # Hook 3: 模板生成后注入约束
    _patch_text_processor()               # Hook 4: 保护语气标签不被括号清理删掉
    _patch_frontend_bridge_templates()    # Hook 5: React 模板页生成/保存时同步约束


def uninstall() -> None:
    """插件禁用时还原所有 monkey-patch，把被替换的方法恢复为原始版本。"""
    _unpatch_legacy_template_generator()
    # 还原 React bridge 模板 API
    try:
        from frontend_bridge_core import handler, templates

        for module in (handler, templates):
            current_generate = getattr(module, "_generate_template_summary", None)
            generate_original: Callable[..., Any] | None = getattr(
                current_generate,
                _FRONTEND_GENERATE_ORIGINAL_ATTR,
                None,
            )
            if generate_original is not None:
                module._generate_template_summary = generate_original

            current_load = getattr(module, "_load_template_session_payload", None)
            load_original: Callable[..., Any] | None = getattr(
                current_load,
                _FRONTEND_LOAD_SESSION_ORIGINAL_ATTR,
                None,
            )
            if load_original is not None:
                module._load_template_session_payload = load_original

            current_save = getattr(module, "_save_template_session_payload", None)
            save_original: Callable[..., Any] | None = getattr(
                current_save,
                _FRONTEND_SAVE_SESSION_ORIGINAL_ATTR,
                None,
            )
            if save_original is not None:
                module._save_template_session_payload = save_original
    except Exception:
        pass
    # 还原 TextProcessor.remove_parentheses
    try:
        from llm.text_processor import TextProcessor

        text_current = TextProcessor.remove_parentheses
        text_original: Callable[..., Any] | None = getattr(
            text_current,
            _TEXT_PROCESSOR_ORIGINAL_ATTR,
            None,
        )
        if text_original is not None:
            TextProcessor.remove_parentheses = text_original
    except Exception:
        pass
    # 还原 ApiSettingsTab._on_save
    try:
        from ui.settings_ui.tabs.api_tab import ApiSettingsTab

        api_current = ApiSettingsTab._on_save
        api_original: Callable[..., Any] | None = getattr(
            api_current,
            _API_SAVE_ORIGINAL_ATTR,
            None,
        )
        if api_original is not None:
            ApiSettingsTab._on_save = api_original
    except Exception:
        pass
    # 还原 TemplateSettingsTab 的两个方法
    try:
        TemplateSettingsTab = _template_settings_tab_class()
        if TemplateSettingsTab is None:
            return
        restore_current = TemplateSettingsTab.restore_last_launch_session
        restore_original: Callable[..., Any] | None = getattr(
            restore_current,
            _TEMPLATE_RESTORE_ORIGINAL_ATTR,
            None,
        )
        if restore_original is not None:
            TemplateSettingsTab.restore_last_launch_session = restore_original
        generate_current = TemplateSettingsTab._on_generate
        generate_original: Callable[..., Any] | None = getattr(
            generate_current,
            _TEMPLATE_GENERATE_ORIGINAL_ATTR,
            None,
        )
        if generate_original is not None:
            TemplateSettingsTab._on_generate = generate_original
    except Exception:
        pass
