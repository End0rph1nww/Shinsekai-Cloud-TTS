# Cloud TTS 插件升级架构说明 v2 —— 适配 Shinsekai PR80 React 插件页

> 目标版本：`0.11.1 → 0.12.0`（向后兼容的新功能，按主程序 semver 约定走 minor）
> 适配基线：Shinsekai 主程序 PR77–PR80 插件分发与 React 插件页架构
> 运行环境：**Tauri 桌面客户端**（Windows = WebView2），非纯浏览器
> 撰写日期：2026-06-10（v2：单界面方案，修正 provider 配置归属与 demo 播放方式）

---

## 1. 目标与约束

| # | 要求 | 实现途径 |
|---|------|----------|
| 1 | 适配 PR80 的 React 插件页 | **单一 `FrontendPageContribution` 自定义页**承载全部设置（见 §4） |
| 2 | 保留原配置界面的**完整功能** | 功能逐项映射（见 §5），不接受降级 |
| 3 | 兼容原 Qt 设置窗口，老用户无感 | 保留 `SettingsUIContribution` 注册；新接口用特性检测，旧宿主跳过 |
| 4 | 新设置页风格：**neobrutalism** | iframe 页样式完全自治（沙箱隔离，不受宿主主题约束），见 §6 |
| 5 | **所有设置集中在一个界面**，不拆 schema 页 | 同 `page_id` 合并机制：schema 置空，config 贡献仅作 API 面（见 §4.3） |

### 配置归属边界（v2 修正）

- **宿主全局设置负责**：`api_key`、`base_api_url` 等鉴权类配置——它们本来就存在宿主
  `api.yaml` 的 TTS extra 里（`state.get_cloud_extra()` / `get_qwen_extra()` /
  `get_gpt_sovits_extra()`），由宿主客户端的全局 TTS 设置页调用。插件页**不重复提供**。
- **插件页负责**：`PLUGIN_STATE_KEYS` 全集（每角色映射、GPT-SoVITS 推理参数、约束开关）
  + 模型/默认音色等插件域参数 + 音色绑定/克隆/导入导出/约束编辑工作流。

---

## 2. 主程序 PR80 插件 UI 能力盘点（事实依据，已逐条核实源码）

### 2.1 贡献类型（`sdk/types.py`、`sdk/register.py:187-230`）

| 贡献类型 | 注册方法 | 渲染方式 | 本插件用法 |
|---|---|---|---|
| `SettingsUIContribution` | `register_settings_ui()` | PySide6 QWidget（Qt 设置窗口） | **保留，老路径** |
| `FrontendConfigContribution` | `register_frontend_config_page()` | React 原生 schema 表单 | **不渲染表单**，仅作 load/save + actions 的 API 面 |
| `FrontendPageContribution` | `register_frontend_page()` | iframe 嵌入插件静态页 | **唯一界面**，承载全部设置 |

### 2.2 支撑单界面方案的四个关键机制

1. **同 `page_id` 合并**（`frontend_bridge_core/plugin_ui.py::_frontend_page_payload`）：
   iframe 页与 config 贡献共用 `page_id` 时，bridge 把 `values`（`load_values()` 结果）
   合并进页 payload，且 config / actions 两条路由对该 `page_id` 生效。
2. **iframe 独占渲染**（`PluginDetailPanel.tsx:160-174`）：页有 `frontendUrl` 时宿主只渲染
   iframe，schema 即使非空也不会被宿主画成表单——schema 置空即可得到"一个界面包含所有设置"。
3. **HTTP 路由**（`frontend_bridge_core/handler.py`）：
   - 读：`GET /api/plugins/{pluginId}/ui`（含合并后的 `values`）
   - 写：`POST /api/plugins/{pluginId}/ui/{pageId}/config`（body → `save_values(values)`）
   - 动作：`POST /api/plugins/{pluginId}/ui/{pageId}/actions/{actionId}`（body=当前值，返回 action 的 dict）
   - iframe 入口/静态资源：`GET /api/plugins/{pluginId}/frontend/{pageId}/...`（仅 entry 目录内；入口 URL 自带 `?pluginId=&pageId=`）
   - **本地媒体直出**：`GET /data/...`（`handler.py:325`，`data/` 下任意文件直接静态服务）
     与 `GET /api/media?path=...` —— **demo 试听的关键**，见 §5。
