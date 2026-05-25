import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _function_source(function_name: str) -> str:
    path = ROOT / "settings.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            return ast.get_source_segment(source, node) or ""
    raise AssertionError(f"missing function: {function_name}")


def test_clone_demo_button_opens_containing_folder():
    source = (ROOT / "settings.py").read_text(encoding="utf-8")
    function_source = _function_source("_open_last_clone_demo_audio")

    assert 'QPushButton("打开试听文件夹")' in source
    assert "QUrl.fromLocalFile(str(path.parent))" in function_source
    assert "QUrl.fromLocalFile(str(path))" not in function_source


def test_voice_id_export_button_writes_single_voice_payload():
    source = (ROOT / "settings.py").read_text(encoding="utf-8")
    payload_source = _function_source("_current_voice_export_payload")
    export_source = _function_source("_export_current_voice_id")
    bind_source = _function_source("_bind_imported_voice_record")

    assert 'QPushButton("导出当前 voice_id")' in source
    assert "self.export_voice_btn.clicked.connect(self._export_current_voice_id)" in source
    assert "voice_actions_lay.addWidget(self.export_voice_btn)" in source
    assert "VOICE_ID_EXPORT_EXCLUDED_KEYS" in source
    assert '"reference_audio_path"' in source
    assert '"type": "cloud_tts.voice_id"' in payload_source
    assert '"character_name": character_name' in payload_source
    assert '"voice_id": voice_id' in payload_source
    assert "key not in VOICE_ID_EXPORT_EXCLUDED_KEYS" in payload_source
    assert "VOICE_ID_EXPORT_EXCLUDED_KEYS" in bind_source
    assert "QFileDialog.getSaveFileName" in export_source
    assert "json.dumps(payload, ensure_ascii=False, indent=2)" in export_source


def test_imported_voice_can_be_default_candidate_with_or_without_character():
    source = (ROOT / "settings.py").read_text(encoding="utf-8")
    all_voice_source = _function_source("_all_voice_options")
    target_source = _function_source("_import_voice_target_character")
    import_source = _function_source("_import_voice_payload")

    assert 'IMPORTED_VOICE_BUCKET = "__imported__"' in source
    assert 'IMPORTED_VOICE_LABEL = "导入音色"' in source
    assert "label_name = IMPORTED_VOICE_LABEL if clean_name == IMPORTED_VOICE_BUCKET else clean_name" in all_voice_source
    assert "state.find_character(exported_name)" in target_source
    assert "state.find_character(current_name)" in target_source
    assert 'return IMPORTED_VOICE_BUCKET, "imported"' in target_source
    assert "if selected and not default_voice_id:" in import_source
    assert "default_voice_id = selected" in import_source
    assert "if voice_id and not default_voice_id:" in import_source
    assert "default_voice_id = voice_id" in import_source
    assert "state.find_character(current_character)" in import_source
