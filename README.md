# MiniMax TTS

MiniMax speech-2.x 语音合成插件。它会向 Shinsekai 注册一个新的 TTS 引擎 `minimax-tts`，并提供独立的插件设置页，用于配置模型、声线克隆、voice_id、合成参数和 Paragraph 段落整段生成。

## 插件信息

| 字段 | 内容 |
| --- | --- |
| 插件 ID | `com.shinsekai.minimax_tts` |
| 版本 | `0.2.0` |
| 作者 | `End0rph1nww` |
| 插件入口 | `plugins.minimax_tts.plugin:MinimaxTtsPlugin` |
| TTS 引擎标识 | `minimax-tts` |
| 插件设置页 | `MiniMax TTS` |

## 功能说明

- 通过 `register_tts_adapter` 注册 `minimax-tts` TTS 适配器。
- 主菜单的 API 设置页只显示 `MiniMax API KEY` 和 `MiniMax Base URL`。
- MiniMax 的模型、voice_id、合成参数、Paragraph 段落整段生成、声线克隆参数和本地声线缓存，都放在插件设置页维护。
- 支持 MiniMax `/t2a_v2`、`/files/upload` 和 `/voice_clone` 接口。
- voice_id 查找顺序为：角色绑定 voice_id、默认兜底 voice_id、已缓存的克隆 voice_id、可选的角色参考音频自动克隆。
- 内置 Paragraph 开关。开启后，普通角色台词只按换行或空行分段，不再按标点拆句，适合让 MiniMax 对较长台词按段落整段生成。
- 只有当插件启用，并且主程序当前 TTS 引擎已经切到 `minimax-tts` 时，插件才会向模板注入 MiniMax 语气标签约束。
- 是否使用 MiniMax 作为主 TTS 引擎，完全由主菜单 API 设置页里的 TTS 引擎选择决定；插件设置页只保存插件行为参数。
- 当用户在插件面板禁用本插件时，`minimax-tts` 不再注册到主菜单 TTS 列表；如果当前主 TTS 仍是 `minimax-tts`，插件会把它清为 `none`，避免下次启动留下失效入口。

## 安装方式

把本目录复制到：

```text
plugins/minimax_tts
```

然后在 `data/config/plugins.yaml` 中加入：

```yaml
- entry: plugins.minimax_tts.plugin:MinimaxTtsPlugin
  enabled: true
```

修改 `plugins.yaml` 后需要重启 Shinsekai。插件 SDK 只会在程序启动时读取插件清单。

## 依赖说明

Shinsekai 主程序原本已经包含插件会用到的基础依赖：

- `requests`
- `PySide6`
- `pyyaml`

本插件额外需要的依赖只有一个，官方根目录 `requirements.txt` 中默认没有：

- `imageio-ffmpeg>=0.6.0`

请在 Shinsekai 项目根目录执行：

```bat
runtime\python.exe -m pip install -r plugins\minimax_tts\requirements.txt
```

`imageio-ffmpeg` 会提供一个内置的 `ffmpeg` 可执行文件。插件上传角色参考音频并创建克隆声线时，会用它把音频转换为 MiniMax 可接受的单声道 32000 Hz wav 文件。

如果没有安装 `imageio-ffmpeg`，但参考音频本身已经是 `.mp3`、`.m4a` 或 `.wav`，并且小于等于 20 MB，插件会直接上传该文件。否则声线克隆上传会失败，并提示安装插件依赖。

## 配置流程

### 1. 启用插件并重启

先在 `data/config/plugins.yaml` 中启用插件，然后重启 Shinsekai。

TTS 引擎列表是在启动时重建的，所以不重启时，API 设置页里可能看不到 `minimax-tts`。

### 2. 先在主菜单 API 设置页填写 API KEY 和 Base URL

打开主菜单设置，进入 API 设置页。

在 TTS 区域选择 MiniMax TTS 引擎。界面上可能显示为 `Minimax Tts`，但内部保存的引擎标识是：

```text
minimax-tts
```

选择该引擎后，API 设置页只需要填写两个 MiniMax 字段：

- `MiniMax API KEY`
- `MiniMax Base URL`

默认 Base URL 是：

```text
https://api.minimaxi.com/v1
```

填写后点击 API 设置页底部的保存按钮。这两个字段会写入 `data/config/api.yaml`：

```yaml
tts_extra_configs:
  minimax-tts:
    api_key: ...
    base_api_url: ...
```

插件设置页不会重复显示 API KEY 和 Base URL。这是为了避免同一组连接凭证在两个页面重复配置。

### 3. 再进入 MiniMax TTS 插件设置页

打开插件设置页 `MiniMax TTS`。

这里配置 MiniMax 的行为参数：

