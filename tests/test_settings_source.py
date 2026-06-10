import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _function_source(function_name: str, file_name: str = "settings.py") -> str:
    path = ROOT / file_name
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            return ast.get_source_segment(source, node) or ""
    raise AssertionError(f"missing function: {file_name}:{function_name}")


def test_clone_demo_button_opens_containing_folder():
    source = (ROOT / "settings.py").read_text(encoding="utf-8")
    function_source = _function_source("_open_last_clone_demo_audio")

    assert 'QPushButton("打开试听文件夹")' in source
    assert "QUrl.fromLocalFile(str(path.parent))" in function_source
    assert "QUrl.fromLocalFile(str(path))" not in function_source


def test_minimax_clone_text_is_labeled_as_demo_text():
    source = (ROOT / "settings.py").read_text(encoding="utf-8")
    handler_source = _function_source("_on_reference_text_changed")

    assert 'self.reference_text_row = self._row("试听文本", self.reference_text)' in source
    assert "可选：用于生成克隆试听音频，留空则使用角色卡 prompt_text" in source
    assert "当前角色试听文本已更新。" in handler_source
    assert 'self.gsv_prompt_text_row = self._row("GSV 参考文本", self.gsv_prompt_text)' in source


def test_voice_id_export_button_writes_single_voice_payload():
    source = (ROOT / "settings.py").read_text(encoding="utf-8")
    service_source = (ROOT / "config_service.py").read_text(encoding="utf-8")
    payload_source = _function_source("voice_export_payload", "config_service.py")
    export_source = _function_source("_export_current_voice_id")
    bind_source = _function_source("bind_imported_voice_record", "config_service.py")

    assert 'QPushButton("导出当前 voice_id")' in source
    assert "self.export_voice_btn.clicked.connect(self._export_current_voice_id)" in source
    assert "voice_actions_lay.addWidget(self.export_voice_btn)" in source
    assert "VOICE_ID_EXPORT_EXCLUDED_KEYS" in service_source
    assert '"reference_audio_path"' in service_source
    assert '"character_name",' in service_source
    assert '"imported_from",' in service_source
    assert '"type": "cloud_tts.voice_id"' in payload_source
    assert '"character_name": character_name' in payload_source
    assert '"voice_id": voice_id' in payload_source
    assert "key not in VOICE_ID_EXPORT_EXCLUDED_KEYS" in payload_source
    assert "VOICE_ID_EXPORT_EXCLUDED_KEYS" in bind_source
    assert "clean.pop(key, None)" in bind_source
    assert "QFileDialog.getSaveFileName" in export_source
    assert "json.dumps(payload, ensure_ascii=False, indent=2)" in export_source


def test_imported_voice_can_be_default_candidate_with_or_without_character():
    service_source = (ROOT / "config_service.py").read_text(encoding="utf-8")
    all_voice_source = _function_source("all_voice_options", "config_service.py")
    character_voice_source = _function_source("_refresh_character_voice_options")
    target_source = _function_source("import_voice_target_character", "config_service.py")
    import_source = _function_source("import_voice_payload", "config_service.py")
    config_import_source = _function_source("import_voice_config_payload", "config_service.py")

    assert 'IMPORTED_VOICE_BUCKET = "__imported__"' in service_source
    assert 'IMPORTED_VOICE_LABEL = "导入音色"' in service_source
    assert 'display_name = str(rec.get("imported_character_name") or "").strip()' in all_voice_source
    assert "label_name = display_name or bucket_label_name" in all_voice_source
    assert 'display_name = str(rec.get("imported_character_name") or "").strip()' in character_voice_source
    assert 'f"{display_name} / 版本 {idx} / {voice_id}"' in character_voice_source
    assert 'f"版本 {idx} / {voice_id}"' in character_voice_source
    assert "state.find_character(exported_name)" in target_source
    assert "state.find_character(current_name)" in target_source
    assert target_source.index("state.find_character(current_name)") < target_source.index(
        "state.find_character(exported_name)"
    )
    assert 'return current_name, "current"' in target_source
    assert 'return IMPORTED_VOICE_BUCKET, "imported"' in target_source
    assert 'target_mode != "matched" and character_name != target_character' in import_source
    assert 'target_mode != "matched" and name != target_name' in config_import_source
    assert "if selected and not default_voice_id:" in import_source
    assert "default_voice_id = selected" in import_source
    assert "if voice_id and not default_voice_id:" in import_source
    assert "default_voice_id = voice_id" in import_source
    assert "state.find_character(current_character)" in import_source