4. **iframe 沙箱与同源**：`sandbox="allow-forms allow-same-origin allow-scripts"`，与
   bridge 同源 → 页面 JS 可直接 `fetch` 上述全部路由、`<audio>` 可直接挂 `/data/...` URL。

### 2.3 Tauri 环境下 iframe 可用的能力（v2 修正）

- **标准 Web API 全量可用**：`<input type="file">` 在 WebView2 中弹**原生文件选择框**，
  `FileReader` 读取所选文件内容——参考音频与导入 JSON 都走这条路，不需要手填路径。
- **Tauri IPC 不可用**：沙箱 iframe 拿不到 `__TAURI__`（IPC 仅注入主窗口 webview）。
  不构成限制——文件进出全部经 bridge HTTP 完成（上传走 action，下载走 `/api/download`）。

### 2.4 Qt 路径现状

`core/plugins/plugin_host.py` 仍收集 `SettingsUIContribution`，
`ui/settings_ui/tabs/plugin_tab.py` 仍渲染，`webui_qt.py` 入口未删。
**老用户链路在 PR80 后完整存活，本插件无需为其改动一行。**

---

## 3. 插件现状盘点

```
cloud_tts/
├── plugin.py            # 入口：注册 3 个 TTS adapter + Qt 设置页
├── state.py    (1853行) # 配置持久化、provider 常量、每角色 prompt 约束存储
├── settings.py (2031行) # Qt 设置页（QWidget），「逻辑+UI」混写
├── adapter.py / qwen_adapter.py / gpt_sovits_adapter.py
├── host_hook.py / prompt_hook.py
```

升级不得丢失的功能清单（来源 `settings.py` 全量方法扫描）：

- **A. Provider 切换与插件域参数**：编辑目标 provider 切换、模型选择、默认音色、
  Qwen 语言类型、GPT-SoVITS 媒体格式/语言/推理参数（`PLUGIN_STATE_KEYS` 中 gpt_sovits_* 全集）
  ——*鉴权类（key/url）按 §1 边界归宿主全局设置*
- **B. 每角色音色绑定**：角色 → voice ID 映射 + 音色版本记录（`voice_id_versions`）
- **C. 参考音频克隆工作流**：本地参考音频、参考文本、参考音频语言、克隆、demo 试听、
  打开音频目录
- **D. 音色导入/导出**：JSON payload（含版本记录）导出、导入并绑定目标角色
- **E. GPT-SoVITS 每角色 profile**：服务端参考音频路径 / 模型路径
- **F. Prompt 语气约束**：全局开关 + 语气标签保护 + 每角色约束版本
  （`data/plugins/{id}/prompt_constraints/{角色}.json`，内置 zh/ja/yue/en）

---

## 4. 升级架构：单界面三层

```
┌────────────────────────────────────────────────────────────┐
│                  宿主 Shinsekai（Tauri 客户端）              │
│  ┌──────────────┐               ┌────────────────────────┐ │
│  │ Qt 设置窗口   │               │ React 插件详情页（PR80） │ │
│  │ webui_qt.py  │               │   单个 iframe 标签页     │ │
│  └──────┬───────┘               └───────────┬────────────┘ │
└─────────┼───────────────────────────────────┼──────────────┘
          │ QWidget                            │ iframe(同源)
┌─────────┼───────────────────────────────────┼──────────────┐
│         ▼                                   ▼              │
│  ┌─────────────┐                 ┌──────────────────────┐  │
│  │ settings.py │                 │ frontend/index.html  │  │
│  │ (Qt 兼容层， │                 │ (neobrutalism 单页，  │  │
│  │  保持现状)   │                 │  含全部设置+工作台)    │  │
│  └──────┬──────┘                 └──────────┬───────────┘  │
│         │              fetch /ui /config /actions /data    │
│         │                                   │              │
│         │            ┌──────────────────────▼───────────┐  │
│         │            │ frontend_contrib.py               │  │
│         │            │ FrontendPageContribution(界面)     │  │
│         │            │ +同id FrontendConfigContribution   │  │
│         │            │  (schema=[]，纯 API 面：           │  │
│         │            │   load/save + actions)            │  │
│         │            └──────────────────┬────────────────┘  │
│         ▼                               ▼                  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │            config_service.py (新增，唯一真相源)         │  │
│  └──────────────────────────┬───────────────────────────┘  │
│                             ▼                              │
│              state.py + adapters（不动）      cloud_tts 插件 │
└────────────────────────────────────────────────────────────┘
```

