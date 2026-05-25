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
