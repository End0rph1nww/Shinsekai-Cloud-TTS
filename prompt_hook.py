from __future__ import annotations

import json
import sys
from functools import wraps
from pathlib import Path
from typing import Any, Callable

from plugins.cloud_tts import state


_API_SAVE_ORIGINAL_ATTR = "_cloud_tts_original_api_save"
_API_SAVE_HOOK_ATTR = "_cloud_tts_api_save_hook"
_LEGACY_TEMPLATE_ORIGINAL_ATTR = "_cloud_tts_original_generate_chat_template"
_TEMPLATE_RESTORE_ORIGINAL_ATTR = "_cloud_tts_original_restore_last_launch_session"
_TEMPLATE_RESTORE_HOOK_ATTR = "_cloud_tts_restore_session_hook"
_TEMPLATE_GENERATE_ORIGINAL_ATTR = "_cloud_tts_original_on_generate"
_TEMPLATE_GENERATE_HOOK_ATTR = "_cloud_tts_on_generate_hook"
_TEXT_PROCESSOR_ORIGINAL_ATTR = "_cloud_tts_original_remove_parentheses"
_TEXT_PROCESSOR_HOOK_ATTR = "_cloud_tts_remove_parentheses_hook"


def _provider_wants_constraint(provider: str | None) -> bool:
    if not state.is_cloud_tts_provider(provider):
        return False
    if not state.plugin_manifest_enabled():
        return False
    return state.prompt_constraint_enabled()


def _selected_template_characters(template_tab: Any) -> list[str]:
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


def _looks_like_generated_template(text: str, selected_characters: list[str]) -> bool:
    base = state.remove_prompt_constraint_text(text).strip()
    if not base:
        return False
    if all(name in base for name in selected_characters):
        return True
    return "character_name" in base and "speech" in base


def _unpatch_legacy_template_generator() -> None:
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
    new = _sync_template_text(old, provider, selected_characters)
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


def _get_character_constraint_text(character_name: str) -> str | None:
    """Get runtime-language constraint text for a character."""
    return state.get_character_constraint_text(
        character_name,
        state.current_system_voice_language(),
    )


def _sync_template_text(
    text: str,
    provider: str | None,
    selected_characters: list[str],
) -> str:
    old = text or ""
    if not selected_characters:
        return state.remove_prompt_constraint_text(old)

    wants_constraint = _provider_wants_constraint(provider)
    if not wants_constraint:
        return state.remove_prompt_constraint_text(old)
    if not _looks_like_generated_template(old, selected_characters):
        return old

    # Collect constraint texts from all selected characters.
    # 注入语言跟随主程序当前语音语言；不同角色仍可维护各自的同语种模板。
    constraint_texts: list[str] = []
    for name in selected_characters:
        ct = _get_character_constraint_text(name)
        if ct:
            constraint_texts.append(ct)

    constraint_text = state.combine_prompt_constraint_texts(constraint_texts)
    if constraint_text:
        return state.add_prompt_constraint_text(old, constraint_text)

    return state.remove_prompt_constraint_text(old)


def _sync_template_tab(template_tab: Any, provider: str | None) -> None:
    field = getattr(template_tab, "template_output", None)
    if (
        field is None
        or not hasattr(field, "toPlainText")
        or not hasattr(field, "setPlainText")
    ):
        return

    old = str(field.toPlainText() or "")
    selected_characters = _selected_template_characters(template_tab)
    new = _sync_template_text(old, provider, selected_characters)
    if new != old:
        field.setPlainText(new)


def _sync_open_template_editor(api_tab: Any, provider: str | None) -> None:
    window = api_tab.window() if hasattr(api_tab, "window") else None
    template_tab = getattr(window, "_template", None) if window is not None else None
    if template_tab is None:
        return
    _sync_template_tab(template_tab, provider)
    _sync_template_session_file(template_tab, provider)


def _patch_api_save() -> None:
    try:
        from ui.settings_ui.tabs.api_tab import ApiSettingsTab
    except Exception:
        return
    current = ApiSettingsTab._on_save
    if getattr(current, _API_SAVE_HOOK_ATTR, False):
        return

    @wraps(current)
    def wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
        result = current(self, *args, **kwargs)
        try:
            # 只读 API 页面保存后的真实配置状态，避免页面切换或插件页保存触发注入。
            _sync_open_template_editor(self, state.current_tts_provider())
        except Exception:
            return result
        return result

    setattr(wrapped, _API_SAVE_HOOK_ATTR, True)
    setattr(wrapped, _API_SAVE_ORIGINAL_ATTR, current)
    ApiSettingsTab._on_save = wrapped


def _patch_template_restore() -> None:
    TemplateSettingsTab = _template_settings_tab_class()
    if TemplateSettingsTab is None:
        return
    current = TemplateSettingsTab.restore_last_launch_session
    if getattr(current, _TEMPLATE_RESTORE_HOOK_ATTR, False):
        return

    @wraps(current)
    def wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
        result = current(self, *args, **kwargs)
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
    TemplateSettingsTab = _template_settings_tab_class()
    if TemplateSettingsTab is None:
        return
    current = TemplateSettingsTab._on_generate
    if getattr(current, _TEMPLATE_GENERATE_HOOK_ATTR, False):
        return

    @wraps(current)
    def wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
        result = current(self, *args, **kwargs)
        try:
            _sync_template_tab(self, state.current_tts_provider())
        except Exception:
            return result
        return result

    setattr(wrapped, _TEMPLATE_GENERATE_HOOK_ATTR, True)
    setattr(wrapped, _TEMPLATE_GENERATE_ORIGINAL_ATTR, current)
    TemplateSettingsTab._on_generate = wrapped


def _patch_text_processor() -> None:
    try:
        from llm.text_processor import TextProcessor
    except Exception:
        return
    current = TextProcessor.remove_parentheses
    if getattr(current, _TEXT_PROCESSOR_HOOK_ATTR, False):
        return

    @wraps(current)
    def wrapped(self: Any, text: str, *args: Any, **kwargs: Any) -> str:
        if state.plugin_manifest_enabled() and state.is_cloud_tts_provider(
            state.current_tts_provider()
        ):
            protected, placeholders = state.protect_tone_tags(text)
            cleaned = current(self, protected, *args, **kwargs)
            return state.restore_tone_tags(cleaned, placeholders)
        return current(self, text, *args, **kwargs)

    setattr(wrapped, _TEXT_PROCESSOR_HOOK_ATTR, True)
    setattr(wrapped, _TEXT_PROCESSOR_ORIGINAL_ATTR, current)
    TextProcessor.remove_parentheses = wrapped


def install() -> None:
    _unpatch_legacy_template_generator()
    _patch_api_save()
    _patch_template_restore()
    _patch_template_generate()
    _patch_text_processor()


def uninstall() -> None:
    _unpatch_legacy_template_generator()
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
