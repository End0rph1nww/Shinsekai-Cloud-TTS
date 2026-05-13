# Cloud TTS

MiniMax speech-2.x + Qwen3 TTS（DashScope / 百炼）语音合成插件。向 Shinsekai 注册两个 TTS 引擎 `minimax-tts` 和 `qwen-tts`，提供独立的插件设置页，用于配置模型、声音复刻/克隆、voice_id、参考音频语言和提示词约束。

## 插件信息

| 字段 | 内容 |
| --- | --- |
| 插件 ID | `com.shinsekai.cloud_tts` |
| 版本 | `0.10.1` |
| 作者 | `End0rph1nww` |
| 插件入口 | `plugins.cloud_tts.plugin:CloudTtsPlugin` |
| TTS 引擎标识 | `minimax-tts`、`qwen-tts` |
| 插件设置页 | `Cloud TTS` |

## 功能说明

- 通过 `register_tts_adapter` 注册 `minimax-tts` 和 `qwen-tts` 两个 TTS 适配器。
- 主菜单的 API 设置页显示当前选中 TTS 引擎的 API KEY 和 Base URL；切换引擎后字段自动切换。
- **MiniMax**：模型（speech-2.8-hd / speech-2.8-turbo / speech-2.6-hd / speech-2.6-turbo）、默认 voice_id、角色 voice_id、参考音频语言、提示词约束和语气标签保护，均在插件设置页维护。
- **Qwen3 TTS**：单一 VC 模型 `qwen3-tts-vc-2026-01-22`，合成与声音复刻共用。无系统音色，voice 只能通过声音复刻生成。支持多语种合成（中文、英语、日语、韩语、法语等 10 种语言）。
- 设置页顶部「TTS Provider 配置」下拉框可独立切换编辑 MiniMax 或 Qwen3 的参数，不影响主 API 页当前选中项。model 和 default_voice_id 按 provider 分别保存到 `api.yaml`。
- voice_id 查找顺序：角色绑定 voice_id → 默认兜底 voice_id → 已缓存的声音复刻 voice_id。
- 需要生成新 voice_id 时，在角色语音配置里手动上传本地参考音频：MiniMax 调用 `/voice_clone`，Qwen 调用 `/services/audio/tts/customization`，根据当前 provider 自动选择。
- TTS 分段功能已由主程序接管（API 设置页「TTS 分句发送」开关），插件不再自行处理分段。
- 提示词约束和语气标签保护仅对 MiniMax 生效；Qwen 不注入提示词约束，不使用语气标签。
- 提示词模板支持中文、日语、粤语、英语四套固定母版；每个角色也会自动生成四套默认提示词。运行时注入语言跟随主程序当前语音语言。
- 关闭插件时，`minimax-tts` 和 `qwen-tts` 均从 TTS 引擎列表移除。

## 安装方式

将本目录复制到：

```text
plugins/cloud_tts
```

在 `data/config/plugins.yaml` 中加入：

```yaml
- entry: plugins.cloud_tts.plugin:CloudTtsPlugin
  enabled: true
```

修改 `plugins.yaml` 后需要重启 Shinsekai。插件 SDK 只在程序启动时读取插件清单。

## 依赖说明

Shinsekai 主程序已包含的基础依赖：

- `requests`
- `PySide6`
- `pyyaml`

本插件额外需要的依赖：

- `imageio-ffmpeg>=0.6.0`（仅 MiniMax 声音克隆音频转换需要）

```bat
runtime\python.exe -m pip install -r plugins\cloud_tts\requirements.txt
```

`imageio-ffmpeg` 提供内置 `ffmpeg`，用于将参考音频转换为 MiniMax 接受的单声道 32000 Hz wav。Qwen 声音复刻不需要 ffmpeg，直接上传原始音频文件。

## 配置流程

### 1. 启用插件并重启

在 `data/config/plugins.yaml` 中启用插件，重启 Shinsekai。TTS 引擎列表在启动时重建。

### 2. 在主菜单 API 设置页填写凭证

打开主菜单 → API 设置页，在 TTS 区域选择目标引擎：

- **MiniMax TTS**：填写 `MiniMax API KEY` 和 `MiniMax Base URL`（默认 `https://api.minimaxi.com/v1`）
- **Qwen3 TTS**：填写 `DashScope API KEY` 和 `DashScope Base URL`（国内 `https://dashscope.aliyuncs.com/api/v1`，国际 `https://dashscope-intl.aliyuncs.com/api/v1`）

