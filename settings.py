from __future__ import annotations

import ast
import json
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from plugins.minimax_tts.adapter import MiniMaxTTSAdapter
from plugins.minimax_tts import state


LABEL_WIDTH = 134
ROW_HEIGHT = 44
FIELD_HEIGHT = 34


class MinimaxTtsSettingsWidget(QWidget):
    def __init__(self, plugin_root: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._plugin_root = plugin_root
        self._characters: list[dict[str, Any]] = []
        self._voice_id_map: dict[str, str] = {}
        self._voice_id_versions: dict[str, list[dict[str, Any]]] = {}
        self._build_ui()
        self._load_values()
        self._reload_characters()

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

        switch_box, switch_lay = self._section("功能开关")
        self.paragraph_split = self._checkbox("Paragraph：按段落整段生成（不按标点切分）⭐推荐开启")
        self.paragraph_split.setChecked(True)
        switch_lay.addWidget(self._check_row(self.paragraph_split))

        self.prompt_constraint = self._checkbox("提示词约束：注入 MiniMax 语气标签指令（关闭则不注入）⭐推荐开启")
        self.prompt_constraint.setChecked(False)
        switch_lay.addWidget(self._check_row(self.prompt_constraint))
        root.addWidget(switch_box)

        api_box, api_lay = self._section("模型与兜底声线")
        self.model = self._combo()
        for item in (
            "speech-2.8-hd",
            "speech-2.8-turbo",
            "speech-2.6-hd",
            "speech-2.6-turbo",
            "speech-02-hd",
            "speech-02-turbo",
        ):
            self.model.addItem(item, item)
        api_lay.addWidget(self._row("模型", self.model))

        self.default_voice_id = self._voice_combo()
        self.default_voice_id.lineEdit().setPlaceholderText("未匹配角色时使用的保底 voice_id")
        api_lay.addWidget(self._row("无角色兜底 voice_id", self.default_voice_id))
        root.addWidget(api_box)

        synth_box, synth_lay = self._section("合成参数")
        self.language_boost = self._combo()
        for item in ("auto", "Japanese", "Chinese", "Chinese,Yue", "English"):
            self.language_boost.addItem(item, item)
        synth_lay.addWidget(self._row("语言增强", self.language_boost))

        self.audio_format = self._combo()
        for item in ("wav", "mp3", "flac"):
            self.audio_format.addItem(item, item)
        synth_lay.addWidget(self._row("音频格式", self.audio_format))

        self.sample_rate = self._spin()
        self.sample_rate.setRange(8000, 48000)
        self.sample_rate.setSingleStep(1000)
        self.sample_rate.setValue(32000)
        synth_lay.addWidget(self._row("采样率", self.sample_rate))

        self.bitrate = self._spin()
        self.bitrate.setRange(32000, 320000)
        self.bitrate.setSingleStep(16000)
        self.bitrate.setValue(128000)
        synth_lay.addWidget(self._row("比特率", self.bitrate))

        self.channel = self._combo()
        self.channel.addItem("单声道", "1")
        self.channel.addItem("双声道", "2")
        synth_lay.addWidget(self._row("声道", self.channel))

        self.speed = self._double_spin()
        self.speed.setRange(0.5, 2.0)
        self.speed.setSingleStep(0.05)
        self.speed.setValue(1.0)
        synth_lay.addWidget(self._row("语速", self.speed))

        self.vol = self._double_spin()
        self.vol.setRange(0.1, 10.0)
        self.vol.setSingleStep(0.05)
        self.vol.setValue(1.0)
        synth_lay.addWidget(self._row("音量", self.vol))

        self.pitch = self._spin()
        self.pitch.setRange(-12, 12)
        synth_lay.addWidget(self._row("音高", self.pitch))

        self.emotion = self._combo()
        for item in (
            "",
            "happy",
            "sad",
            "angry",
            "fearful",
            "disgusted",
            "surprised",
            "neutral",
        ):
            self.emotion.addItem(item or "不固定", item)
        synth_lay.addWidget(self._row("默认情绪", self.emotion))

        self.auto_clone = self._checkbox("未找到 voice_id 时，从角色参考音频自动克隆")
        self.auto_clone.setChecked(False)
        synth_lay.addWidget(self._check_row(self.auto_clone))

        self.request_timeout = self._spin()
        self.request_timeout.setRange(5, 600)
        self.request_timeout.setValue(120)
        synth_lay.addWidget(self._row("请求超时", self.request_timeout))

        root.addWidget(synth_box)

        clone_box, clone_lay = self._section("角色参考音频上传")
        role_line = QWidget()
        role_line.setFixedHeight(ROW_HEIGHT)
        role_lay = QHBoxLayout(role_line)
        role_lay.setContentsMargins(0, 4, 0, 4)
        role_lay.setSpacing(8)
        self.character_combo = self._combo()
        self.refresh_roles = QPushButton("刷新角色")
        self.refresh_roles.setFixedHeight(FIELD_HEIGHT)
        self.refresh_roles.clicked.connect(self._reload_characters)
        role_lay.addWidget(self.character_combo, stretch=1)
        role_lay.addWidget(self.refresh_roles)
        clone_lay.addWidget(role_line)

        self.ref_path = QLabel("")
        self.ref_path.setWordWrap(True)
        self.ref_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        clone_lay.addWidget(self.ref_path)

        self.character_voice_id = self._voice_combo()
        self.character_voice_id.lineEdit().setPlaceholderText("该角色专用 voice_id")
        self.character_voice_id.currentIndexChanged.connect(
            lambda _index: self._store_current_character_voice_id()
        )
        self.character_voice_id.lineEdit().editingFinished.connect(
            self._store_current_character_voice_id
        )
        clone_lay.addWidget(self._row("角色 voice_id 版本", self.character_voice_id))

        self.upload_btn = QPushButton("上传所选角色参考音频并缓存 voice_id")
        self.upload_btn.setFixedHeight(FIELD_HEIGHT)
        self.upload_btn.clicked.connect(self._upload_selected_character)

        self.import_voice_btn = QPushButton("导入 voice_id JSON")
        self.import_voice_btn.setFixedHeight(FIELD_HEIGHT)
        self.import_voice_btn.clicked.connect(self._import_voice_ids)

        self.need_noise_reduction = self._checkbox("克隆时启用降噪")
        clone_lay.addWidget(self._check_row(self.need_noise_reduction))

        self.need_volume_normalization = self._checkbox("克隆时音量归一")
        clone_lay.addWidget(self._check_row(self.need_volume_normalization))

        self.voice_cache_path = self._line_edit("cache/audio/minimax_voice_cache.json")
        clone_lay.addWidget(self._row("自动克隆缓存", self.voice_cache_path))

        voice_actions = QWidget()
        voice_actions.setFixedHeight(ROW_HEIGHT)
        voice_actions_lay = QHBoxLayout(voice_actions)
        voice_actions_lay.setContentsMargins(0, 4, 0, 4)
        voice_actions_lay.setSpacing(8)
        voice_actions_lay.addWidget(self.upload_btn, stretch=1)
        voice_actions_lay.addWidget(self.import_voice_btn)
        clone_lay.addWidget(voice_actions)
        root.addWidget(clone_box)
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

        actions = QHBoxLayout()
        actions.setContentsMargins(12, 8, 12, 8)
        actions.setSpacing(12)
        self.save_btn = QPushButton("保存配置")
        self.save_btn.clicked.connect(self._save)
        self.save_btn.setFixedHeight(FIELD_HEIGHT)
        self.save_btn.setMinimumWidth(160)
        self.save_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        actions.addWidget(self.save_btn)
        actions.addStretch(1)
        foot_lay.addLayout(actions)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setContentsMargins(12, 0, 12, 8)
        foot_lay.addWidget(self.status)
        outer.addWidget(foot)

        self.character_combo.currentIndexChanged.connect(self._sync_reference_label)

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

        title = QLabel("MiniMax TTS 使用提示")
        title.setStyleSheet("color: #b88cff; font-weight: 600;")
        lay.addWidget(title)

        body = QLabel(
            “<b>① MiniMax TTS 选择：</b>先在首页 / 主菜单 API 设置页选择 MiniMax TTS，填写 API KEY 和 BASE URL 并保存；”
            “本页不重复保存这两个连接凭证，只保存模型、合成参数、Paragraph 和 voice_id 绑定。<br/><br/>”
            “<b>② ⭐功能开关（重要）：</b>「功能开关」区块的两个选项建议开启——“
            “<b>Paragraph</b> 按段落整段生成，台词更长更自然；”
            “<b>提示词约束</b> 则向 LLM 注入语气标签指令，让语音表现更丰富。<br/><br/>”
            “<b>③ 声纹复刻：</b>请在本页选择角色，确认角色已有参考音频，然后点击「上传所选角色参考音频并缓存 voice_id」。”
            “生成的 voice_id 保存在 <code>data/plugins/com.shinsekai.minimax_tts/voices/</code>，升级插件不会自动删除。<br/><br/>”
            “<b>④ 参考音频格式：</b>插件会使用 imageio-ffmpeg 提供的 ffmpeg 自动转换；”
            “未安装依赖时，只能直接上传符合 MiniMax 要求的 mp3、m4a 或 wav 文件。”
        )
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        # 支持富文本中的 HTML 标签
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

    def _check_row(self, checkbox: QCheckBox) -> QWidget:
        row = QWidget()
        row.setFixedHeight(34)
        lay = QHBoxLayout(row)
        lay.setContentsMargins(LABEL_WIDTH + 12, 0, 0, 0)
        lay.addWidget(checkbox)
        return row

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

    def _spin(self) -> QSpinBox:
        spin = QSpinBox()
        self._prepare_field(spin)
        return spin

    def _double_spin(self) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        self._prepare_field(spin)
        return spin

    def _checkbox(self, text: str) -> QCheckBox:
        checkbox = QCheckBox(text)
        checkbox.setFixedHeight(30)
        checkbox.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return checkbox

    def _apply_field_style(self) -> None:
        self.setStyleSheet("")

    def _as_int(self, value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _as_float(self, value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
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

    def _load_values(self) -> None:
        state.migrate_package_config_to_data_root()
        state.migrate_api_extra_to_plugin_state(self._plugin_root)
        cfg = state.load_plugin_config(self._plugin_root)
        extra = state.get_minimax_extra()
        values = dict(
            {
                k: v
                for k, v in cfg.items()
                if v not in (None, "", {}, [])
            }
        )
        # 官方 adapter 配置从 api.yaml 读取；旧版插件状态只作为兼容兜底。
        values.update(extra)
        self._set_combo(self.model, str(values.get("model") or "speech-2.8-hd"))
        self._voice_id_map = self._coerce_voice_id_map(values.get("voice_id_map"))
        self._voice_id_versions = self._coerce_voice_id_versions(values.get("voice_id_versions"))
        self._ensure_versions_from_selected_map()
        self._refresh_default_voice_options(str(values.get("default_voice_id") or ""))
        self._set_combo(self.language_boost, str(values.get("language_boost") or "auto"))
        self._set_combo(self.audio_format, str(values.get("audio_format") or "wav"))
        self.sample_rate.setValue(self._as_int(values.get("sample_rate"), 32000))
        self.bitrate.setValue(self._as_int(values.get("bitrate"), 128000))
        self._set_combo(self.channel, str(values.get("channel") or "1"))
        self._set_combo(self.emotion, str(values.get("emotion") or ""))
        self.speed.setValue(self._as_float(values.get("speed"), 1.0))
        self.vol.setValue(self._as_float(values.get("vol"), 1.0))
        self.pitch.setValue(self._as_int(values.get("pitch"), 0))
        self.auto_clone.setChecked(bool(values.get("auto_clone_from_reference", False)))
        self.paragraph_split.setChecked(
            self._as_bool(values.get("paragraph_split_enabled"), True)
        )
        self.prompt_constraint.setChecked(
            self._as_bool(values.get("auto_prompt_constraint"), False)
        )
        self.request_timeout.setValue(self._as_int(values.get("request_timeout"), 120))
        self.need_noise_reduction.setChecked(bool(values.get("need_noise_reduction", False)))
        self.need_volume_normalization.setChecked(
            bool(values.get("need_volume_normalization", False))
        )
        self.voice_cache_path.setText(
            str(values.get("voice_cache_path") or "cache/audio/minimax_voice_cache.json")
        )

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

    def _reload_characters(self) -> None:
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
        self._sync_reference_label()

    def _selected_character(self) -> dict[str, Any] | None:
        name = self.character_combo.currentText()
        return state.find_character(name)

    def _sync_reference_label(self) -> None:
        char = self._selected_character()
        if not char:
            self.ref_path.setText("未找到角色。")
            return
        path = state.resolve_reference_audio(char)
        name = str(char.get("name") or "").strip()
        if path and path.is_file():
            self.ref_path.setText(f"参考音频：{path}")
        elif path:
            self.ref_path.setText(f"参考音频不存在：{path}")
        else:
            self.ref_path.setText("该角色没有 refer_audio_path。")
        self._refresh_character_voice_options(name)

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
        return {
            "model": str(self.model.currentData() or "speech-2.8-hd"),
            "default_voice_id": self._combo_voice_id(self.default_voice_id),
            "voice_id_map": dict(self._voice_id_map),
            "voice_id_versions": dict(self._voice_id_versions),
            "language_boost": str(self.language_boost.currentData() or "auto"),
            "audio_format": str(self.audio_format.currentData() or "wav"),
            "sample_rate": int(self.sample_rate.value()),
            "bitrate": int(self.bitrate.value()),
            "channel": int(self.channel.currentData() or 1),
            "speed": float(self.speed.value()),
            "vol": float(self.vol.value()),
            "pitch": int(self.pitch.value()),
            "emotion": str(self.emotion.currentData() or ""),
            "auto_clone_from_reference": self.auto_clone.isChecked(),
            "auto_prompt_constraint": self.prompt_constraint.isChecked(),
            "paragraph_split_enabled": self.paragraph_split.isChecked(),
            "request_timeout": int(self.request_timeout.value()),
            "need_noise_reduction": self.need_noise_reduction.isChecked(),
            "need_volume_normalization": self.need_volume_normalization.isChecked(),
            "voice_cache_path": (
                self.voice_cache_path.text().strip()
                or "cache/audio/minimax_voice_cache.json"
            ),
        }

    def _adapter(self) -> MiniMaxTTSAdapter:
        values = self._values()
        values.update(state.get_minimax_extra())
        # 上传按钮使用当前表单即时值，不等待下一次 adapter 运行时重新读配置。
        values["use_runtime_config"] = False
        return MiniMaxTTSAdapter(**values)

    def _save(self) -> None:
        values = self._values()
        state.suppress_prompt_constraint()
        # 插件页只保存 MiniMax 行为参数；实际 TTS 引擎由主菜单 API 页选择。
        state.save_plugin_config(self._plugin_root, values)
        # 不刷新主 ConfigManager，避免插件页保存时连带触发模板页生成 Prompt。
        self.status.setText(
            "已保存配置。TTS 引擎请在主菜单 API 页选择；"
            "如果主聊天进程已经启动，请重启聊天进程让 adapter 重新载入。"
        )

    def _import_voice_ids(self) -> None:
        backup_dir = state.project_root() / "temp_export_minimax_voice_ids_20260512"
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
            QMessageBox.warning(self, "MiniMax TTS", "\n".join(errors[:5]))

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

    def _upload_selected_character(self) -> None:
        char = self._selected_character()
        if not char:
            QMessageBox.warning(self, "MiniMax TTS", "没有选中的角色。")
            return
        path = state.resolve_reference_audio(char)
        if not path or not path.is_file():
            QMessageBox.warning(self, "MiniMax TTS", "角色参考音频不存在。")
            return
        if not str(state.get_minimax_extra().get("api_key") or "").strip():
            QMessageBox.warning(self, "MiniMax TTS", "请先在 API 设定页填写 MiniMax API KEY。")
            return
        self.upload_btn.setEnabled(False)
        self.status.setText("正在转换并上传参考音频，随后创建 voice_id...")
        try:
            voice_id = self._adapter().create_cloned_voice_from_file(
                path,
                character_name=str(char.get("name") or ""),
                prompt_text=str(char.get("prompt_text") or ""),
            )
        except Exception as exc:
            self.status.setText(f"上传失败：{exc}")
            QMessageBox.warning(self, "MiniMax TTS", str(exc))
        else:
            name = str(char.get("name") or "").strip()
            if name:
                self._ensure_voice_version(
                    name,
                    voice_id,
                    source="upload",
                    model=str(self.model.currentData() or ""),
                    reference_audio_path=str(path),
                )
                self._voice_id_map[name] = voice_id
                self._refresh_character_voice_options(name)
                self._refresh_default_voice_options()
            self._save()
            self.status.setText(f"上传完成，已绑定 {name or '当前角色'} 的 voice_id：{voice_id}")
        finally:
            self.upload_btn.setEnabled(True)