- 模型：`speech-2.8-hd`、`speech-2.8-turbo`、`speech-2.6-hd`、`speech-2.6-turbo`、`speech-02-hd` 或 `speech-02-turbo`。
- 无角色兜底 voice_id：角色没有专用 voice_id 时使用。
- 语言增强：`auto`、`Japanese`、`Chinese`、`Chinese,Yue` 或 `English`。
- 音频格式：`wav`、`mp3` 或 `flac`。
- 采样率、比特率、声道、语速、音量、音高、默认情绪和请求超时。
- 未找到 voice_id 时，是否从角色参考音频自动克隆。
- Paragraph：是否按段落整段生成。默认开启；关闭后会回到 Shinsekai 内置的按标点切分行为。
- 克隆时是否启用降噪、音量归一。
- 自动克隆缓存路径，默认是 `cache/audio/minimax_voice_cache.json`。

插件页底部只有一个 `保存配置` 按钮。点击后只会保存插件行为参数，不会修改主菜单 API 设置页里的 `tts_provider`。

MiniMax 是否成为主程序实际使用的 TTS 引擎，由主菜单 API 设置页保存后的 TTS 引擎状态决定。也就是说：在主菜单选择 `minimax-tts` 并点击保存后，当前系统提示词和后续生成的模板会自动加入 MiniMax 语气标签约束；如果主菜单切换到 GPT-SoVITS、Genie TTS 或 `none` 并点击保存，当前系统提示词里的 MiniMax 语气标签约束会自动移除。插件设置页保存不会修改主 TTS 选择，也不会触发系统提示词注入。

Paragraph 段落整段生成只需要插件启用并打开 Paragraph 开关，不要求主程序 TTS 已切换到 `minimax-tts`。因此它也可以配合本地 TTS 引擎使用；推荐和 MiniMax 一起使用时打开，让较长台词按段落整段生成。

如果主聊天进程已经启动，保存后请重启聊天进程，让 TTS adapter 重新读取最新配置。

### 4. 绑定、导入或创建 voice_id

插件可以通过三种方式获得 voice_id：

- 手动为角色输入或选择 voice_id。
- 点击 `导入 voice_id JSON`，导入已有 voice_id 文件。
- 选择角色后，点击 `上传所选角色参考音频并缓存 voice_id`，用角色参考音频创建 MiniMax 克隆声线。

上传参考音频前，必须先在主菜单 API 设置页保存 `MiniMax API KEY`。插件会从 `characters.yaml` 中读取角色的 `refer_audio_path` 作为参考音频路径。

## 本地数据位置

API KEY 和 Base URL 由主程序保存到：

```text
data/config/api.yaml
```

插件行为设置保存到插件数据目录：

```text
data/plugins/com.shinsekai.minimax_tts/config.json
```

角色 voice_id 记录保存到：

```text
data/plugins/com.shinsekai.minimax_tts/voices/
```

默认 voice_id 保存到：

```text
data/plugins/com.shinsekai.minimax_tts/voices/_defaults.json
```

这些 voice_id 文件属于本地运行数据。发布插件包或上传插件仓库时，不要包含这些文件。

旧版本如果把 voice_id 放在 `plugins/minimax_tts/voices/*.json` 下，插件会在迁移时复制到 `data/plugins/com.shinsekai.minimax_tts/voices/`。迁移只复制，不删除旧文件，避免升级时误伤用户本地声线数据。

## 运行说明

- 默认情况下，合成音频会写入 `cache/audio/`，除非主程序传入了明确的输出路径。
- adapter 会从主程序 API 设置中的 `tts_extra_configs.minimax-tts` 读取 API KEY 和 Base URL。
- 插件设置页只保存行为参数，不保存 API KEY 和 Base URL。
- Paragraph 开关只影响普通角色台词。只要插件启用且 Paragraph 开关打开，它就会按段落处理普通角色台词；系统消息、BGM、CG 和思维链/状态消息仍交给 Shinsekai 内置 handler。
- 禁用插件时，`minimax-tts` 会从主菜单 TTS 引擎列表中消失；如果当前 TTS 引擎仍是 `minimax-tts`，插件会把主 TTS 清为 `none`，避免留下无法注册的旧选择。
- 修改 `plugins.yaml` 后需要重启 Shinsekai。
- 修改 API 设置或插件设置后，如果聊天进程已经启动，需要重启聊天进程让 adapter 重新构造。

## 常见问题

如果合成日志提示 API KEY 为空，请先到主菜单 API 设置页保存 `MiniMax API KEY`。

如果合成日志提示没有可用 voice_id，请为角色绑定 voice_id、设置默认兜底 voice_id、导入 voice_id JSON，或开启从参考音频自动克隆。

如果声线克隆上传提示参考音频需要转换，请安装插件依赖：

```bat
runtime\python.exe -m pip install -r plugins\minimax_tts\requirements.txt
```

如果 API 设置页看不到 MiniMax TTS 引擎，请确认 `data/config/plugins.yaml` 已加入插件入口，并重启 Shinsekai。

如果插件设置已经保存，但当前聊天仍使用旧声音，请重启聊天进程，让 TTS adapter 重新读取最新设置。