保存后写入 `data/config/api.yaml`：

```yaml
tts_extra_configs:
  minimax-tts:
    api_key: ...
    base_api_url: ...
  qwen-tts:
    api_key: ...
    base_api_url: ...
```

### 3. 进入 Cloud TTS 插件设置页配置参数

打开插件设置页 `Cloud TTS`，通过顶部「TTS Provider 配置」下拉框切换编辑目标。

**MiniMax 配置项**：
- 模型：`speech-2.8-hd` / `speech-2.8-turbo` / `speech-2.6-hd` / `speech-2.6-turbo`
- 默认 voice_id：角色未绑定时使用的兜底 voice_id
- 角色 voice_id：按角色绑定 voice_id，支持多版本历史
- 参考音频语言：用于 MiniMax 语音克隆时识别语言
- 功能开关：提示词约束、语气标签保护
- 提示词模板：中文、日语、粤语、英语四套母版

**Qwen3 配置项**：
- 模型：固定 `qwen3-tts-vc-2026-01-22`（合成与声音复刻共用）
- 默认 voice_id：角色未绑定时使用的兜底 voice_id
- 角色 voice_id：按角色绑定 voice_id，支持多版本历史
- 合成语言：中文、英语、日语、韩语、法语等 10 种

插件设置页不提供全局保存按钮。模型、默认 voice_id、角色 voice_id、本地参考音频、参考音频语言和开关在修改时自动保存。

### 4. 创建 voice_id（声音复刻/克隆）

选择角色 → 配置本地参考音频 → 点击上传按钮。插件根据当前 provider 自动选择 API。

**MiniMax 语音克隆**：
- 源音频要求：mp3 / m4a / wav，时长 10 秒 ~ 5 分钟，不超过 20 MB
- 建议使用干净、单人、少噪音的人声
- 参考：[MiniMax Voice Clone](https://platform.minimax.io/docs/guides/speech-voice-clone)
- 需要 `imageio-ffmpeg` 进行音频转换

**Qwen3 声音复刻**：
- 直接上传原始音频（mp3 / wav / m4a / flac）
- 不需要 ffmpeg 转换
- 生成的 voice_id 同时用于合成和复刻，必须使用同一 VC 模型
- 参考：[Qwen Voice Cloning](https://www.alibabacloud.com/help/zh/model-studio/voice-cloning-user-guide)

## 本地数据位置

API KEY 和 Base URL 由主程序保存到：

```text
data/config/api.yaml
```

插件行为设置保存到：

```text
data/plugins/com.shinsekai.cloud_tts/config.json
```

按 provider 分目录存储 voice 数据：

```text
data/plugins/com.shinsekai.cloud_tts/minimax-tts/voices/
data/plugins/com.shinsekai.cloud_tts/qwen-tts/voices/
```

默认 voice_id 分别保存在各 provider 目录的 `_defaults.json`。

旧版共享 `voices/` 目录数据会在首次加载时自动迁移到 `minimax-tts/voices/`。

## 运行说明

- 合成音频写入 `cache/audio/`，除非主程序传入明确输出路径。
- adapter 从 `tts_extra_configs.{provider_slug}` 读取 API KEY 和 Base URL。
- 修改 `plugins.yaml` 后需要重启 Shinsekai；修改 API 或插件设置后需要重启聊天进程。
- 禁用插件时，两个 TTS 引擎均从列表移除；当前引擎若为二者之一则清为 `none`。

## 常见问题

- **API KEY 为空**：先到主菜单 API 设置页选择对应 TTS 引擎，填写 API KEY 并保存。
- **没有可用 voice**：为角色绑定 voice_id、设置默认兜底 voice_id，或上传本地参考音频进行声音复刻/克隆。
- **MiniMax 音频转换失败**：安装 `imageio-ffmpeg`：`runtime\python.exe -m pip install -r plugins\cloud_tts\requirements.txt`
- **Qwen 声音复刻 400**：检查 Base URL（国内/国际端点需与合成一致），确认参考音频格式正确。
- **API 设置页看不到引擎**：确认 `plugins.yaml` 已加入插件入口并重启 Shinsekai。
- **设置已保存但聊天使用旧声音**：重启聊天进程让 TTS adapter 重新读取配置。