### 4.1 第一层：`config_service.py`（新增，地基）

把 `settings.py` 里的非 UI 逻辑抽成纯函数模块（约 600–800 行迁出）：数据规整
（`_coerce_*` 五件套）、导入导出 payload、音色版本管理、角色列表读取、provider
模型选项推导。**验收：不 import 任何 Qt/浏览器概念；现有 `tests/test_settings_*.py`
改指向 service 层后全绿。**

### 4.2 第二层：Qt 兼容层（最小改动）

`CloudTtsSettingsWidget` 与 `register_settings_ui` 注册保持原样，内部改调
`config_service`。**不引入任何新 SDK 依赖**——老宿主能继续加载的前提。

### 4.3 第三层：React 单界面层

**为什么不需要 schema 页 / 为什么可以"一个界面包含所有设置"：**
`FrontendConfigContribution` 的 schema 只是给宿主渲染表单用的描述；当同 `page_id`
存在 iframe 页时宿主只渲染 iframe（§2.2-2）。因此 schema 置空、只保留
`load_values` / `save_values` / `actions`，config 贡献就退化成一个纯 API 面——
界面 100% 由 `frontend/index.html` 自己画，所有设置集中一页。

**注册（`plugin.py`，特性检测保证老宿主兼容）：**

```python
def initialize(self, register, plugin_root, host) -> None:
    host_hook.install()
    prompt_hook.install()
    register.register_tts_adapter(state.PROVIDER_SLUG, CloudTTSAdapter)
    register.register_tts_adapter(state.QWEN_PROVIDER_SLUG, QwenTTSAdapter)
    register.register_tts_adapter(state.GPT_SOVITS_PROVIDER_SLUG, GPTSoVITSApiAdapter)

    # Qt 路径：原样保留（老用户唯一依赖）
    register.register_settings_ui(SettingsUIContribution(...))  # 现有代码不动

    # React 路径：旧宿主 SDK 没有这些方法/类型，双重防御
    if hasattr(register, "register_frontend_page"):
        try:
            from plugins.cloud_tts.frontend_contrib import build_api_surface, build_page
        except ImportError:
            return  # 旧 SDK 缺新类型时静默跳过
        register.register_frontend_config_page(build_api_surface(plugin_root))  # schema=[]
        register.register_frontend_page(build_page(plugin_root))                # 同 page_id
```

**单页 `page_id = "cloud_tts"` 的 API 契约：**

- `load_values()` → 全量插件配置快照：当前编辑 provider、provider extra 中的插件域字段
  （model / default_voice_id / language_type，**不含 api_key / base_api_url**）、
  `PLUGIN_STATE_KEYS` 全集、角色列表 + 每角色绑定/版本/profile/约束语言摘要。
  *（角色列表在每次 `GET /ui` 时实时生成——load_values 是运行时调用，没有 schema
  注册时冻结的问题，天然支持角色增减。）*
- `save_values(values)` → 全局开关与 provider 插件域参数落盘（写 api.yaml extra 中
  插件域字段 + 插件 state 文件，**不触碰鉴权字段**）。
- **actions**（每角色工作流，浏览器 ⇄ Python 的通道）：

| action_id | 入参 | 返回 | 对应原 Qt 功能 |
|---|---|---|---|
| `list_characters` | — | 角色数组（绑定/版本/profile/约束语言） | `_reload_characters` |
| `bind_voice` | `character, voice_id` | 更新后的角色记录 | 每角色绑定 |
| `upload_reference` | `character, filename, content_b64, text, language` | 落盘路径 + 更新记录 | 参考音频选择（v2：上传替代手填路径，文件存 `data/plugins/cloud_tts/reference_audio/`） |
| `clear_reference` | `character` | 更新记录 | 清除参考音频 |
| `clone_voice` | `character` | `{demo_url, voice_id, version}` | 克隆；`demo_url` 即 `/data/...` 直链（§5） |
| `export_voice` | `character` | 导出 JSON payload | 导出（前端 Blob 下载） |
| `import_voice` | `payload_json` | 导入摘要 | 导入（`<input type="file">` + FileReader 读 JSON） |
| `save_gpt_sovits_profile` | `character, ref_path, model_path` | 更新记录 | E |
| `get_constraints` / `save_constraints` | `character[, store]` | 约束 store | F 每角色部分 |

