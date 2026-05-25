from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from plugins.cloud_tts.adapter import CloudTTSAdapter


class DummyResponse:
    def __init__(self, content=b"", json_data=None, status_code=200):
        self.content = content
        self._json_data = json_data or {}
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(response=self)
        return None

    def json(self):
        return self._json_data


def test_minimax_generate_speech_downloads_url_audio(monkeypatch, tmp_path):
    calls = []
    audio_url = "https://audio.example.test/generated.mp3"
    audio_bytes = b"fake mp3 bytes"

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(("POST", url, headers, json, timeout))
        return DummyResponse(
            json_data={
                "base_resp": {"status_code": 0, "status_msg": "success"},
                "data": {"audio": audio_url, "status": 2},
                "extra_info": {"usage_characters": 5},
            }
        )

    def fake_get(url, headers=None, timeout=None):
        calls.append(("GET", url, headers, None, timeout))
        return DummyResponse(content=audio_bytes)

    import plugins.cloud_tts.adapter as adapter_module

    monkeypatch.setattr(adapter_module.requests, "post", fake_post)
    monkeypatch.setattr(adapter_module.requests, "get", fake_get)

    adapter = CloudTTSAdapter(
        use_runtime_config=False,
        api_key="user-platform-key",
        base_api_url="https://api.example.test/v1",
        default_voice_id="voice-1",
        audio_format="mp3",
        request_timeout=17,
    )

    out_path = tmp_path / "speech.mp3"

    result = adapter.generate_speech("hello", file_path=out_path)

    assert result == str(out_path.resolve())
    assert out_path.read_bytes() == audio_bytes
    assert calls[0][0] == "POST"
    assert calls[0][1] == "https://api.example.test/v1/t2a_v2"
    assert calls[0][3]["output_format"] == "url"
    assert calls[1] == ("GET", audio_url, None, None, 17)
