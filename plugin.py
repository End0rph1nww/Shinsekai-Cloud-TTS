from __future__ import annotations

from pathlib import Path

from sdk.plugin import PluginBase
from sdk.plugin_host_context import PluginHostContext
from sdk.register import PluginCapabilityRegistry
from sdk.types import (
    FrontendConfigAction,
    FrontendConfigContribution,
    FrontendPageContribution,
    SettingsUIContribution,
)

from plugins.cloud_tts.adapter import CloudTTSAdapter
from plugins.cloud_tts.gpt_sovits_adapter import GPTSoVITSApiAdapter
from plugins.cloud_tts.qwen_adapter import QwenTTSAdapter
from plugins.cloud_tts import host_hook, prompt_hook, state, ui_service


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

        def _load_frontend_values():
            return ui_service.load_values(plugin_root)

        def _save_frontend_values(values):
            ui_service.save_values(plugin_root, values)

        def _frontend_action(action_id: str):
            return lambda values: ui_service.run_action(plugin_root, action_id, values)

        register.register_frontend_config_page(
            FrontendConfigContribution(
                page_id="cloud_tts",
                title="Cloud TTS",
                description="Cloud TTS provider, voice ID and prompt template settings.",
                schema=[],
                load_values=_load_frontend_values,
                save_values=_save_frontend_values,
                order=41.0,
                actions=[
                    FrontendConfigAction(
                        id="switch_provider",
                        label="切换 Provider",
                        run=_frontend_action("switch_provider"),
                        order=10.0,
                    ),
                    FrontendConfigAction(
                        id="import_voice_ids",
                        label="导入 voice_id",
                        run=_frontend_action("import_voice_ids"),
                        order=20.0,
                    ),
                    FrontendConfigAction(
                        id="export_voice_id",
                        label="导出 voice_id",
                        run=_frontend_action("export_voice_id"),
                        order=30.0,
                    ),
                    FrontendConfigAction(
                        id="upload_voice",
                        label="上传复刻",
                        run=_frontend_action("upload_voice"),
                        order=40.0,
                    ),
                    FrontendConfigAction(
                        id="select_template",
                        label="切换模板",
                        run=_frontend_action("select_template"),
                        order=50.0,
                    ),
                    FrontendConfigAction(
                        id="save_template",
                        label="保存模板",
                        run=_frontend_action("save_template"),
                        order=60.0,
                    ),
                    FrontendConfigAction(
                        id="reset_template",
                        label="重置模板",
                        variant="danger",
                        run=_frontend_action("reset_template"),
                        order=70.0,
                    ),
                    FrontendConfigAction(
                        id="create_template",
                        label="新建模板",
                        run=_frontend_action("create_template"),
                        order=80.0,
                    ),
                    FrontendConfigAction(
                        id="delete_template",
                        label="删除模板",
                        variant="danger",
                        run=_frontend_action("delete_template"),
                        order=90.0,
                    ),
                ],
            )
        )
        register.register_frontend_page(
            FrontendPageContribution(
                page_id="cloud_tts",
                title="Cloud TTS",
                entry=str(Path(__file__).resolve().parent / "frontend" / "dist" / "index.html"),
                description="Cloud TTS standalone plugin page.",
                order=41.0,
            )
        )

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

    def shutdown(self) -> None:
        prompt_hook.uninstall()
        if not state.plugin_manifest_enabled():
            host_hook.uninstall()
