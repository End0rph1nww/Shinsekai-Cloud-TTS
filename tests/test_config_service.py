from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from plugins.cloud_tts import config_service as service
from plugins.cloud_tts import state


def test_coerce_voice_id_map_accepts_json_and_repr_strings():
    assert service.coerce_voice_id_map('{"A": "v1"}') == {"A": "v1"}
    assert service.coerce_voice_id_map("{'A': 'v1'}") == {"A": "v1"}
    assert service.coerce_voice_id_map({"A": "", "": "x", "B": "v2"}) == {"B": "v2"}
    assert service.coerce_voice_id_map("not a dict") == {}


def test_coerce_voice_id_versions_dedups_and_normalizes():
    out = service.coerce_voice_id_versions(
        {"A": ["v1", {"voice_id": "v1"}, {"id": "v2", "source": "x"}], "": ["v3"]}
    )

    assert [rec["voice_id"] for rec in out["A"]] == ["v1", "v2"]
    assert out["A"][0]["created_at"] == 0
    assert "" not in out


def test_ensure_voice_version_skips_existing_and_empty_extras():
    versions: dict[str, list[dict]] = {}

    service.ensure_voice_version(versions, "A", "v1", source="manual", note="")
    service.ensure_voice_version(versions, "A", "v1", source="other")

    assert len(versions["A"]) == 1
    assert versions["A"][0]["source"] == "manual"
    assert "note" not in versions["A"][0]


def test_voice_export_payload_excludes_internal_keys():
    versions = {
        "A": [
            {
                "voice_id": "v1",
                "reference_audio_path": "/x.wav",
                "note": "keep",
                "model": "m0",
            }
        ]
    }

    payload = service.voice_export_payload(
        "A", "v1", versions, provider_slug=state.PROVIDER_SLUG, model=""
    )

    assert payload["type"] == "cloud_tts.voice_id"
    assert payload["character_name"] == "A"
    assert payload["voice_id"] == "v1"
    assert payload["model"] == "m0"
    assert payload["note"] == "keep"
    assert "reference_audio_path" not in payload
    assert (
        service.voice_export_payload(
            "A", "", versions, provider_slug=state.PROVIDER_SLUG, model=""
        )
        is None
    )


def test_import_voice_payload_binds_to_current_character(monkeypatch, tmp_path):
    monkeypatch.setattr(
        state,
        "find_character",
        lambda name: {"name": name} if name == "Hanadan" else None,
    )
    voice_map: dict[str, str] = {}
    versions: dict[str, list[dict]] = {}
    raw = {"character_name": "Exported", "voice_id": "v9"}

    count, default = service.import_voice_payload(
        voice_map, versions, raw, tmp_path / "x.json", current_character="Hanadan"
    )

    assert count == 1
    assert default == "v9"
    assert voice_map["Hanadan"] == "v9"
    assert versions["Hanadan"][0]["imported_character_name"] == "Exported"


def test_import_voice_payload_falls_back_to_imported_bucket(monkeypatch, tmp_path):
    monkeypatch.setattr(state, "find_character", lambda name: None)
    voice_map: dict[str, str] = {}
    versions: dict[str, list[dict]] = {}

    count, default = service.import_voice_payload(
        voice_map, versions, {"voice_id": "v5"}, tmp_path / "x.json", current_character=""
    )

    assert count == 1
    assert default == "v5"
    assert voice_map[service.IMPORTED_VOICE_BUCKET] == "v5"


def test_import_voice_config_payload_imports_maps_and_versions(monkeypatch, tmp_path):
    monkeypatch.setattr(state, "find_character", lambda name: None)
    voice_map: dict[str, str] = {}
    versions: dict[str, list[dict]] = {}
    raw = {
        "voice_id_map": {"A": "v1"},
        "voice_id_versions": {"B": [{"voice_id": "v2"}]},
    }

    count = service.import_voice_config_payload(
        voice_map, versions, raw, tmp_path / "y.json", current_character=""
    )

    assert count == 2
    bucket = versions[service.IMPORTED_VOICE_BUCKET]
    assert {rec["voice_id"] for rec in bucket} == {"v1", "v2"}
    assert voice_map[service.IMPORTED_VOICE_BUCKET] == "v1"


def test_all_voice_options_labels_imported_bucket():
    voice_map = {"A": "v3"}
    versions = {
        service.IMPORTED_VOICE_BUCKET: [
            {"voice_id": "v1", "imported_character_name": "原角色"}
        ]
    }

    options = service.all_voice_options(voice_map, versions)

    labels = {voice_id: label for label, voice_id in options}
    assert labels["v1"] == "原角色 / 版本 1 / v1"
    assert labels["v3"] == "A / 当前 / v3"


def test_reference_text_for_character_prefers_custom_map():
    char = {"name": "Hanadan", "prompt_text": "角色卡参考文本"}

    assert service.reference_text_for_character(char, {"Hanadan": "自定义"}) == "自定义"
    assert service.reference_text_for_character(char, {}) == "角色卡参考文本"


def test_provider_helpers_cover_three_providers():
    assert service.provider_label(state.PROVIDER_SLUG) == "MiniMax TTS"
    assert service.provider_label(state.QWEN_PROVIDER_SLUG) == "Qwen3 TTS"
    assert service.provider_label(state.GPT_SOVITS_PROVIDER_SLUG) == "GPT SoVITS Cloud"
    assert service.provider_default_model(state.PROVIDER_SLUG) == service.MINIMAX_DEFAULT_MODEL
    assert service.provider_default_model(state.QWEN_PROVIDER_SLUG) == state.QWEN_DEFAULT_MODEL
    assert service.provider_model_options(state.GPT_SOVITS_PROVIDER_SLUG) == state.GPT_SOVITS_MODELS