危险操作（导入覆盖、清除参考）声明 `confirm` + `variant="danger"`，宿主 iframe 外
不弹窗——确认框由页面自绘（neobrutalism 风格的确认卡）。

**`frontend/` 目录（零构建依赖方针）：**

```
cloud_tts/frontend/
├── index.html      # 单页入口：全局设置区 + 角色工作台区
├── studio.css      # neobrutalism 设计令牌 + 组件
└── studio.js       # 原生 ES modules；从 URL query 读 pluginId/pageId 拼 API
```

不引入 React/Vite 构建链：插件以源码 zip 分发（PR78 hash/size 审核），node_modules
会让包从 KB 级膨胀到 MB 级。这个交互量级原生 JS + `<template>` 足够。

---

## 5. 功能映射表（完整性验收清单，v2）

| 原 Qt 功能 | React 落点 | 机制 |
|---|---|---|
| Provider 切换 + 联动显隐 | 单页「全局设置区」 | `save_values` |
| api_key / base_api_url | **宿主全局 TTS 设置**（本来就在 api.yaml extra，宿主页管理） | 不在插件页重复 |
| 模型 / 默认音色 / Qwen 语言类型 | 单页「全局设置区」 | `save_values` 写 extra 插件域字段 |
| GPT-SoVITS 推理参数全集 | 单页「全局设置区」折叠组 | `save_values` |
| Prompt 约束开关、语气标签保护 | 单页「全局设置区」 | `save_values` |
| 每角色 voice ID 绑定 | 单页「角色工作台」卡片 | `list_characters` / `bind_voice` |
| 参考音频选择 | `<input type="file">` 原生选择框 → FileReader → `upload_reference` | **v2：Tauri WebView2 下原生文件框可用，上传落盘替代手填路径** |
| 克隆 + demo 试听 | `clone_voice` 返回 `demo_url`，`<audio src="/data/plugins/cloud_tts/clone_demos/xxx.mp3">` | **v2：demo 完整文件照旧存文件夹（原逻辑不变），经 bridge `/data/` 静态路由直接播放完整文件，零截取零转码** |
| 打开音频所在目录 | 路径展示 + 复制按钮（iframe 无 shell 能力）；Qt 页保留原功能 | 信息不丢 |
| 音色导出 / 导入 | `export_voice` → Blob 下载；`<input type="file">` + FileReader → `import_voice` | action |
| GPT-SoVITS 每角色 profile | 单页「角色工作台」profile 子卡 | action |
| 每角色约束版本（zh/ja/yue/en） | 单页「角色工作台」约束编辑器 | action |

---

## 6. Neobrutalism 设计规范（单页）

iframe 与宿主样式完全隔离，独立设计系统。核心令牌：

```css
:root {
  --nb-bg: #f5f1e8;        /* 米纸底 */
  --nb-surface: #ffffff;
  --nb-ink: #111111;        /* 近黑描边与正文 */
  --nb-accent: #ff6b35;     /* 主行动（克隆/保存） */
  --nb-accent-2: #4d96ff;   /* 次级（试听/导出） */
  --nb-accent-3: #ffd23f;   /* 高亮贴纸（选中角色卡） */
  --nb-danger: #ff3864;     /* 危险（导入覆盖/清除） */

  --nb-border: 3px solid var(--nb-ink);
  --nb-shadow: 5px 5px 0 0 var(--nb-ink);     /* 硬投影，零模糊 */
  --nb-shadow-sm: 3px 3px 0 0 var(--nb-ink);
  --nb-radius: 10px;
}

.nb-card   { background: var(--nb-surface); border: var(--nb-border);
             border-radius: var(--nb-radius); box-shadow: var(--nb-shadow); }
.nb-button { border: var(--nb-border); box-shadow: var(--nb-shadow-sm);
             font-weight: 800; transition: transform 80ms, box-shadow 80ms; }
.nb-button:hover  { transform: translate(-2px,-2px); box-shadow: 5px 5px 0 0 var(--nb-ink); }
.nb-button:active { transform: translate(3px,3px);   box-shadow: 0 0 0 0 var(--nb-ink); }
```

