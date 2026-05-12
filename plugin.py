from __future__ import annotations

from pathlib import Path

from sdk.plugin import PluginBase
from sdk.plugin_host_context import PluginHostContext
from sdk.register import PluginCapabilityRegistry
from sdk.types import SettingsUIContribution

from plugins.minimax_tts.adapter import MiniMaxTTSAdapter
from plugins.minimax_tts import host_hook, prompt_hook, state


class MinimaxTtsPlugin(PluginBase):
    @property
    def plugin_id(self) -> str:
        return state.PLUGIN_ID

    @property
    def plugin_version(self) -> str:
        return state.PLUGIN_VERSION

    @property
    def plugin_name(self) -> str:
        return "MiniMax TTS"

    @property
    def plugin_description(self) -> str:
        return "MiniMax speech-2.x TTS adapter with character reference voice cloning."

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
        # SDK 尚未提供“插件被禁用”的事件；host_hook 只负责禁用时恢复 TTS provider。
        host_hook.install()
        # SDK 也暂未提供模板钩子；prompt_hook 使用幂等 monkey patch 注入 MiniMax 语气约束。
        prompt_hook.install()
        register.register_tts_adapter(state.PROVIDER_SLUG, MiniMaxTTSAdapter)

        def _build_settings(ctx):
            from plugins.minimax_tts.settings import MinimaxTtsSettingsWidget

            _ = ctx
            return MinimaxTtsSettingsWidget(plugin_root)

        register.register_settings_ui(
            SettingsUIContribution(
                page_id="minimax_tts",
                nav_label="MiniMax TTS",
                build=_build_settings,
                order=41.0,
            )
        )

    def shutdown(self) -> None:
        prompt_hook.uninstall()
        if not state.plugin_manifest_enabled():
            host_hook.uninstall()
