# Cloud TTS PR80 升级进度跟踪

> **交接说明**：本文件是升级工作的唯一进度真相源。接手的 Agent 请先读
> [UPGRADE-ARCHITECTURE-PR80.md](UPGRADE-ARCHITECTURE-PR80.md)（架构方案 v2，含全部源码依据），
> 再按本文件「当前状态」继续。每完成一项把 `[ ]` 改 `[x]` 并在变更日志追加一行。

## 工作约定

- **仓库**：`D:\Workspace\Assistant\Shinsekai-Cloud-TTS`（GitHub: End0rph1nww/Shinsekai-Cloud-TTS）
- **工作分支**：`upgrade/pr80-react-ui`（从 main 切出；每阶段完成后可独立合回）
- **宿主参照源码**：`D:\Workspace\Assistant\Shinsekai-main-20260606`（PR80 分支工作区）
- **测试命令**（在插件仓库根目录）：`python -m pytest tests/ -v`
  （conftest 需把宿主仓库根加进 sys.path——见 tests/ 现有写法）
- **版本规则**（宿主 CLAUDE.md）：bug 修复=patch；新功能=minor；破坏性=major。
  每次功能提交后更新 `state.py` 的 `PLUGIN_VERSION` 并单独提交
  `bump: version to x.y.z - <描述>`
- **提交信息**：不带 Co-Authored-By 落款（用户要求）
- **红线**：`settings.py` 的 Qt 对外行为不得变化；`plugin.py` 顶部不得 import 新 SDK 类型

---

## P1 — 抽取 config_service.py（目标版本 0.11.2，patch）

- [ ] P1.1 通读 `settings.py`，列出迁出函数清单（写入下方「P1 迁出清单」）
- [ ] P1.2 新建 `config_service.py`：数据规整层（`coerce_voice_id_map` / `coerce_path_map` /
      `coerce_text_map` / `coerce_voice_id_versions` / `coerce_gpt_sovits_profiles` /
      `coerce_voice_records` / `valid_choice` / `as_bool`）
- [ ] P1.3 迁出音色版本管理（`ensure_voice_version` / `ensure_versions_from_selected_map`）
- [ ] P1.4 迁出导入导出（export payload 构建 / import payload 解析与绑定）
- [ ] P1.5 迁出 provider 推导（模型选项 / 默认模型 / provider extra 读写包装）
- [ ] P1.6 迁出角色数据读取（角色列表 / 参考音频与文本查询）
- [ ] P1.7 `settings.py` 改为调用 service，删除迁出副本（行为零变化）
- [ ] P1.8 测试迁移：`tests/test_settings_*.py` 中纯逻辑断言改指向 service；新增 service 单测
- [ ] P1.9 全量测试通过（`python -m pytest tests/ -v`）
- [ ] P1.10 提交 P1 + bump 0.11.2

### P1 迁出清单（P1.1 完成后填写）

（待填）

---

## P2 — frontend_contrib.py API 面（目标版本 0.12.0，minor）

- [ ] P2.1 新建 `frontend_contrib.py`：`build_api_surface()`（`FrontendConfigContribution`，
      schema=[]，load_values/save_values 按架构文档 §4.3 契约）
- [ ] P2.2 实现 9 个 action（list_characters / bind_voice / upload_reference / clear_reference /
      clone_voice / export_voice / import_voice / save_gpt_sovits_profile / get_constraints+save_constraints）
- [ ] P2.3 `build_page()`（`FrontendPageContribution`，entry=frontend/index.html，同 page_id）
- [ ] P2.4 `plugin.py` 注册：`hasattr` + `try/except ImportError` 双重防御（架构文档 §4.3 代码）
- [ ] P2.5 `load_values` 返回 `key_configured` 布尔（不回明文 key）
- [ ] P2.6 新增 `tests/test_frontend_contrib.py`（load/save 往返、每个 action 入出参）
- [ ] P2.7 旧宿主兼容验证：模拟无新方法的 register 对象，initialize 不抛错
- [ ] P2.8 在 PR80 宿主里实测：`GET /api/plugins/{id}/ui` 返回合并 payload；config/action 路由可用
- [ ] P2.9 提交 P2 + bump 0.12.0

---

## P3 — neobrutalism 单页前端（目标版本 0.12.x）

- [ ] P3.1 `frontend/index.html` 骨架：全局设置区 + 角色工作台两区 + 粘性锚点导航
- [ ] P3.2 `frontend/studio.css`：设计令牌（架构文档 §6）+ 卡片/按钮/表单组件
- [ ] P3.3 `frontend/studio.js`：API 客户端（从 URL query 读 pluginId/pageId；fetch /ui /config /actions）
- [ ] P3.4 全局设置区落地（provider 切换联动、模型/默认音色、GPT-SoVITS 参数折叠组、约束开关）
- [ ] P3.5 角色工作台：角色卡网格 + 绑定 voice ID
- [ ] P3.6 参考音频上传（`<input type="file">` + FileReader → upload_reference）+ 清除
- [ ] P3.7 克隆 + demo 试听（`/data/` 直链 `<audio>`，自绘播放控件）
- [ ] P3.8 导入导出（Blob 下载 / FileReader 读 JSON）
- [ ] P3.9 自绘确认卡（danger 操作），无 key 引导横幅（key_configured=false 时）
- [ ] P3.10 Tauri 客户端实测：文件框、试听、保存往返、`visibilitychange` 重拉
- [ ] P3.11 提交 P3 + bump

---

## P4 — 收尾与市场提交（目标版本 0.13.0）

- [ ] P4.1 GPT-SoVITS 每角色 profile 编辑入页
- [ ] P4.2 每角色约束版本编辑器（zh/ja/yue/en）入页
- [ ] P4.3 深色模式适配（prefers-color-scheme 第二套令牌）
- [ ] P4.4 §5 功能映射表逐项勾验（对照架构文档）
- [ ] P4.5 README / CHANGELOG 更新
- [ ] P4.6 市场提交物料（截图、描述、最低 Shinsekai 版本声明）
- [ ] P4.7 通过 PR80 提交入口完成市场提交
- [ ] P4.8 提交 P4 + bump 0.13.0

---

## 当前状态

- **进行中**：P1
- **下一步**：P1.1 通读 settings.py 填写迁出清单

## 变更日志

| 日期 | 完成项 | 提交 | 备注 |
|---|---|---|---|
| 2026-06-10 | 架构文档 v2、本进度文件建立 | — | 分支尚未创建 |
