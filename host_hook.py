from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from plugins.cloud_tts import state


_PATCHED_ATTR = "_cloud_tts_host_hook"
_ORIGINAL_ATTR = "_cloud_tts_original"
_GPT_SOVITS_PROVIDER_LABEL = "GPT SoVITS Cloud"


def _clear_main_tts_provider_if_needed() -> None:
    changed = state.clear_cloud_tts_provider_if_selected()
    if not changed:
        return
    try:
        from config.config_manager import ConfigManager

        ConfigManager().reload()
    except Exception:
        pass


def _remove_runtime_adapter() -> None:
    try:
        from tts.tts_manager import TTSAdapterFactory

        TTSAdapterFactory._adapters.pop(state.PROVIDER_SLUG, None)
        TTSAdapterFactory._adapters.pop(state.QWEN_PROVIDER_SLUG, None)
        TTSAdapterFactory._adapters.pop(state.GPT_SOVITS_PROVIDER_SLUG, None)
    except Exception:
        pass


def _wrap_manifest_setter(func: Callable[..., bool]) -> Callable[..., bool]:
    if getattr(func, _PATCHED_ATTR, False):
        return func

    @wraps(func)
    def wrapped(entry: str, enabled: bool, *args: Any, **kwargs: Any) -> bool:
        ok = func(entry, enabled, *args, **kwargs)
        if ok and state.is_cloud_tts_entry(entry) and not bool(enabled):
            # 禁用插件后下一次启动不会再注册 cloud-tts；
            # 如果主菜单仍选着它，就清到 none，避免留下失效入口。
            _clear_main_tts_provider_if_needed()
            _remove_runtime_adapter()
        return ok

    setattr(wrapped, _PATCHED_ATTR, True)
    setattr(wrapped, _ORIGINAL_ATTR, func)
    return wrapped


def _patch_manifest_setters() -> None:
    try:
        import core.plugins.plugin_host as plugin_host

        plugin_host.set_plugin_manifest_enabled = _wrap_manifest_setter(
            plugin_host.set_plugin_manifest_enabled
        )
    except Exception:
        pass
    try:
        from ui.settings_ui.tabs import plugin_tab

        plugin_tab.set_plugin_manifest_enabled = _wrap_manifest_setter(
            plugin_tab.set_plugin_manifest_enabled
        )
    except Exception:
        pass


def _with_gpt_sovits_cloud_label(
    prefs: tuple[tuple[str, str], ...],
) -> tuple[tuple[str, str], ...]:
    out = [
        (slug, label)
        for slug, label in prefs
        if str(slug).lower() != state.GPT_SOVITS_PROVIDER_SLUG
    ]
    return ((state.GPT_SOVITS_PROVIDER_SLUG, _GPT_SOVITS_PROVIDER_LABEL), *out)


def _patch_api_tab_provider_label() -> None:
    try:
        from ui.settings_ui.tabs import api_tab

        prefs = getattr(api_tab, "_TTS_LABEL_PREFS", ())
        if isinstance(prefs, tuple):
            api_tab._TTS_LABEL_PREFS = _with_gpt_sovits_cloud_label(prefs)
    except Exception:
        pass


def install() -> None:
    _patch_manifest_setters()
    _patch_api_tab_provider_label()


def uninstall() -> None:
    _clear_main_tts_provider_if_needed()
    _remove_runtime_adapter()
