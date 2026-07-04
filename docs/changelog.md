# 更新日志

## v2.0.0 — 2026-07-04

### 重大变更

- **架构迁移**：从 MaiBot 旧 API（`BaseCommand` / `BaseEventHandler` / `ConfigField`）迁移至 `maibot_sdk` 新 API（`MaiBotPlugin` + `@Command` + `@EventHandler` + `PluginConfigBase`）
- **配置重构**：配置文件改为四层嵌套模型（plugin / commands / security / challenge），由 pydantic 强类型验证
- **清单升级**：`_manifest.json` 升级至 v2 格式，补齐全部必填字段

### 新增功能

- **配置热更新**：`on_config_update` 支持 `db_path` 变更时自动重新初始化数据库，CD 时间等动态读取
- **CD 缓存清理**：`on_unload` 时清空 `_cd_cache`，插件重载后不再残留旧 CD 状态
- **每日定时任务**：异步 `_daily_loop` 替代旧版循环，支持 `isalive` 不活跃惩罚

### Bug 修复

- 修复命令执行成功但消息未发送到 QQ 的问题（`_manifest.json` 中 `capabilities` 值修正为 `send.text` / `send.image`）
- 修复群主执行 toggle 返回「权限不足」的问题（NapCat 适配器未注入 `user_role`）
- 修复 yinpa 返回「无法解析命令」的问题（旧版 toggle handler 二次 regex 误判）
- 修复 `config_version` 缺失导致插件加载失败的问题
- 修复 `on_load` 失败 AttributeError（`ctx.paths` 在安装的 SDK 版本中未实现）
- 修复 toggle 返回「无法解析命令」（`raw_message` 键不存在，改用 `text` 键）
- 修复日 @ 用户 / 嗦 @ 用户 命令未拦截的问题（@ 解析改用 `_parse_at_target` 从 raw_message 段提取）
- 修复 `get_group_member_list` 废弃导致群主/管理检测失效的问题

### 移除

- 删除 `__init__.py`（新 SDK 不需要）
- 删除 `utils.py`（模板文件，从未使用）
- 删除 BaseCommand / BaseEventHandler 相关代码

---

## v1.0.0 — 初始版本

从 nonebot-plugin-impart 移植至 MaiBot 平台的初始版本。

- 使用 MaiBot 旧 API（`BaseCommand` / `BaseEventHandler` / `ConfigField`）
- 包含全部 9 个命令：帮助、查询、排行榜、打胶、嗦、PK、透群友、开关银趴、注入查询
- 登神挑战系统
- 排行榜分群过滤
- 反透机制
