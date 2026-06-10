from __future__ import annotations

from pathlib import Path

from sdk.plugin import PluginBase
from sdk.plugin_host_context import PluginHostContext
from sdk.register import PluginCapabilityRegistry
from sdk.types import SettingsUIContribution

from plugins.cloud_tts.adapter import CloudTTSAdapter
from plugins.cloud_tts.gpt_sovits_adapter import GPTSoVITSApiAdapter
from plugins.cloud_tts.qwen_adapter import QwenTTSAdapter
from plugins.cloud_tts import host_hook, prompt_hook, state


class CloudTtsPlugin(PluginBase):
    @property
    def plugin_id(self) -> str:
        return state.PLUGIN_ID

    @property
    def plugin_version(self) -> str:
        return state.PLUGIN_VERSION

    @property
    def plugin_name(self) -> str:
        return "Cloud TTS"

    @property
    def plugin_description(self) -> str:
        return (
            "Cloud TTS adapter for Shinsekai supporting MiniMax, Qwen3 TTS, "
            "and GPT SoVITS Cloud. Provides per-character voice ID binding, "
            "reference-audio voice cloning, server-side reference audio and model paths "
            "for self-hosted GPT-SoVITS, plus practical tone-control prompt helpers."
        )

    @property
    def plugin_author(self) -> str:
        return "End0rph1nww"

    @property
    def priority(self) -> int:
        return 92

    def initialize(
        self,
        register: PluginCapabilityRegistry,
        plugin_root: Path,
        host: PluginHostContext,
    ) -> None:
        # SDK 尚未提供"插件被禁用"的事件；host_hook 只负责禁用时清理失效的 Cloud TTS 选择。
        host_hook.install()
        # SDK 也暂未提供模板钩子；prompt_hook 使用幂等 monkey patch 注入 MiniMax 语气约束。
        prompt_hook.install()
        register.register_tts_adapter(state.PROVIDER_SLUG, CloudTTSAdapter)
        register.register_tts_adapter(state.QWEN_PROVIDER_SLUG, QwenTTSAdapter)
        register.register_tts_adapter(state.GPT_SOVITS_PROVIDER_SLUG, GPTSoVITSApiAdapter)
        def _build_settings(ctx):
            from plugins.cloud_tts.settings import CloudTtsSettingsWidget

            _ = ctx
            return CloudTtsSettingsWidget(plugin_root)

        register.register_settings_ui(
            SettingsUIContribution(
                page_id="cloud_tts",
                nav_label="Cloud TTS",
                build=_build_settings,
                order=41.0,
            )
        )
        _register_react_contributions(register, plugin_root)

    def shutdown(self) -> None:
        prompt_hook.uninstall()
        if not state.plugin_manifest_enabled():
            host_hook.uninstall()


def _register_react_contributions(register: PluginCapabilityRegistry, plugin_root: Path) -> None:
    """注册 PR80+ 宿主的 React 插件页；旧宿主缺少注册方法/SDK 类型时静默跳过。

    frontend_contrib 顶层 import 了新 SDK 类型，因此必须延迟到特性检测之后
    再 import，不得提升到本文件顶部。
    """
    if not hasattr(register, "register_frontend_config_page"):
        return
    try:
        from plugins.cloud_tts.frontend_contrib import build_api_surface, build_page
    except ImportError:
        return
    register.register_frontend_config_page(build_api_surface(plugin_root))
    if hasattr(register, "register_frontend_page"):
        register.register_frontend_page(build_page(plugin_root))