单页布局与守则：

1. **页面纵向两区**：顶部「全局设置」（provider 切换 + 参数组，密度优先、装饰降级）；
   下方「角色工作台」（卡片网格，贴纸感）。粘性子导航条（粗下边框）锚点跳转。
2. **硬投影、零模糊、零渐变**；**按压交互**（hover 上浮 / active 压扁阴影）。
3. 选中角色卡 `--nb-accent-3` 底 + `rotate(-1deg)`；克隆中状态粗斜纹进度条；
   `<audio>` 控件用自绘播放按钮包一层（原生控件风格与 neobrutalism 冲突）。
4. 标题字重 800+；voice ID / 路径用等宽字体。
5. `prefers-color-scheme` 深色令牌组（底 `#1c1a17`、描边 `#f5f1e8`、阴影随描边色）。
6. 表单密集区（GPT-SoVITS 参数）保留粗边框、禁用旋转装饰——可用性优先。

---

## 7. 风险与对策（v2）

| # | 风险 | 对策 |
|---|---|---|
| 1 | 旧宿主加载新插件崩溃 | `hasattr` + `try/except ImportError` 双保险；新类型 import 只出现在 `frontend_contrib.py` |
| 2 | iframe 与 Qt 同时改配置互相覆盖 | `config_service` 写入走读-改-写整文件原子替换；两边保存后重 `load`；页面 `visibilitychange` 时重新拉取 |
| 3 | demo 文件路径含中文/空格导致 `/data/` URL 失效 | `demo_url` 由 Python 侧 `urllib.parse.quote` 生成后返回，前端不自行拼接 |
| 4 | 上传大参考音频（base64 经 JSON body） | 限制 ≤20MB（与各云端 API 上限对齐），超限前端先提示；Python 侧二次校验 |
| 5 | 宿主全局设置未配 key 时插件页操作失败 | `load_values` 返回 `key_configured: bool`（只回布尔不回明文），页面顶部显示引导横幅「请到宿主 TTS 设置配置密钥」 |
| 6 | 插件市场提交（PR80 入口）版本协议 | registry 元数据最低 Shinsekai 版本可保持现值（React 能力是可选增强，老宿主自动跳过注册） |

---

## 8. 实施阶段（建议 4 个 PR）

| 阶段 | 内容 | 版本 | 验收 |
|---|---|---|---|
| P1 | 抽出 `config_service.py`；`settings.py` 改调用；测试迁移 | 0.11.2（patch） | Qt 页全功能回归；`tests/` 全绿 |
| P2 | `frontend_contrib.py` API 面（load/save + 全部 actions）+ 单元测试 | 0.12.0（minor） | curl 级别走通全部路由；老宿主加载无报错 |
| P3 | `frontend/` neobrutalism 单页：全局设置区 + 角色工作台（绑定/上传/克隆/试听/导入导出） | 0.12.x | §5 映射表逐项勾验；Tauri 客户端实测文件框与 `/data/` 试听 |
| P4 | GPT-SoVITS profile + 约束编辑器入页；深色适配；市场提交物料 | 0.13.0 | 通过 PR80 提交入口完成市场提交 |

每阶段独立可发布，任一阶段中止都不损害 Qt 老用户。

---

## 附：本说明核实过的宿主源码位置

- `sdk/types.py` — 四种贡献类型定义
- `sdk/register.py:187-230` — 注册方法
- `frontend_bridge_core/plugin_ui.py` — schema 字段形状、同 page_id 合并（`_frontend_page_payload:395-406`）、iframe 资源服务
- `frontend_bridge_core/handler.py:316-325` — `/api/media` 与 `/data/` 静态路由（demo 直链播放依据）
- `frontend_bridge_core/handler.py:688-711` — config / action 路由
- `frontend/src/features/plugin-manager/PluginDetailPanel.tsx:160-178` — iframe 独占渲染与沙箱
- `core/plugins/plugin_host.py`、`ui/settings_ui/tabs/plugin_tab.py` — Qt 路径存活证明
- 插件侧：`state.py:28-60`（`ADAPTER_CONFIG_KEYS` 含 api_key 等存宿主 api.yaml extra 的证据）、`settings.py:119-133`（`_provider_extra` 读写宿主 extra）
