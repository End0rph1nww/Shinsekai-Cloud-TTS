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

### 双 Provider 支持

- 通过 `register_tts_adapter` 注册 `minimax-tts` 和 `qwen-tts` 两个 TTS 适配器。
- 主菜单 API 设置页显示当前选中 TTS 引擎的 API KEY 和 Base URL；切换引擎后字段自动切换。
- 设置页顶部「TTS Provider 配置」下拉框可独立切换编辑 MiniMax 或 Qwen3 的参数，**不影响主 API 页当前选中项**。
- model 和 default_voice_id 按 provider 分别保存到 `api.yaml` 的 `tts_extra_configs.{provider_slug}`。
- 禁用插件时，两个引擎均从 TTS 列表移除；当前引擎若为二者之一则清为 `none`。

### MiniMax

- 模型：`speech-2.8-hd` / `speech-2.8-turbo` / `speech-2.6-hd` / `speech-2.6-turbo`
- 语音克隆 API：`/voice_clone`（需 `imageio-ffmpeg` 转换音频格式）
- 提示词约束：运行时向 system prompt 顶部注入 MiniMax 语气标签约束块
- 语气标签保护：拦截主程序 `remove_parentheses()`，保护 `(laughs)`、`(sighs)` 等 19 种标签不被删除
- 提示词模板：内置中文、日语、粤语、英语四套固定母版，每个角色首次打开自动生成同语种默认版本

### Qwen3 TTS

- 单一 VC 模型 `qwen3-tts-vc-2026-01-22`，合成与声音复刻共用（API 要求二者必须一致）
- 无系统音色，voice 只能通过声音复刻 API `/services/audio/tts/customization` 生成
- 声音复刻直接上传原始音频（mp3 / wav / m4a / flac），无需 `imageio-ffmpeg` 转换
- 合成语言下拉框支持中文、英语、日语、韩语、法语等 10 种语言
- **不注入提示词约束**，不使用语气标签保护（仅 MiniMax 走这套机制）

### Voice ID 管理

- 按 provider 分目录存储：`minimax-tts/voices/` 和 `qwen-tts/voices/`
- 查找顺序：角色绑定 voice_id → 默认兜底 voice_id → 已缓存的声音复刻 voice_id
- 角色 voice_id 支持多版本历史管理
- 旧版共享 `voices/` 目录数据在首次加载时自动迁移到 `minimax-tts/voices/`（Qwen 不受影响）

### 提示词模板系统（仅 MiniMax）

- 内置中文、日语、粤语、英语四套固定母版，以 `<<<CLOUD_TTS_TONE_CONSTRAINT_START>>>` / `<<<CLOUD_TTS_TONE_CONSTRAINT_END>>>` 标记包裹
- 每个角色首次打开自动生成四套同语种默认版本
- `source="default"` 的版本跟随母版同步更新；手动保存后变为 `source="manual"`，停止同步
- 运行时注入语言**跟随主程序当前语音语言**，不受设置页模板语言下拉框影响
- 「重置默认模板」按钮对所有角色开放，按当前选中的语言版本重置为硬编码原始内容

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

修改 `plugins.yaml` 后**必须重启 Shinsekai**。插件 SDK 只在程序启动时读取插件清单。

## 依赖说明

Shinsekai 主程序已包含的基础依赖：

- `requests`
- `PySide6`
- `pyyaml`

本插件额外需要的依赖（仅 MiniMax 语音克隆需要）：

- `imageio-ffmpeg>=0.6.0`

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
- **Qwen3 TTS**：填写 `DashScope API KEY` 和 `DashScope Base URL`
  - 国内端点：`https://dashscope.aliyuncs.com/api/v1`
  - 国际端点：`https://dashscope-intl.aliyuncs.com/api/v1`
  - **重要**：声音复刻和语音合成必须使用同一端点，否则复刻生成的 voice 在合成时会报 400 `Invalid voice specified`

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
- 功能开关：提示词约束、语气标签保护（状态按钮，修改即时生效）
- 提示词模板：中文、日语、粤语、英语四套母版

**Qwen3 配置项**：
- 模型：固定 `qwen3-tts-vc-2026-01-22`（合成与声音复刻共用）
- 默认 voice_id：角色未绑定时使用的兜底 voice_id
- 角色 voice_id：按角色绑定 voice_id，支持多版本历史
- 合成语言：中文、英语、日语、韩语、法语等 10 种

