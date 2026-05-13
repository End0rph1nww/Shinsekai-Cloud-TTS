from __future__ import annotations

import ast
import json
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from plugins.cloud_tts.adapter import (
    CloudTTSAdapter,
    VALID_MODELS,
)
from plugins.cloud_tts import state


LABEL_WIDTH = 134
ROW_HEIGHT = 44
FIELD_HEIGHT = 34


class CloudTtsSettingsWidget(QWidget):
    def __init__(self, plugin_root: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._plugin_root = plugin_root
        self._characters: list[dict[str, Any]] = []
        self._voice_id_map: dict[str, str] = {}
        self._voice_id_versions: dict[str, list[dict[str, Any]]] = {}
        self._local_reference_audio_map: dict[str, str] = {}
        self._reference_audio_language_map: dict[str, str] = {}
        self._current_voice_character_name = ""
        self._current_template_character_name = ""
        self._prompt_constraint_enabled = False
        self._tone_tag_protection_enabled = True
        self._loading_values = True
        # 默认编辑主 API 页当前选中的 provider
        cur = state.current_tts_provider()
        if state.is_qwen_tts_provider(cur):
            self._edit_provider_slug = state.QWEN_PROVIDER_SLUG
        else:
            self._edit_provider_slug = state.PROVIDER_SLUG
        self._build_ui()
        self._load_values()
        self._reload_characters()
        self._loading_values = False

    def showEvent(self, event: Any) -> None:
        """页签切到插件时自动刷新角色列表."""
        super().showEvent(event)
        self._reload_characters()

    def _is_qwen_active(self) -> bool:
        return self._edit_provider_slug == state.QWEN_PROVIDER_SLUG

    def _is_minimax_active(self) -> bool:
        return self._edit_provider_slug == state.PROVIDER_SLUG

    def _current_provider_model_options(self) -> tuple[str, ...]:
        if self._is_qwen_active():
            return state.QWEN_MODELS
        return VALID_MODELS

    def _current_provider_default_model(self) -> str:
        if self._is_qwen_active():
            return state.QWEN_DEFAULT_MODEL
        return "speech-2.8-hd"

    def _provider_extra(self) -> dict[str, Any]:
        """返回当前编辑中 provider 的 api.yaml extra 配置。"""
        if self._is_qwen_active():
            return state.get_qwen_extra()
        return state.get_cloud_extra()

    def _save_provider_extra(self, values: dict[str, Any]) -> None:
        """保存 model / default_voice_id 等到当前 provider 的 api.yaml extra。"""
        if self._is_qwen_active():
            state.set_qwen_extra(values)
        else:
            state.set_cloud_extra(values)

    def _build_ui(self) -> None:
        self._apply_field_style()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        inner = QWidget()
        inner.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        scroll.setWidget(inner)

        root = QVBoxLayout(inner)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(14)

        root.addWidget(self._guide_block())

        # Provider 选择器，独立于主 API 页，方便分别配置两个模型
        provider_box, provider_lay = self._section("TTS Provider 配置")
        self.edit_provider = self._combo()
        self.edit_provider.addItem("MiniMax TTS", state.PROVIDER_SLUG)
        self.edit_provider.addItem("Qwen3 TTS", state.QWEN_PROVIDER_SLUG)
        self.edit_provider.currentIndexChanged.connect(self._on_edit_provider_changed)
        provider_lay.addWidget(self._row("当前编辑", self.edit_provider))
        root.addWidget(provider_box)

        api_box, api_lay = self._section("模型与兜底声线")
        self.model = self._combo()
        self._refresh_model_options()
        self.model.currentIndexChanged.connect(lambda _index: self._on_model_changed())
        api_lay.addWidget(self._row("模型", self.model))

        self.default_voice_id = self._voice_combo()
        self.default_voice_id.lineEdit().setPlaceholderText("未匹配角色时使用的兜底 voice_id")
        self.default_voice_id.currentIndexChanged.connect(
            lambda _index: self._on_default_voice_changed()
        )
        self.default_voice_id.lineEdit().editingFinished.connect(
            self._on_default_voice_changed
        )
        api_lay.addWidget(self._row("默认 voice_id", self.default_voice_id))

        # Qwen 特有：合成语言
        self.qwen_language_type = self._combo()
        for code, label in state.QWEN_LANGUAGE_TYPES:
            self.qwen_language_type.addItem(label, code)
        self.qwen_language_type.currentIndexChanged.connect(
            lambda _index: self._on_qwen_language_type_changed()
        )
        self.qwen_language_type_row = self._row("合成语言", self.qwen_language_type)
        api_lay.addWidget(self.qwen_language_type_row)

        root.addWidget(api_box)

        self.switch_box, switch_lay = self._section("功能开关")
        switch_lay.addWidget(
            self._feature_label(
                "⭐ 提示词约束：推荐开启，体验完整效果；插件会按主程序语音语言注入对应角色模板。"
            )
        )
        self.prompt_constraint_btn = QPushButton()
        self.prompt_constraint_btn.setFixedHeight(FIELD_HEIGHT)
        self.prompt_constraint_btn.clicked.connect(self._toggle_prompt_constraint)
        switch_lay.addWidget(self._row("提示词约束", self.prompt_constraint_btn))
        switch_lay.addWidget(
            self._feature_label(
                "⭐ 语气标签保护：推荐开启。主程序会清理括号内容；开启后插件会接管 translate 的语气标签保护，避免 (laughs)、(sighs) 等标签在合成前被删掉。"
            )
        )
        self.tone_tag_protection_btn = QPushButton()
        self.tone_tag_protection_btn.setFixedHeight(FIELD_HEIGHT)
        self.tone_tag_protection_btn.clicked.connect(self._toggle_tone_tag_protection)
        switch_lay.addWidget(self._row("语气标签保护", self.tone_tag_protection_btn))
        switch_lay.addWidget(
            self._feature_label(
                "⭐ TTS 分句：推荐到主菜单 API 页关闭「启用分句合成语音」，避免云端语音被切碎。"
            )
        )
        root.addWidget(self.switch_box)

        voice_box, voice_lay = self._section("角色语音配置")

        role_line = QWidget()
        role_line.setFixedHeight(ROW_HEIGHT)
        role_lay = QHBoxLayout(role_line)
        role_lay.setContentsMargins(0, 4, 0, 4)
        role_lay.setSpacing(8)
        self.character_combo = self._combo()
        self.refresh_roles = QPushButton("刷新角色")
        self.refresh_roles.setFixedHeight(FIELD_HEIGHT)
        self.refresh_roles.clicked.connect(self._reload_characters)
        self.open_card_ref_btn = QPushButton("打开角色卡音频位置")
        self.open_card_ref_btn.setFixedHeight(FIELD_HEIGHT)
        self.open_card_ref_btn.clicked.connect(self._open_current_card_reference_audio)
        role_lay.addWidget(self.character_combo, stretch=1)
        role_lay.addWidget(self.refresh_roles)
        role_lay.addWidget(self.open_card_ref_btn)
        voice_lay.addWidget(role_line)

        local_ref_field = QWidget()
        local_ref_lay = QHBoxLayout(local_ref_field)
        local_ref_lay.setContentsMargins(0, 0, 0, 0)
        local_ref_lay.setSpacing(8)
        self.local_ref_path = self._line_edit("")
        self.local_ref_path.setPlaceholderText("可选：不受主程序时长限制的本地参考音频")
        self.local_ref_path.editingFinished.connect(self._on_local_reference_changed)
        self.choose_local_ref_btn = QPushButton("选择")
        self.choose_local_ref_btn.setFixedHeight(FIELD_HEIGHT)
        self.choose_local_ref_btn.clicked.connect(self._choose_local_reference_audio)
        self.clear_local_ref_btn = QPushButton("清除")
        self.clear_local_ref_btn.setFixedHeight(FIELD_HEIGHT)
        self.clear_local_ref_btn.clicked.connect(self._clear_local_reference_audio)
        local_ref_lay.addWidget(self.local_ref_path, stretch=1)
        local_ref_lay.addWidget(self.choose_local_ref_btn)
        local_ref_lay.addWidget(self.clear_local_ref_btn)
        voice_lay.addWidget(self._row("本地参考音频", local_ref_field))

        self.reference_audio_language = self._combo()
        reference_language_options = (
            ("auto", "自动识别 / auto"),
            ("zh", "中文"),
            ("ja", "日语"),
            ("yue", "粤语"),
            ("en", "英语"),
        )
        for code, label in reference_language_options:
            self.reference_audio_language.addItem(label, code)
        self.reference_audio_language.currentIndexChanged.connect(
            lambda _index: self._on_reference_audio_language_changed()
        )
        voice_lay.addWidget(self._row("参考音频语言", self.reference_audio_language))

        self.character_voice_id = self._voice_combo()
        self.character_voice_id.lineEdit().setPlaceholderText("该角色专用 voice_id")
        self.character_voice_id.currentIndexChanged.connect(
            lambda _index: self._on_character_voice_changed()
        )
        self.character_voice_id.lineEdit().editingFinished.connect(
            self._on_character_voice_changed
        )
        voice_lay.addWidget(self._row("角色 voice_id", self.character_voice_id))

        self.upload_btn = QPushButton("上传本地参考音频并生成 voice_id")
        self.upload_btn.setFixedHeight(FIELD_HEIGHT)
        self.upload_btn.clicked.connect(self._upload_selected_character)

        self.import_voice_btn = QPushButton("导入 voice_id JSON")
        self.import_voice_btn.setFixedHeight(FIELD_HEIGHT)
        self.import_voice_btn.clicked.connect(self._import_voice_ids)

        voice_actions = QWidget()
        voice_actions.setFixedHeight(ROW_HEIGHT)
        voice_actions_lay = QHBoxLayout(voice_actions)
        voice_actions_lay.setContentsMargins(0, 4, 0, 4)
        voice_actions_lay.setSpacing(8)
        voice_actions_lay.addWidget(self.upload_btn, stretch=1)
        voice_actions_lay.addWidget(self.import_voice_btn)
        voice_lay.addWidget(voice_actions)

        root.addWidget(voice_box)

        self.template_box, template_lay = self._section("提示词模板")
        self.template_character_combo = self._combo()
        self.template_character_combo.setMinimumContentsLength(20)
        self.template_character_combo.currentIndexChanged.connect(self._on_template_character_changed)
        template_lay.addWidget(self._row("角色", self.template_character_combo))

        self.constraint_version_combo = self._combo()
        self.constraint_version_combo.setMinimumContentsLength(20)
        self.constraint_version_combo.currentIndexChanged.connect(self._on_constraint_version_changed)
        template_lay.addWidget(self._row("模板语言", self.constraint_version_combo))

        self.version_name_edit = self._line_edit("")
        self.version_name_edit.setPlaceholderText("版本名称，如「默认模板」「优化版」")
        self.version_name_row = self._row("版本名称", self.version_name_edit)
        self.version_name_row.setVisible(False)
        template_lay.addWidget(self.version_name_row)

        self.constraint_text_edit = QTextEdit()
        self.constraint_text_edit.setMinimumHeight(200)
        template_lay.addWidget(self.constraint_text_edit)

        template_actions = QWidget()
        template_actions.setFixedHeight(ROW_HEIGHT)
        template_actions_lay = QHBoxLayout(template_actions)
        template_actions_lay.setContentsMargins(0, 4, 0, 4)
        template_actions_lay.setSpacing(8)
        self.new_version_btn = QPushButton("新建版本")
        self.new_version_btn.setFixedHeight(FIELD_HEIGHT)
        self.new_version_btn.clicked.connect(self._new_constraint_version)
        self.save_version_btn = QPushButton("保存当前版本")
        self.save_version_btn.setFixedHeight(FIELD_HEIGHT)
        self.save_version_btn.clicked.connect(self._save_constraint_version)
        self.delete_version_btn = QPushButton("删除当前版本")
        self.delete_version_btn.setFixedHeight(FIELD_HEIGHT)
        self.delete_version_btn.clicked.connect(self._delete_constraint_version)
        self.reset_default_btn = QPushButton("重置默认模板")
        self.reset_default_btn.setFixedHeight(FIELD_HEIGHT)
        self.reset_default_btn.clicked.connect(self._reset_default_template)
        self.new_version_btn.setVisible(False)
        self.delete_version_btn.setVisible(False)
        template_actions_lay.addWidget(self.save_version_btn)
        template_actions_lay.addWidget(self.reset_default_btn)
        template_lay.addWidget(template_actions)
        root.addWidget(self.template_box)

        root.addStretch(1)

        outer.addWidget(scroll, stretch=1)

        foot = QFrame()
        foot.setFrameShape(QFrame.Shape.NoFrame)
        foot_lay = QVBoxLayout(foot)
        foot_lay.setContentsMargins(0, 0, 0, 0)
        foot_lay.setSpacing(0)
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        foot_lay.addWidget(sep)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setContentsMargins(12, 8, 12, 8)
        foot_lay.addWidget(self.status)
        outer.addWidget(foot)

        self.character_combo.currentIndexChanged.connect(self._on_character_changed)

    def _section(self, title: str) -> tuple[QGroupBox, QVBoxLayout]:
        box = QGroupBox(title)
        lay = QVBoxLayout(box)
        lay.setContentsMargins(10, 18, 10, 10)
        lay.setSpacing(6)
        return box, lay

    def _guide_block(self) -> QWidget:
        block = QWidget()
        lay = QVBoxLayout(block)
        lay.setContentsMargins(0, 0, 0, 2)
        lay.setSpacing(6)

        title = QLabel("Cloud TTS 使用提示")
        title.setStyleSheet("color: #b88cff; font-weight: 600;")
        lay.addWidget(title)

        body = QLabel(
            "<b>1. 前置条件：</b>先在首页 / 主菜单 API 设置页选择 MiniMax TTS 或 Qwen3 TTS，填写对应 API KEY 和 BASE URL 并保存。"
            "本页不重复保存连接凭证。<br/><br/>"
            "<b>2. MiniMax 模式：</b>建议开启<b>提示词约束</b>和<b>语气标签保护</b>，让 translate 字段的语气标签不被打断。"
            "TTS 分段功能已由主程序接管，请在 API 设置页配置「TTS 分句发送」。<br/><br/>"
            "<b>3. Qwen3 TTS 模式：</b>通过<b>声音复刻</b>上传参考音频创建自定义音色，"
            "合成和复刻均使用 qwen3-tts-vc 模型。支持多语种合成。<br/><br/>"
            "<b>4. 角色 voice_id：</b>选择角色后在下拉框中选择或粘贴 voice_id，支持多版本历史管理。"
            "也可选择本地参考音频后上传克隆/复刻 voice_id；"
            "结果缓存在 <code>data/plugins/com.shinsekai.cloud_tts/voices/</code>。<br/><br/>"
            "<b>5. 提示词模板（仅 MiniMax）：</b>「默认模板」内置中文、日语、粤语、英语四套母版；每个角色首次打开也会自动生成四套同语种默认提示词。"
        )
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(body)
        return block

    def _row(self, label: str, field: QWidget) -> QWidget:
        row = QWidget()
        row.setFixedHeight(ROW_HEIGHT)
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 4, 0, 4)
        lay.setSpacing(12)
        lab = QLabel(label)
        lab.setFixedWidth(LABEL_WIDTH)
        lab.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(lab)
        lay.addWidget(field, stretch=1)
        return row

    def _feature_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setStyleSheet("color: #cfcfcf; font-size: 12px; font-weight: 500;")
        return label

    def _prepare_field(self, field: QWidget) -> QWidget:
        field.setFixedHeight(FIELD_HEIGHT)
        field.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return field

    def _line_edit(self, text: str = "") -> QLineEdit:
        field = QLineEdit(text)
        self._prepare_field(field)
        return field

    def _combo(self) -> QComboBox:
        combo = QComboBox()
        combo.setMinimumContentsLength(12)
        combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self._prepare_field(combo)
        return combo

    def _voice_combo(self) -> QComboBox:
        combo = self._combo()
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        return combo

    def _apply_field_style(self) -> None:
        self.setStyleSheet("")

    def _valid_choice(self, value: Any, valid: tuple[str, ...], default: str) -> str:
        item = str(value or "").strip()
        if item in valid:
            return item
        lowered = item.lower()
        for candidate in valid:
            if candidate.lower() == lowered:
                return candidate
        return default

    def _as_bool(self, value: Any, default: bool) -> bool:
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

    def _refresh_prompt_constraint_button(self) -> None:
        if not hasattr(self, "prompt_constraint_btn"):
            return
        if self._prompt_constraint_enabled:
            self.prompt_constraint_btn.setText("已开启，点击关闭")
            self.prompt_constraint_btn.setStyleSheet(
                "QPushButton { color: #d7ffd7; border: 1px solid #3a7c46; }"
            )
        else:
            self.prompt_constraint_btn.setText("已关闭，点击开启")
            self.prompt_constraint_btn.setStyleSheet(
                "QPushButton { color: #cfcfcf; border: 1px solid #555; }"
            )

    def _refresh_tone_tag_protection_button(self) -> None:
        if not hasattr(self, "tone_tag_protection_btn"):
            return
        if self._tone_tag_protection_enabled:
            self.tone_tag_protection_btn.setText("已开启，点击关闭")
            self.tone_tag_protection_btn.setStyleSheet(
                "QPushButton { color: #d7ffd7; border: 1px solid #3a7c46; }"
            )
        else:
            self.tone_tag_protection_btn.setText("已关闭，点击开启")
            self.tone_tag_protection_btn.setStyleSheet(
                "QPushButton { color: #cfcfcf; border: 1px solid #555; }"
            )

    def _toggle_prompt_constraint(self) -> None:
        if self._loading_values:
            return
        self._prompt_constraint_enabled = not self._prompt_constraint_enabled
        self._refresh_prompt_constraint_button()
        state_text = "开启" if self._prompt_constraint_enabled else "关闭"
        self._save(f"提示词约束已{state_text}。")

    def _toggle_tone_tag_protection(self) -> None:
        if self._loading_values:
            return
        self._tone_tag_protection_enabled = not self._tone_tag_protection_enabled
        self._refresh_tone_tag_protection_button()
        state_text = "开启" if self._tone_tag_protection_enabled else "关闭"
        self._save(f"语气标签保护已{state_text}。")

    def _update_provider_visibility(self) -> None:
        """根据当前选中的 TTS provider 切换可见的 UI 区块。"""
        is_qwen = self._is_qwen_active()
        is_minimax = self._is_minimax_active()
        # Qwen 特有控件
        self.qwen_language_type_row.setVisible(is_qwen)
        # MiniMax 特有区块
        self.switch_box.setVisible(is_minimax)
        self.template_box.setVisible(is_minimax)

    def _on_edit_provider_changed(self) -> None:
        """用户手动切换插件页的 provider 编辑视图。"""
        if self._loading_values:
            return
        new_slug = self.edit_provider.currentData()
        if not new_slug or new_slug == self._edit_provider_slug:
            return
        # 保存当前编辑的 model/default_voice_id/voice 数据到旧 provider
        self._store_current_character_voice_id()
        self._save_provider_extra({
            "model": str(self.model.currentData() or ""),
            "default_voice_id": self._combo_voice_id(self.default_voice_id),
            "language_type": str(self.qwen_language_type.currentData() or "Chinese") if self._is_qwen_active() else "",
        })
        state.save_voice_config_to_files(
            dict(self._voice_id_map),
            dict(self._voice_id_versions),
            provider_slug=self._edit_provider_slug,
        )
        # 切换到新 provider
        self._edit_provider_slug = new_slug
        # 重新加载 voice 数据
        cfg = state.load_plugin_config(self._plugin_root, self._edit_provider_slug)
        self._voice_id_map = self._coerce_voice_id_map(cfg.get("voice_id_map"))
        self._voice_id_versions = self._coerce_voice_id_versions(cfg.get("voice_id_versions"))
        # 刷新模型列表并加载新 provider 的配置
        self._refresh_model_options()
        extra = self._provider_extra()
        model_value = extra.get("model", self._current_provider_default_model())
        self._set_combo(self.model, model_value)
        default_vid = extra.get("default_voice_id", "")
        self._refresh_default_voice_options(default_vid or "")
        self._set_voice_combo_value(self.default_voice_id, default_vid)
        lang = extra.get("language_type", "Chinese")
        self._set_combo(self.qwen_language_type, lang)
        self._update_provider_visibility()
        # 刷新当前角色的 voice 选项
        char = self.character_combo.currentText().strip()
        if char:
            self._refresh_character_voice_options(char)
        provider_label = "Qwen3 TTS" if self._is_qwen_active() else "MiniMax TTS"
        self.status.setText(f"已切换到 {provider_label} 配置视图。")

    def _refresh_model_options(self) -> None:
        """根据当前选中的 TTS provider 刷新模型下拉框。"""
        self.model.blockSignals(True)
        self.model.clear()
        for item in self._current_provider_model_options():
            self.model.addItem(item, item)
        self.model.blockSignals(False)

    def _on_qwen_language_type_changed(self) -> None:
        if self._loading_values:
            return
        lang = self.qwen_language_type.currentData()
        self._save(f"Qwen 合成语言已切换为 {lang or 'auto'}。")

    def _on_model_changed(self) -> None:
        if self._loading_values:
            return
        self._save(f"模型已切换为 {self.model.currentData()}。")

    def _on_default_voice_changed(self) -> None:
        if self._loading_values:
            return
        self._save("默认 voice_id 已更新。")

    def _on_character_voice_changed(self) -> None:
        if self._loading_values:
            return
        self._store_current_character_voice_id()
        self._save("当前角色 voice_id 已更新。")

    def _on_local_reference_changed(self) -> None:
        if self._loading_values:
            return
        self._store_current_local_reference_audio()
        self._save("当前角色本地参考音频已更新。")

    def _on_reference_audio_language_changed(self) -> None:
        if self._loading_values:
            return
        self._store_current_reference_audio_language()
        self._save("当前角色参考音频语言已更新。")

    def _load_values(self) -> None:
        state.migrate_package_config_to_data_root()
        state.migrate_api_extra_to_plugin_state(self._plugin_root)
        cfg = state.load_plugin_config(self._plugin_root, self._edit_provider_slug)
        # 根据编辑的 provider 读取 api.yaml 中的对应 extra
        extra = self._provider_extra()
        values = dict(
            {
                k: v
                for k, v in cfg.items()
                if v not in (None, "", {}, [])
            }
        )
        # 官方 adapter 配置从 api.yaml 读取；旧版插件状态只作为兼容兜底。
        values.update(extra)
        # 设置 provider 选择器（不触发信号，因为 _loading_values=True）
        self._set_combo(self.edit_provider, self._edit_provider_slug)
        self._set_combo(
            self.model,
            self._valid_choice(
                values.get("model"),
                self._current_provider_model_options(),
                self._current_provider_default_model(),
            ),
        )
        self._voice_id_map = self._coerce_voice_id_map(values.get("voice_id_map"))
        self._voice_id_versions = self._coerce_voice_id_versions(values.get("voice_id_versions"))
        self._local_reference_audio_map = self._coerce_path_map(
            values.get("local_reference_audio_map")
        )
        self._reference_audio_language_map = state.coerce_voice_language_map(
            values.get("reference_audio_language_map")
        )
        self._ensure_versions_from_selected_map()
        self._refresh_default_voice_options(str(values.get("default_voice_id") or ""))
        self._prompt_constraint_enabled = self._as_bool(
            values.get("auto_prompt_constraint"),
            False,
        )
        self._tone_tag_protection_enabled = self._as_bool(
            values.get("protect_translate_tone_tags"),
            True,
        )
        self._refresh_prompt_constraint_button()
        self._refresh_tone_tag_protection_button()
        # Qwen 特有字段
        qwen_lang = str(values.get("qwen_language_type") or values.get("language_type") or "Chinese")
        self._set_combo(self.qwen_language_type, qwen_lang)
        self._update_provider_visibility()

    def _set_combo(self, combo: QComboBox, value: str) -> None:
        idx = combo.findData(value)
        if idx < 0:
            idx = combo.findText(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def _set_voice_combo_value(self, combo: QComboBox, value: str) -> None:
        voice_id = (value or "").strip()
        idx = combo.findData(voice_id)
        if idx >= 0:
            combo.setCurrentIndex(idx)
            return
        if combo.isEditable():
            combo.setEditText(voice_id)

    def _combo_voice_id(self, combo: QComboBox) -> str:
        text = combo.currentText().strip()
        if combo.isEditable() and combo.currentIndex() >= 0:
            if combo.itemText(combo.currentIndex()) != text:
                return text
        data = combo.currentData()
        if isinstance(data, str) and data.strip():
            return data.strip()
        for i in range(combo.count()):
            if combo.itemText(i) == text and not str(combo.itemData(i) or "").strip():
                return ""
        return text

    def _all_voice_options(self) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        seen: set[str] = set()
        for name, versions in self._voice_id_versions.items():
            clean_name = str(name or "").strip()
            for idx, rec in enumerate(versions, start=1):
                voice_id = str(rec.get("voice_id") or "").strip()
                if not voice_id or voice_id in seen:
                    continue
                label = f"{clean_name} / 版本 {idx} / {voice_id}"
                out.append((label, voice_id))
                seen.add(voice_id)
        for name, voice_id in self._voice_id_map.items():
            if voice_id and voice_id not in seen:
                out.append((f"{name} / 当前 / {voice_id}", voice_id))
                seen.add(voice_id)
        return out

    def _refresh_default_voice_options(self, selected: str | None = None) -> None:
        current = self._combo_voice_id(self.default_voice_id) if selected is None else selected
        self.default_voice_id.blockSignals(True)
        self.default_voice_id.clear()
        self.default_voice_id.addItem("不固定", "")
        for label, voice_id in self._all_voice_options():
            self.default_voice_id.addItem(label, voice_id)
        self._set_voice_combo_value(self.default_voice_id, current or "")
        self.default_voice_id.blockSignals(False)

    def _refresh_character_voice_options(self, character_name: str) -> None:
        selected = self._voice_id_map.get(character_name, "")
        self.character_voice_id.blockSignals(True)
        self.character_voice_id.clear()
        self.character_voice_id.addItem("使用默认保底 voice_id", "")
        versions = self._voice_id_versions.get(character_name, [])
        for idx, rec in enumerate(versions, start=1):
            voice_id = str(rec.get("voice_id") or "").strip()
            if voice_id:
                self.character_voice_id.addItem(f"版本 {idx} / {voice_id}", voice_id)
        if selected and self.character_voice_id.findData(selected) < 0:
            self.character_voice_id.addItem(f"手动 / {selected}", selected)
        self._set_voice_combo_value(self.character_voice_id, selected)
        self.character_voice_id.blockSignals(False)

    def _refresh_reference_audio_language(self, character_name: str) -> None:
        if not hasattr(self, "reference_audio_language"):
            return
        code = self._reference_audio_language_map.get(character_name, "auto")
        self.reference_audio_language.blockSignals(True)
        self._set_combo(
            self.reference_audio_language,
            state.normalize_voice_language_code(code),
        )
        self.reference_audio_language.blockSignals(False)

    def _reload_characters(self) -> None:
        self._store_current_local_reference_audio()
        self._store_current_reference_audio_language()
        current = self.character_combo.currentText()
        self._characters = state.load_characters()
        self.character_combo.blockSignals(True)
        self.character_combo.clear()
        for item in self._characters:
            name = str(item.get("name") or "").strip()
            if name:
                self.character_combo.addItem(name, name)
        if current:
            idx = self.character_combo.findText(current)
            if idx >= 0:
                self.character_combo.setCurrentIndex(idx)
        self.character_combo.blockSignals(False)
        self._current_voice_character_name = self.character_combo.currentText().strip()
        self._sync_reference_label()
        self._refresh_template_characters()

    def _selected_character(self) -> dict[str, Any] | None:
        name = self.character_combo.currentText()
        return state.find_character(name)

    def _sync_reference_label(self) -> None:
        char = self._selected_character()
        if not char:
            self.local_ref_path.setText("")
            return
        name = str(char.get("name") or "").strip()
        self.local_ref_path.blockSignals(True)
        self.local_ref_path.setText(self._local_reference_audio_map.get(name, ""))
        self.local_ref_path.blockSignals(False)
        self._refresh_character_voice_options(name)
        self._refresh_reference_audio_language(name)

    def _on_character_changed(self, _index: int) -> None:
        self._store_local_reference_audio_for_name(self._current_voice_character_name)
        self._store_reference_audio_language_for_name(self._current_voice_character_name)
        self._current_voice_character_name = self.character_combo.currentText().strip()
        self._sync_reference_label()

    def _open_current_card_reference_audio(self) -> None:
        char = self._selected_character()
        if not char:
            QMessageBox.warning(self, "Cloud TTS", "请先选择角色。")
            return
        path = state.resolve_reference_audio(char)
        if not path:
            QMessageBox.information(self, "Cloud TTS", "当前角色卡没有 refer_audio_path。")
            return
        if not path.exists():
            QMessageBox.warning(self, "Cloud TTS", f"角色卡音频路径不存在：\n{path}")
            return
        target = path if path.is_dir() else path.parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    def _choose_local_reference_audio(self) -> None:
        char = self._selected_character()
        if not char:
            QMessageBox.warning(self, "Cloud TTS", "请先选择角色。")
            return
        start_path = self.local_ref_path.text().strip()
        if not start_path:
            ref_path = state.resolve_reference_audio(char)
            start_path = str(ref_path) if ref_path else str(state.project_root())
        start = state.project_path(start_path)
        start_dir = start if start.is_dir() else start.parent
        path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "选择本地参考音频",
            str(start_dir),
            "Audio Files (*.wav *.mp3 *.m4a *.flac *.ogg *.aac);;All Files (*)",
        )
        if not path:
            return
        self.local_ref_path.setText(str(Path(path)))
        self._store_current_local_reference_audio()
        self._save("已选择并保存本地参考音频。")

    def _clear_local_reference_audio(self) -> None:
        self.local_ref_path.clear()
        self._store_current_local_reference_audio()
        self._save("已清除当前角色的本地参考音频。")

    def _store_current_local_reference_audio(self) -> None:
        self._store_local_reference_audio_for_name(self.character_combo.currentText().strip())

    def _store_local_reference_audio_for_name(self, character_name: str) -> None:
        name = (character_name or "").strip()
        if not name or not hasattr(self, "local_ref_path"):
            return
        path = self.local_ref_path.text().strip()
        if path:
            self._local_reference_audio_map[name] = path
        else:
            self._local_reference_audio_map.pop(name, None)

    def _store_current_reference_audio_language(self) -> None:
        self._store_reference_audio_language_for_name(self.character_combo.currentText().strip())

    def _store_reference_audio_language_for_name(self, character_name: str) -> None:
        name = (character_name or "").strip()
        if not name or not hasattr(self, "reference_audio_language"):
            return
        code = state.normalize_voice_language_code(
            self.reference_audio_language.currentData()
        )
        if code == "auto":
            self._reference_audio_language_map.pop(name, None)
        else:
            self._reference_audio_language_map[name] = code

    def _reference_audio_language_for_name(self, character_name: str) -> str:
        name = (character_name or "").strip()
        if not name:
            return "auto"
        return state.normalize_voice_language_code(
            self._reference_audio_language_map.get(name, "auto")
        )

    def _reference_audio_for_upload(self, char: dict[str, Any]) -> tuple[Path | None, str]:
        name = str(char.get("name") or "").strip()
        local_path = self._local_reference_audio_map.get(name, "").strip()
        if local_path:
            return state.project_path(local_path).resolve(), "本地参考音频"
        return None, "本地参考音频"

    def _store_current_character_voice_id(self) -> None:
        name = self.character_combo.currentText().strip()
        if not name:
            return
        voice_id = self._combo_voice_id(self.character_voice_id)
        if voice_id:
            self._voice_id_map[name] = voice_id
            self._ensure_voice_version(name, voice_id, source="manual")
        else:
            self._voice_id_map.pop(name, None)
        self._refresh_default_voice_options()

    def _coerce_voice_id_map(self, value: Any) -> dict[str, str]:
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except Exception:
                try:
                    value = ast.literal_eval(value)
                except Exception:
                    value = {}
        if not isinstance(value, dict):
            return {}
        out: dict[str, str] = {}
        for key, item in value.items():
            name = str(key or "").strip()
            vid = str(item or "").strip()
            if name and vid:
                out[name] = vid
        return out

    def _coerce_path_map(self, value: Any) -> dict[str, str]:
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except Exception:
                try:
                    value = ast.literal_eval(value)
                except Exception:
                    value = {}
        if not isinstance(value, dict):
            return {}
        out: dict[str, str] = {}
        for key, item in value.items():
            name = str(key or "").strip()
            path = str(item or "").strip()
            if name and path:
                out[name] = path
        return out

    def _coerce_voice_id_versions(self, value: Any) -> dict[str, list[dict[str, Any]]]:
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except Exception:
                try:
                    value = ast.literal_eval(value)
                except Exception:
                    value = {}
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

    def _ensure_voice_version(
        self,
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
        versions = self._voice_id_versions.setdefault(name, [])
        if any(str(item.get("voice_id") or "").strip() == vid for item in versions):
            return
        rec: dict[str, Any] = {
            "voice_id": vid,
            "source": source,
            "created_at": int(time.time()),
        }
        rec.update({k: v for k, v in extra.items() if v not in (None, "")})
        versions.append(rec)

    def _ensure_versions_from_selected_map(self) -> None:
        for name, voice_id in list(self._voice_id_map.items()):
            self._ensure_voice_version(name, voice_id, source="selected")

    def _values(self) -> dict[str, Any]:
        self._store_current_character_voice_id()
        self._store_current_local_reference_audio()
        self._store_current_reference_audio_language()
        default_model = self._current_provider_default_model()
        result = {
            "model": str(self.model.currentData() or default_model),
            "default_voice_id": self._combo_voice_id(self.default_voice_id),
            "voice_id_map": dict(self._voice_id_map),
            "voice_id_versions": dict(self._voice_id_versions),
            "local_reference_audio_map": dict(self._local_reference_audio_map),
            "reference_audio_language_map": dict(self._reference_audio_language_map),
            "auto_prompt_constraint": self._prompt_constraint_enabled,
            "protect_translate_tone_tags": self._tone_tag_protection_enabled,
        }
        if self._is_qwen_active():
            result["qwen_language_type"] = str(self.qwen_language_type.currentData() or "Chinese")
        return result

    def _adapter(self):
        """返回当前 provider 对应的 adapter 实例，用于上传/克隆操作。"""
        values = self._values()
        if self._is_qwen_active():
            from plugins.cloud_tts.qwen_adapter import QwenTTSAdapter
            values.update(state.get_qwen_extra())
            values["use_runtime_config"] = False
            return QwenTTSAdapter(**values)
        values.update(state.get_cloud_extra())
        values["use_runtime_config"] = False
        return CloudTTSAdapter(**values)

    def _save(self, status_message: str | None = None) -> None:
        if self._loading_values:
            return
        self._store_current_character_voice_id()
        values = self._values()
        state.suppress_prompt_constraint()
        # 插件页保存行为参数到插件数据目录。
        state.save_plugin_config(self._plugin_root, values, self._edit_provider_slug)
        # 当前编辑 provider 的 model / default_voice_id 等写入 api.yaml extra。
        provider_extra = {
            "model": str(self.model.currentData() or ""),
            "default_voice_id": self._combo_voice_id(self.default_voice_id),
        }
        if self._is_qwen_active():
            provider_extra["language_type"] = str(self.qwen_language_type.currentData() or "Chinese")
        self._save_provider_extra(provider_extra)
        # 不刷新主 ConfigManager，避免插件页保存时连带触发模板页生成 Prompt。
        self.status.setText(status_message or "插件设置已保存。")

    def _import_voice_ids(self) -> None:
        backup_dir = state.project_root() / "temp_export_cloud_tts_voice_ids_20260512"
        start_dir = backup_dir if backup_dir.is_dir() else state.project_root()
        paths, _selected_filter = QFileDialog.getOpenFileNames(
            self,
            "导入 voice_id JSON",
            str(start_dir),
            "JSON Files (*.json);;All Files (*)",
        )
        if not paths:
            return
        imported = 0
        default_voice_id = ""
        errors: list[str] = []
        for item in paths:
            path = Path(item)
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                errors.append(f"{path.name}: {exc}")
                continue
            try:
                count, default_value = self._import_voice_payload(raw, path)
            except Exception as exc:
                errors.append(f"{path.name}: {exc}")
                continue
            imported += count
            if default_value:
                default_voice_id = default_value

        current_character = self.character_combo.currentText().strip()
        self._ensure_versions_from_selected_map()
        self._refresh_default_voice_options(default_voice_id or None)
        if default_voice_id:
            self._set_voice_combo_value(self.default_voice_id, default_voice_id)
        if current_character:
            self._refresh_character_voice_options(current_character)
        self._save()

        parts = []
        if imported:
            parts.append(f"已导入 {imported} 个 voice_id")
        if default_voice_id:
            parts.append("已恢复默认 voice_id")
        if errors:
            parts.append(f"{len(errors)} 个文件失败")
        message = "，".join(parts) or "没有找到可导入的 voice_id"
        self.status.setText(message)
        if errors:
            QMessageBox.warning(self, "Cloud TTS", "\n".join(errors[:5]))

    def _import_voice_payload(self, raw: Any, source_path: Path) -> tuple[int, str]:
        if isinstance(raw, list):
            imported = 0
            default_voice_id = ""
            for item in raw:
                count, default_value = self._import_voice_payload(item, source_path)
                imported += count
                if default_value:
                    default_voice_id = default_value
            return imported, default_voice_id
        if not isinstance(raw, dict):
            return 0, ""

        imported = 0
        default_voice_id = str(raw.get("default_voice_id") or "").strip()
        current_character = self.character_combo.currentText().strip()
        if default_voice_id and current_character:
            self._ensure_voice_version(
                current_character,
                default_voice_id,
                source="import_default",
                imported_from=str(source_path),
            )

        if "voice_id_map" in raw or "voice_id_versions" in raw or "voice_map" in raw:
            imported += self._import_voice_config_payload(raw, source_path)

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
                raw_voices = [{"voice_id": selected}]
            counted_voice_ids: set[str] = set()
            for rec in self._coerce_voice_records(raw_voices):
                voice_id = str(rec.get("voice_id") or "").strip()
                clean = dict(rec)
                clean.pop("voice_id", None)
                clean.setdefault("source", "import")
                clean["imported_from"] = str(source_path)
                self._ensure_voice_version(character_name, voice_id, **clean)
                if voice_id not in counted_voice_ids:
                    counted_voice_ids.add(voice_id)
                    imported += 1
            if selected:
                self._voice_id_map[character_name] = selected
                self._ensure_voice_version(
                    character_name,
                    selected,
                    source="import_selected",
                    imported_from=str(source_path),
                )
                if selected not in counted_voice_ids:
                    imported += 1
            return imported, default_voice_id

        voice_id = str(raw.get("voice_id") or raw.get("id") or "").strip()
        if voice_id and current_character:
            self._voice_id_map[current_character] = voice_id
            self._ensure_voice_version(
                current_character,
                voice_id,
                source="import_manual",
                imported_from=str(source_path),
            )
            imported += 1

        return imported, default_voice_id

    def _import_voice_config_payload(self, raw: dict[str, Any], source_path: Path) -> int:
        imported = 0
        counted_voice_ids: set[tuple[str, str]] = set()
        voice_map = self._coerce_voice_id_map(raw.get("voice_id_map") or raw.get("voice_map"))
        for name, voice_id in voice_map.items():
            self._voice_id_map[name] = voice_id
            self._ensure_voice_version(
                name,
                voice_id,
                source="import_map",
                imported_from=str(source_path),
            )
            key = (name, voice_id)
            if key not in counted_voice_ids:
                counted_voice_ids.add(key)
                imported += 1
        versions = self._coerce_voice_id_versions(raw.get("voice_id_versions"))
        for name, records in versions.items():
            for rec in records:
                voice_id = str(rec.get("voice_id") or "").strip()
                clean = dict(rec)
                clean.pop("voice_id", None)
                clean.setdefault("source", "import_versions")
                clean["imported_from"] = str(source_path)
                self._ensure_voice_version(name, voice_id, **clean)
                key = (name, voice_id)
                if key not in counted_voice_ids:
                    counted_voice_ids.add(key)
                    imported += 1
        return imported

    def _coerce_voice_records(self, value: Any) -> list[dict[str, Any]]:
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

    # ------------------------------------------------------------------
    # 提示词模板 - 角色约束版本管理
    # ------------------------------------------------------------------

    def _refresh_template_characters(self) -> None:
        """刷新提示词模板区块的角色下拉列表，首项为「默认模板」."""
        current = self.template_character_combo.currentText()
        self.template_character_combo.blockSignals(True)
        self.template_character_combo.clear()
        # 虚拟角色：默认模板，查看/编辑硬编码默认约束
        self.template_character_combo.addItem("默认模板", "默认模板")
        for char in self._characters:
            name = str(char.get("name") or "").strip()
            if name and name != "默认模板":
                self.template_character_combo.addItem(name, name)
        if current:
            idx = self.template_character_combo.findText(current)
            if idx >= 0:
                self.template_character_combo.setCurrentIndex(idx)
        self.template_character_combo.blockSignals(False)
        self._refresh_constraint_version_combo()


    def _on_template_character_changed(self) -> None:
        """切换模板角色时刷新约束版本下拉框和按钮状态."""
        self._refresh_constraint_version_combo()
        self._update_default_template_buttons()

    def _refresh_constraint_version_combo(self) -> None:
        """刷新约束版本下拉框，格式: 'v1 / 用户取名'"""
        name = self.template_character_combo.currentText().strip()
        self.constraint_version_combo.blockSignals(True)
        self.constraint_version_combo.clear()
        if not name:
            self.constraint_version_combo.blockSignals(False)
            self.constraint_text_edit.clear()
            self.version_name_edit.clear()
            self._current_template_character_name = ""
            return

        previous_name = self._current_template_character_name
        same_character = previous_name == name
        current_vid = self.constraint_version_combo.currentData() if same_character else None
        self._current_template_character_name = name

        store = state.load_character_constraints(name)
        allowed_vids = set(state.DEFAULT_PROMPT_VERSION_IDS.values())
        selected_vid = current_vid if current_vid in allowed_vids else None
        if not selected_vid:
            selected_vid = state._default_prompt_version_id(state.current_system_voice_language())

        for code, language_name in state.PROMPT_LANGUAGE_OPTIONS:
            vid = state.DEFAULT_PROMPT_VERSION_IDS[code]
            vdata = store["versions"].get(vid, {})
            version_name = str(vdata.get("name", "")).strip()
            label = f"{language_name} / {version_name}" if version_name else language_name
            self.constraint_version_combo.addItem(label, vid)

        if selected_vid:
            idx = self.constraint_version_combo.findData(selected_vid)
            if idx >= 0:
                self.constraint_version_combo.setCurrentIndex(idx)
        self.constraint_version_combo.blockSignals(False)

        # 传入已读取的 store，避免 _on_constraint_version_changed 重复读盘
        self._on_constraint_version_changed(store=store)
        self._update_default_template_buttons()

    def _update_default_template_buttons(self) -> None:
        """默认模板角色不允许新建/删除版本；重置按钮对所有角色开放."""
        is_default = self.template_character_combo.currentText().strip() == "默认模板"
        self.new_version_btn.setEnabled(not is_default)
        self.delete_version_btn.setEnabled(not is_default)
        self.reset_default_btn.setEnabled(True)

    def _on_constraint_version_changed(self, *, store: dict | None = None) -> None:
        """切换版本时加载名称和内容，仅在版本确实变化时写盘."""
        name = self.template_character_combo.currentText().strip()
        vid = self.constraint_version_combo.currentData()
        if not name or not vid:
            return

        if store is None:
            store = state.load_character_constraints(name)
        version = store.get("versions", {}).get(vid)
        if not version:
            return

        self.version_name_edit.blockSignals(True)
        self.version_name_edit.setText(str(version.get("name", "") or ""))
        self.version_name_edit.blockSignals(False)

        self.constraint_text_edit.blockSignals(True)
        self.constraint_text_edit.setPlainText(version.get("constraint_text", ""))
        self.constraint_text_edit.blockSignals(False)

        # 仅在版本确实变化时才写盘，避免每次浏览都触发磁盘写入
        if store.get("selected_version") != vid:
            state.select_constraint_version(name, vid)

    def _new_constraint_version(self) -> None:
        """以默认模板当前内容为基底创建新版本."""
        name = self.template_character_combo.currentText().strip()
        if not name or name == "默认模板":
            return

        # 从默认模板角色文件读取当前内容，确保随母版同步更新
        store = state.load_character_constraints(name)
        current_vid = self.constraint_version_combo.currentData()
        current_version = store.get("versions", {}).get(current_vid, {})
        language = current_version.get("language") if isinstance(current_version, dict) else None
        language = state._normalize_prompt_language(language) or state._prompt_language_from_version_id(current_vid)
        default_text = ""
        if isinstance(current_version, dict):
            default_text = str(current_version.get("constraint_text") or "")
        if not default_text:
            default_text = state.get_default_template_text(language)

        version_name = self.version_name_edit.text().strip()
        if not version_name:
            version_name = "新版本"
        # 新建版本默认跟随母版同步（source="default"）
        state.upsert_constraint_version(
            name,
            None,
            default_text,
            name=version_name,
            source="manual",
            language=language,
        )
        self._refresh_constraint_version_combo()
        self.status.setText(f"已为 {name} 创建新约束版本。")

    def _save_constraint_version(self) -> None:
        """保存当前编辑内容和名称到选中的版本。默认模板保存时全局同步."""
        name = self.template_character_combo.currentText().strip()
        vid = self.constraint_version_combo.currentData()
        if not name or not vid:
            QMessageBox.warning(self, "Cloud TTS", "请先选择角色和模板语言。")
            return

        text = self.constraint_text_edit.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Cloud TTS", "约束内容不能为空。")
            return

        version_name = self.version_name_edit.text().strip()
        store = state.load_character_constraints(name)
        old_version = store.get("versions", {}).get(vid, {})
        language = old_version.get("language") if isinstance(old_version, dict) else None
        language = state._normalize_prompt_language(language) or state._prompt_language_from_version_id(vid)
        # 默认模板：保存后全局同步所有 source="default" 的角色版本
        if name == "默认模板":
            state.upsert_constraint_version(
                name,
                vid,
                text,
                name=version_name,
                source="default",
                language=language,
            )
            count = state.propagate_default_template(text, language=language)
            self._refresh_constraint_version_combo()
            self.status.setText(
                f"已保存默认模板。已同步 {count} 个使用默认模板的角色。"
            )
        else:
            # 手动保存意味着用户自定义，标记为 manual 停止跟随母版同步
            state.upsert_constraint_version(
                name,
                vid,
                text,
                name=version_name,
                source="manual",
                language=language,
            )
            self._refresh_constraint_version_combo()
            self.status.setText(f"已保存 {name} 的模板语言 {vid}。")

    def _delete_constraint_version(self) -> None:
        """删除当前选中的约束版本（至少保留一个）."""
        name = self.template_character_combo.currentText().strip()
        vid = self.constraint_version_combo.currentData()
        if not name or not vid:
            QMessageBox.warning(self, "Cloud TTS", "请先选择角色和版本。")
            return

        versions = state.list_constraint_versions(name)
        if len(versions) <= 1:
            QMessageBox.warning(self, "Cloud TTS", "至少需要保留一个约束版本。")
            return

        reply = QMessageBox.question(
            self, "Cloud TTS",
            f"确认删除 {name} 的约束版本「{vid}」？\n删除后无法恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if state.remove_constraint_version(name, vid):
            self._refresh_constraint_version_combo()
            self.status.setText(f"已删除约束版本「{vid}」。")
        else:
            QMessageBox.warning(self, "Cloud TTS", "删除失败。")

    def _reset_default_template(self) -> None:
        """将当前角色的当前语言模板重置为硬编码原始内容。默认模板会全局同步，普通角色仅重置自身。"""
        name = self.template_character_combo.currentText().strip()
        if not name:
            return
        is_default = name == "默认模板"

        vid = self.constraint_version_combo.currentData()
        if not vid:
            QMessageBox.warning(self, "Cloud TTS", "请先选择要重置的提示词版本。")
            return
        store = state.load_character_constraints(name)
        version = store.get("versions", {}).get(vid, {})
        language = version.get("language") if isinstance(version, dict) else None
        language = state._normalize_prompt_language(language) or state._prompt_language_from_version_id(vid)
        if not language:
            QMessageBox.warning(self, "Cloud TTS", "无法确定当前版本的语言，请重新选择版本后再试。")
            return
        default_text = state.build_default_constraint_text(language)

        if is_default:
            prompt = "确认将当前默认模板重置为原始硬编码内容？\n此操作只会同步更新同语种、且仍跟随母版的角色版本。"
        else:
            language_label = dict(state.PROMPT_LANGUAGE_OPTIONS).get(language, language)
            prompt = f"确认将角色「{name}」的 {language_label} 模板重置为原始硬编码内容？\n此操作不会影响其他角色。"

        reply = QMessageBox.question(
            self, "Cloud TTS",
            prompt,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        version_name = self.version_name_edit.text().strip()
        state.upsert_constraint_version(
            name,
            vid,
            default_text,
            name=version_name,
            source="default",
            language=language,
        )
        if is_default:
            count = state.propagate_default_template(default_text, language=language)
            self.status.setText(
                f"已重置默认模板为原始内容。已同步 {count} 个使用默认模板的角色。"
            )
        else:
            self.status.setText(
                f"已重置角色「{name}」的 {dict(state.PROMPT_LANGUAGE_OPTIONS).get(language, language)} 模板为原始内容。"
            )
        self._refresh_constraint_version_combo()

    def _upload_selected_character(self) -> None:
        char = self._selected_character()
        if not char:
            QMessageBox.warning(self, "Cloud TTS", "没有选中的角色。")
            return
        self._store_current_local_reference_audio()
        self._store_current_reference_audio_language()
        path, source_label = self._reference_audio_for_upload(char)
        if not path or not path.is_file():
            QMessageBox.warning(self, "Cloud TTS", "请先选择一个存在的本地参考音频。")
            return
        is_qwen = self._is_qwen_active()
        provider_label = "DashScope" if is_qwen else "MiniMax"
        api_extra = state.get_qwen_extra() if is_qwen else state.get_cloud_extra()
        if not str(api_extra.get("api_key") or "").strip():
            QMessageBox.warning(
                self, "Cloud TTS",
                f"请先在 API 设定页选择 {'Qwen3 TTS' if is_qwen else 'MiniMax TTS'} 并填写 API KEY。",
            )
            return
        self.upload_btn.setEnabled(False)
        self.status.setText(f"正在上传参考音频，通过 {provider_label} 创建 voice_id...")
        try:
            adapter = self._adapter()
            if is_qwen:
                voice_id = adapter.create_cloned_voice_from_file(
                    path,
                    character_name=str(char.get("name") or ""),
                    voice_name=str(char.get("name") or ""),
                    target_model=str(self.model.currentData() or ""),
                )
            else:
                voice_id = adapter.create_cloned_voice_from_file(
                    path,
                    character_name=str(char.get("name") or ""),
                    prompt_text=str(char.get("prompt_text") or ""),
                    reference_audio_language=self._reference_audio_language_for_name(
                        str(char.get("name") or "")
                    ),
                )
        except Exception as exc:
            self.status.setText(f"上传失败：{exc}")
            QMessageBox.warning(self, "Cloud TTS", str(exc))
        else:
            name = str(char.get("name") or "").strip()
            if name:
                self._ensure_voice_version(
                    name,
                    voice_id,
                    source="local_upload" if source_label.startswith("本地") else "upload",
                    model=str(self.model.currentData() or ""),
                    reference_audio_path=str(path),
                    reference_audio_source=source_label,
                    reference_audio_language=self._reference_audio_language_for_name(name),
                )
                self._voice_id_map[name] = voice_id
                self._refresh_character_voice_options(name)
                self._refresh_default_voice_options()
            self._save()
            self.status.setText(f"上传完成，已绑定 {name or '当前角色'} 的 voice_id：{voice_id}")
        finally:
            self.upload_btn.setEnabled(True)
