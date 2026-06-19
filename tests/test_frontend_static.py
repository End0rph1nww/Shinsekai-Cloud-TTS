from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"


def test_frontend_page_declares_p3_workbench_assets_and_regions():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")

    assert '<link rel="stylesheet" href="./studio.css"' in html
    assert '<script type="module" src="./studio.js"' in html

    required_ids = [
        "cloud-tts-app",
        "global-settings",
        "provider-select",
        "model-select",
        "character-workbench",
        "character-grid",
        "voice-bind-form",
        "reference-upload",
        "clone-panel",
        "voice-import-file",
        "gsv-profile-form",
        "constraint-editor",
        "confirm-panel",
        "toast-region",
    ]
    for element_id in required_ids:
        assert f'id="{element_id}"' in html


def test_frontend_styles_define_neobrutalist_tokens_and_states():
    css = (FRONTEND / "studio.css").read_text(encoding="utf-8")

    for token in (
        "--nb-bg",
        "--nb-surface",
        "--nb-ink",
        "--nb-accent",
        "--nb-accent-2",
        "--nb-accent-3",
        "--nb-danger",
        "--nb-border",
        "--nb-shadow",
    ):
        assert token in css

    assert ".nb-card" in css
    assert ".nb-button:hover" in css
    assert ".character-card.is-selected" in css
    assert "@media (prefers-color-scheme: dark)" in css


def test_frontend_script_uses_pr80_plugin_routes_and_all_actions():
    js = (FRONTEND / "studio.js").read_text(encoding="utf-8")

    for route_part in (
        "/api/plugins/",
        "/ui",
        "/config",
        "/actions/",
    ):
        assert route_part in js

    for action_id in (
        "list_characters",
        "bind_voice",
        "upload_reference",
        "clear_reference",
        "clone_voice",
        "export_voice",
        "import_voice",
        "save_gpt_sovits_profile",
        "get_constraints",
        "save_constraints",
    ):
        assert action_id in js

    for browser_api in ("FileReader", "Blob", "URL.createObjectURL", "visibilitychange"):
        assert browser_api in js


def test_dist_provider_switch_does_not_pre_save_before_switch_action():
    html = (FRONTEND / "dist" / "index.html").read_text(encoding="utf-8")
    marker = 'runAction("switch_provider", { fromProvider: snapshot.provider, toProvider: next }, {'
    start = html.index(marker)
    block = html[start : html.index("});", start)]

    assert "saveFirst" not in block