插件设置页**不提供全局保存按钮**。模型、默认 voice_id、角色 voice_id、本地参考音频、参考音频语言和开关在修改时自动保存。

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
- `target_model` 固定使用 `qwen3-tts-vc-2026-01-22`（API 要求复刻与合成模型一致）
- `preferred_name` 由插件自动从音频路径生成纯字母标识（API 不接受数字/下划线/中文）
- 参考：[Qwen Voice Cloning](https://www.alibabacloud.com/help/zh/model-studio/voice-cloning-user-guide)

## 本地数据位置

```
data/plugins/com.shinsekai.cloud_tts/
├── config.json                        # 插件行为设置
├── prompt_constraints/                # 提示词模板（按角色分文件）
│   ├── 默认模板.json                  # 四语言母版
│   └── {角色名}.json                  # 各角色提示词模板
├── minimax-tts/voices/               # MiniMax voice_id 数据
│   ├── _defaults.json                # 默认兜底 voice_id
│   └── {角色名}.json                  # 角色绑定 voice_id
└── qwen-tts/voices/                  # Qwen voice_id 数据
    ├── _defaults.json
    └── {角色名}.json
```

API KEY 和 Base URL 由主程序保存到 `data/config/api.yaml`：

```yaml
tts_extra_configs:
  minimax-tts:
    api_key: ...
    base_api_url: ...
    model: speech-2.8-hd
    default_voice_id: ...
  qwen-tts:
    api_key: ...
    base_api_url: ...
    model: qwen3-tts-vc-2026-01-22
    default_voice_id: ...
    language_type: Chinese
```

## 数据迁移

插件首次加载时自动执行以下迁移（均**只复制不删除**，不会覆盖已有数据）：

| 迁移 | 源位置 | 目标位置 |
|------|--------|----------|
| API 配置 | `tts_extra_configs["cloud-tts"]` | `tts_extra_configs["minimax-tts"]` |
| 插件数据目录 | `data/plugins/com.shinsekai.minimax_tts/` | `data/plugins/com.shinsekai.cloud_tts/` |
| 包内配置 | `plugins/cloud_tts/config.json` | `data/plugins/...cloud_tts/config.json` |
| API 行为参数 | `api.yaml` 中的 model/voice_id 等 | 插件 `config.json` |
| 旧 voice 文件 | `plugins/minimax_tts/voices/`、`plugins/cloud_tts/voices/` | `data/plugins/...cloud_tts/voices/` |
| 共享 voice 目录 | `data/plugins/...cloud_tts/voices/` | `data/plugins/...cloud_tts/minimax-tts/voices/` |

旧版 `prompt_constraints.json` 全局约束也自动迁移为 per-character 版本管理格式。

## 实现原理

### Monkey-Patch 系统

插件通过运行时替换（monkey-patch）主程序的四个关键方法来实现提示词注入和语气标签保护，**不修改主程序代码**：

| Hook | 目标方法 | 触发时机 | 作用 |
|------|----------|----------|------|
| `_patch_api_save` | `ApiSettingsTab._on_save` | API 设置页保存后 | 同步模板中的约束块 |
| `_patch_template_restore` | `TemplateSettingsTab.restore_last_launch_session` | 模板页恢复上次会话 | 同步模板中的约束块 |
| `_patch_template_generate` | `TemplateSettingsTab._on_generate` | 模板页生成后 | 同步模板中的约束块 |
| `_patch_text_processor` | `TextProcessor.remove_parentheses` | 主程序清理括号时 | 保护 MiniMax 语气标签 |

插件禁用时 `uninstall()` 将所有替换的方法还原为原始版本。

### 提示词注入流程

```
主程序保存/恢复/生成模板
    → prompt_hook 拦截
    → 判断是否 MiniMax + 约束开关开启
    → 否：清除已有约束块
    → 是：遍历选中角色 → 读取各角色当前语音语言对应的约束模板
           → 合并多角色约束（单角色直接包裹，多角色加 guard 分列）
           → 用 <<<MARKER>>> 包裹注入到 system prompt 顶部
```

### 语气标签保护流程

```
主程序 remove_parentheses 被调用
    → prompt_hook 拦截
    → 保护开关开启？
    → 是：protect_tone_tags() 把 19 种标签替换为无括号占位符
           → 原方法执行（占位符不受影响）
           → restore_tone_tags() 占位符还原
    → 否：直接执行原方法
```

## 运行说明

- 合成音频写入 `cache/audio/`，除非主程序传入明确输出路径。
- adapter 从 `tts_extra_configs.{provider_slug}` 读取 API KEY 和 Base URL。
- 修改 `plugins.yaml` 后需要重启 Shinsekai；修改 API 或插件设置后需要重启聊天进程。
- 禁用插件时，两个 TTS 引擎均从列表移除；当前引擎若为二者之一则清为 `none`。
- 提示词约束注入仅在主程序当前 TTS 引擎为 MiniMax 且插件启用时生效。

## 常见问题

### 通用

- **API KEY 为空**：先到主菜单 API 设置页选择对应 TTS 引擎，填写 API KEY 并保存。
- **没有可用 voice**：为角色绑定 voice_id、设置默认兜底 voice_id，或上传本地参考音频进行声音复刻/克隆。
- **API 设置页看不到引擎**：确认 `plugins.yaml` 已加入插件入口并重启 Shinsekai。
- **设置已保存但聊天使用旧声音**：重启聊天进程让 TTS adapter 重新读取配置。
- **模板里没有约束块**：确认主菜单 API 页选择了 MiniMax TTS 并保存；确认设置页提示词约束开关已开启。
- **切换 provider 后配置混乱**：模型和默认 voice_id 按 provider 独立存储，切换「TTS Provider 配置」下拉框不会影响对方的数据。

### MiniMax

- **音频转换失败 / 声线克隆上传失败**：安装 `imageio-ffmpeg`：`runtime\python.exe -m pip install -r plugins\cloud_tts\requirements.txt`
- **语气标签被删除**：确认设置页语气标签保护开关已开启（状态按钮显示「已开启，点击关闭」）。
- **提示词约束不生效**：确认主菜单 API 页 TTS 引擎选择了 MiniMax 并保存；确认设置页提示词约束开关已开启；重启聊天进程。

### Qwen3

- **声音复刻 400 `preferred_name is invalid`**：此问题已在 0.10.1 修复。如果仍出现，请更新插件到最新版本。
- **合成 400 `Invalid voice specified`**：声音复刻和合成使用了不同的 Base URL 端点。请确保两处使用同一端点（国内或国际），并在同一端点重新进行声音复刻。
- **合成 404**：检查 Base URL 路径是否正确，应为 `https://dashscope.aliyuncs.com/api/v1` 或 `https://dashscope-intl.aliyuncs.com/api/v1`，末尾不要带其他路径。
