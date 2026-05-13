from __future__ import annotations

import base64
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import requests

from sdk.adapters import TTSAdapter

from plugins.cloud_tts import state


def _hex_to_alpha(hex_str: str) -> str:
    """将 hex 字符串映射为纯小写字母，满足 Qwen preferred_name 只接受字母的要求。"""
    _map = {
        "0": "a", "1": "b", "2": "c", "3": "d", "4": "e",
        "5": "f", "6": "g", "7": "h", "8": "i", "9": "j",
        "a": "k", "b": "l", "c": "m", "d": "n", "e": "o", "f": "p",
    }
    return "".join(_map.get(ch, ch) for ch in hex_str.lower())


class QwenTTSAdapter(TTSAdapter):
    """DashScope / 百炼 Qwen TTS 适配器，支持语音合成和声音复刻。"""

    def __init__(
        self,
        api_key: str = "",
        base_api_url: str = "https://dashscope.aliyuncs.com/api/v1",
        model: str = state.QWEN_DEFAULT_MODEL,
        default_voice_id: str = "",
        voice_id_map: dict[str, str] | str | None = None,
        local_reference_audio_map: dict[str, str] | str | None = None,
        reference_audio_language_map: dict[str, Any] | str | None = None,
        language_type: str = "Chinese",
        audio_format: str = "mp3",
        sample_rate: int = 32000,
        request_timeout: int = 120,
        use_runtime_config: bool = True,
        **_ignored_kwargs: Any,
    ) -> None:
        runtime_cfg: dict[str, Any] = {}
        if use_runtime_config:
            plugin_cfg = state.load_plugin_config(
                state.plugin_data_root(),
                state.QWEN_PROVIDER_SLUG,
            )
            runtime_cfg = dict(plugin_cfg)
            runtime_cfg.update(state.get_qwen_extra())
        if runtime_cfg:
            api_key = runtime_cfg.get("api_key", api_key)
            base_api_url = runtime_cfg.get("base_api_url", base_api_url)
            model = runtime_cfg.get("model", model)
            default_voice_id = runtime_cfg.get(
                "default_voice_id",
                runtime_cfg.get("voice", default_voice_id),
            )
            voice_id_map = runtime_cfg.get("voice_id_map", voice_id_map)
            local_reference_audio_map = runtime_cfg.get(
                "local_reference_audio_map",
                local_reference_audio_map,
            )
            reference_audio_language_map = runtime_cfg.get(
                "reference_audio_language_map",
                reference_audio_language_map,
            )
            language_type = runtime_cfg.get("language_type", language_type)
        self.api_key = self._normalize_api_key(api_key)
        self.base_api_url = (base_api_url or "https://dashscope.aliyuncs.com/api/v1").rstrip("/")
        self.model = self._normalize_choice(model, state.QWEN_MODELS, state.QWEN_DEFAULT_MODEL)
        self.default_voice_id = (default_voice_id or "").strip()
        self.voice_id_map = self._coerce_voice_id_map(voice_id_map)
        self.local_reference_audio_map = self._coerce_local_reference_audio_map(
            local_reference_audio_map
        )
        self.reference_audio_language_map = state.coerce_voice_language_map(
            reference_audio_language_map
        )
        self.language_type = self._normalize_choice(
            language_type,
            tuple(code for code, _label in state.QWEN_LANGUAGE_TYPES),
            "Chinese",
        )
        self.audio_format = audio_format
        self.sample_rate = sample_rate
        self.request_timeout = int(request_timeout or 120)

    @classmethod
    def get_config_schema(cls) -> dict[str, dict]:
        return {
            "api_key": {
                "type": "str",
                "label": "DashScope API KEY",
                "default": "",
                "secret": True,
            },
            "base_api_url": {
                "type": "str",
                "label": "DashScope Base URL",
                "default": "https://dashscope.aliyuncs.com/api/v1",
            },
        }

    def switch_model(self, model_info: Any) -> None:
        if isinstance(model_info, dict):
            vid = str(
                model_info.get("voice")
                or model_info.get("cloud_voice_id")
                or ""
            ).strip()
            if vid:
                name = str(model_info.get("character_name") or "").strip()
                if name:
                    self.voice_id_map[name] = vid
                else:
                    self.default_voice_id = vid

    def _log(self, message: str) -> None:
        print(f"Qwen TTS：{message}", flush=True)

    def generate_speech(self, text, file_path=None, **kwargs):
        api_key_error = self._api_key_error()
        if api_key_error:
            self._log(f"合成失败：{api_key_error}")
            return None
        text_value = str(text or "")
        character_name = str(kwargs.get("character_name") or "").strip()
        if not character_name:
            character_name = "未指定角色"
        self._log(
            f"开始合成：角色={character_name}，"
            f"文本长度={len(text_value)}，模型={self.model}"
        )
        out_path = Path(file_path or f"cache/audio/qwen_tts_{int(time.time() * 1000)}.mp3")
        out_path.parent.mkdir(parents=True, exist_ok=True)

        voice = self._voice_for_request(**kwargs)
        if not voice:
            self._log("合成失败：没有可用的 voice，请先上传参考音频进行声音复刻。")
            return None

        language = self.language_type
        char_lang = self._voice_language_for_character(character_name)
        if char_lang != "auto":
            language = self._voice_language_to_qwen_language_type(char_lang)

        payload: dict[str, Any] = {
            "model": self.model,
            "input": {
                "text": text_value,
            },
            "parameters": {
                "voice": voice,
                "language_type": language,
            },
        }
        self._log(
            f"合成参数：voice={voice}，语言={language}，模型={self.model}"
        )
        self._log("正在请求 DashScope 语音合成接口 /services/aigc/multimodal-generation/generation ...")
        try:
            resp = requests.post(
                f"{self.base_api_url}/services/aigc/multimodal-generation/generation",
                headers=self._json_headers(),
                json=payload,
                timeout=self.request_timeout,
            )
            if not resp.ok:
                body = resp.text[:1000]
                self._log(f"HTTP {resp.status_code}：{body}")
            resp.raise_for_status()
            data = resp.json()
            audio_url = self._extract_audio_url(data)
            if not audio_url:
                raise RuntimeError(
                    f"DashScope 返回为空或格式异常：{json.dumps(data, ensure_ascii=False)[:500]}"
                )
            self._log("接口返回成功，正在下载音频文件...")
            audio_resp = requests.get(audio_url, timeout=self.request_timeout)
            audio_resp.raise_for_status()
            out_path.write_bytes(audio_resp.content)
            abs_path = os.path.abspath(out_path)
            self._log(f"合成完成：{abs_path}")
            return abs_path
        except Exception as exc:
            self._log(f"合成失败：{exc}")
            return None

    def create_cloned_voice_from_file(
        self,
        audio_path: str | Path,
        *,
        character_name: str = "",
        voice_name: str = "",
        target_model: str = "",
    ) -> str:
        """使用本地参考音频进行声音复刻，返回生成的 voice id。"""
        self._ensure_api_key()
        path = state.project_path(audio_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(str(path))
        display_name = character_name or "未命名角色"
        raw_name = (voice_name or "").strip()
        # preferred_name 只接受纯 ASCII 字母（API 要求，数字/下划线/连字符均不接受）
        if raw_name and raw_name.isascii() and re.match(r"^[A-Za-z]+$", raw_name):
            preferred_name = raw_name
        else:
            hex_hash = state.short_hash(str(path), 8)
            preferred_name = _hex_to_alpha(hex_hash)
        # target_model 必须是 VC 模型，不能是 UI 选的 TTS 模型
        target = target_model or state.QWEN_VC_MODEL
        self._log(
            f"开始声音复刻：角色={display_name}，"
            f"voice_name={preferred_name}，target_model={target}"
        )
        # 读取音频并 base64 编码
        audio_bytes = path.read_bytes()
        b64 = base64.b64encode(audio_bytes).decode("ascii")
        # 根据扩展名推断 MIME 类型
        suffix = path.suffix.lower()
        mime_map = {".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4", ".flac": "audio/flac"}
        mime = mime_map.get(suffix, "audio/mpeg")
        data_uri = f"data:{mime};base64,{b64}"
        payload = {
            "model": state.QWEN_VOICE_ENROLLMENT_MODEL,
            "input": {
                "action": "create",
                "target_model": target,
                "preferred_name": preferred_name,
                "audio": {"data": data_uri},
            },
        }
        self._log("正在请求 DashScope 声音复刻接口 /services/audio/tts/customization ...")
        resp = requests.post(
            f"{self.base_api_url}/services/audio/tts/customization",
            headers=self._json_headers(),
            json=payload,
            timeout=self.request_timeout,
        )
        if not resp.ok:
            body = resp.text[:1000]
            self._log(f"HTTP {resp.status_code}：{body}")
        resp.raise_for_status()
        data = resp.json()
        try:
            voice_id = data["output"]["voice"]
        except (KeyError, TypeError) as e:
            raise RuntimeError(
                f"声音复刻响应解析失败：{json.dumps(data, ensure_ascii=False)[:500]}"
            ) from e
        if character_name:
            state.upsert_voice_record(
                character_name,
                voice_id,
                {
                    "source": "qwen_auto_clone",
                    "model": target,
                    "reference_audio_path": str(path),
                },
                selected=True,
                provider_slug=state.QWEN_PROVIDER_SLUG,
            )
        self._log(f"声音复刻完成，voice={voice_id}")
        return voice_id

    def _json_headers(self) -> dict[str, str]:
        return {
            **self._auth_headers(),
            "Content-Type": "application/json",
        }

    def _auth_headers(self) -> dict[str, str]:
        self._ensure_api_key()
        return {"Authorization": f"Bearer {self.api_key}"}

    @staticmethod
    def _normalize_api_key(value: Any) -> str:
        key = str(value or "").strip()
        if key.lower().startswith("bearer "):
            key = key[7:].strip()
        return key

    def _api_key_error(self) -> str:
        if not self.api_key:
            return "API KEY 为空，请先在主菜单 API 设置页选择 Qwen3 TTS，填写 DashScope API KEY 并保存。"
        try:
            self.api_key.encode("ascii")
        except UnicodeEncodeError:
            return "API KEY 包含非 ASCII 字符，请检查是否误粘贴了中文或其他非 ASCII 内容。"
        return ""

    def _ensure_api_key(self) -> None:
        error = self._api_key_error()
        if error:
            raise RuntimeError(error)

    def _voice_for_request(self, **kwargs) -> str:
        character_name = str(kwargs.get("character_name") or "").strip()
        # 角色绑定优先
        mapped = self._voice_id_for_character(character_name)
        if mapped:
            self._log(f"使用角色绑定 voice：{character_name} -> {mapped}")
            return mapped
        # 默认保底
        if self.default_voice_id:
            if character_name:
                self._log(
                    f"角色 {character_name} 未绑定 voice，"
                    f"使用默认保底：{self.default_voice_id}"
                )
            return self.default_voice_id
        return ""

    def _voice_id_for_character(self, character_name: str) -> str:
        if not character_name:
            return ""
        for key, value in self.voice_id_map.items():
            if key.strip().lower() == character_name.strip().lower():
                return str(value or "").strip()
        return ""

    def _voice_language_for_character(self, character_name: str) -> str:
        target = (character_name or "").strip().lower()
        if not target:
            return "auto"
        for key, value in self.reference_audio_language_map.items():
            if key.strip().lower() == target:
                return state.normalize_voice_language_code(value)
        return "auto"

    def _voice_language_to_qwen_language_type(self, code: str) -> str:
        mapping = {
            "zh": "Chinese",
            "ja": "Japanese",
            "en": "English",
            "ko": "Korean",
        }
        return mapping.get(code, "Chinese")

    @staticmethod
    def _extract_audio_url(data: dict[str, Any]) -> str:
        """从 DashScope 响应中提取音频 URL。"""
        # 格式1: {"output": {"audio": {"url": "..."}}}
        try:
            audio = data.get("output", {}).get("audio")
            if isinstance(audio, dict) and audio.get("url"):
                return str(audio["url"])
        except Exception:
            pass
        # 格式2: {"output": {"choices": [{"message": {"audio": {"url": "..."}}}]}}
        try:
            choices = data.get("output", {}).get("choices", [])
            if choices and isinstance(choices, list):
                choice = choices[0]
                content = choice.get("message", {}).get("content", {})
                if isinstance(content, dict):
                    audio = content.get("audio")
                    if isinstance(audio, dict) and audio.get("url"):
                        return str(audio["url"])
        except Exception:
            pass
        # 格式3: {"output": {"data": [{"url": "..."}]}}
        try:
            data_list = data.get("output", {}).get("data", [])
            if data_list and isinstance(data_list, list):
                return str(data_list[0]["url"])
        except Exception:
            pass
        return ""

    @staticmethod
    def _normalize_choice(value: Any, valid: tuple[str, ...], default: str) -> str:
        item = str(value or "").strip()
        if item in valid:
            return item
        lowered = item.lower()
        for candidate in valid:
            if candidate.lower() == lowered:
                return candidate
        return default

    def _coerce_voice_id_map(self, value: dict[str, str] | str | None) -> dict[str, str]:
        if value is None:
            return {}
        raw: Any = value
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return {}
            try:
                raw = json.loads(text)
            except json.JSONDecodeError:
                return {}
        if not isinstance(raw, dict):
            return {}
        out: dict[str, str] = {}
        for key, item in raw.items():
            name = str(key or "").strip()
            vid = str(item or "").strip()
            if name and vid:
                out[name] = vid
        return out

    def _coerce_local_reference_audio_map(
        self,
        value: dict[str, str] | str | None,
    ) -> dict[str, str]:
        if value is None:
            return {}
        raw: Any = value
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return {}
            try:
                raw = json.loads(text)
            except json.JSONDecodeError:
                return {}
        if not isinstance(raw, dict):
            return {}
        out: dict[str, str] = {}
        for key, item in raw.items():
            name = str(key or "").strip()
            path = str(item or "").strip()
            if name and path:
                out[name] = path
        return out

    @staticmethod
    def _clamp_float(value: Any, default: float, minimum: float, maximum: float) -> float:
        try:
            item = float(value)
        except (TypeError, ValueError):
            return default
        return max(minimum, min(maximum, item))
