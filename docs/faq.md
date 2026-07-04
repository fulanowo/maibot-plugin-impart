# 常见问题

## 安装与配置

### 插件加载失败，报错 `ModuleNotFoundError`

确认已安装以下依赖：

```bash
pip install sqlalchemy aiosqlite Pillow
```

`maibot_sdk` 由 MaiBot 提供，无需手动安装。如果版本过低，请升级 MaiBot。

### 插件加载成功但没有任何命令响应

检查以下项目：

1. **`_manifest.json` 的能力声明**：确认 `capabilities` 包含 `send.text`（及 `send.image` 如有需要）。旧版可能配置为 `send_message`，会导致能力检查不通过。
2. **群银趴开关**：发送 `开启银趴` 开启当前群功能（需要群主 / 管理员权限）。
3. **插件加载位置**：确认插件目录在 MaiBot 的 `plugins/` 下，且 `config.toml` 和 `_manifest.json` 存在。

### 数据库初始化失败

检查 `config.toml` 中 `db_path` 配置的路径是否可写。插件会自动创建数据目录。如果使用自定义路径，确保父目录存在或具有创建权限。

## 使用问题

### 群主执行 toggle 返回「权限不足」

这是因为 NapCat 适配器未将 `sender.role` 注入 `additional_config`。请更新 `MaiBot-Napcat-Adapter` 到最新版本，或通过以下方式手动修复：

1. 在适配器的 `message_codec.py` 中找到 `build_message_dict`
2. 在 `additional_config` 中添加 `user_role` 字段：

```python
user_role = sender.get("role") or ""
additional_config = {"self_id": self_id, "user_role": user_role}
```

3. 重启 MaiBot

### 命令返回「未开启」但群功能已打开

确认群 ID 正确——私聊中群 ID 为 0，所有命令都会返回「未开启」。请确保在群聊中使用。

### 图片发送失败（排行榜 / 注入折线图）

检查 `_manifest.json` 的 `capabilities` 是否包含 `send.image`。如果不包含，添加后重启 MaiBot：

```json
"capabilities": ["send.text", "send.image"]
```

### 排行榜只显示「数据不足」

排行榜使用 `user_group` 表按群过滤，只显示在**当前群内互动过**的用户。要增加数据：

- 在本群使用打胶、PK、嗦、透群友等命令
- 让群内其他用户也互动起来
- 排行榜要求至少 5 个用户参与过

### 透群友时「该用户无法被透」

该用户的 QQ 号在 `config.toml` 的 `security.ban_id_list` 中。如需解除限制，从中移除该 QQ 号即可。

### 修改 `config.toml` 后需要重启吗？

大部分配置不需要：

- **CD 时间**、**ban 列表**、**admin 列表**：在每个命令执行时动态读取，修改即生效
- **数据库路径**（`db_path`）：插件会自动检测变更并重新初始化数据库，无需重启
- **其他字段**：插件会在 `on_config_update` 中处理，通常无需重启

如果修改后未生效，可以尝试重启 MaiBot。

## 登神挑战

### 如何触发登神挑战？

牛牛长度达到 25cm 时自动触发。可以通过以下方式增长：

- 打胶 / 开导：随机增长（默认 CD 300 秒）
- PK 胜利：增长对方减少量的一半
- 嗦牛子：为目标用户增长

### 登神挑战中能做什么？

挑战中打胶和嗦指令被锁定，只能通过 PK 增长长度。每次 PK 胜利长度增长 rn/2，胜率每次 -1%。

### 如何完成挑战？

当长度 ≥ 30cm 时自动完成。获得「牛々の神」称号，胜率恢复，打胶和嗦解锁。

### 挑战失败了会怎样？

如果挑战中长度跌回 25cm 以下，挑战失败：

- 长度再减 5cm
- 胜率恢复并 ×1.25
- 打胶和嗦解锁

### 完成挑战后还会失败吗？

会。如果已完成后长度再次跌回 25cm 以下，会「跌落神坛」：

- 长度再减 5cm
- 挑战完成标记清除，需要重新挑战

## 开发与调试

### 如何查看插件的运行日志？

MaiBot 控制台会输出 `[mai_plugin_impart]` 前缀的日志。在插件代码中通过 `self.ctx.logger` 输出的日志都会显示在控制台中。

### 插件重载后 CD 为什么没有重置？

这个问题已在 v2.0.0 修复。插件卸载时 (`on_unload`) 会调用 `_cd_cache.clear()` 清空所有 CD 状态，重载后从零开始。

### 数据库文件在哪里？

默认路径为 `maibot-plugin-impart/data/impart.db`，可通过 `config.toml` 的 `plugin.db_path` 修改。

### 如何备份或迁移数据？

直接复制 `impart.db` 文件即可。插件会自动检测旧数据库并补充缺少的列。SQLite 单文件，复制即备份。
