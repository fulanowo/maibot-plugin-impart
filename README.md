# maibot-plugin-impart

_✨ MaiBot 银趴插件 ✨_

基于 [nonebot-plugin-impart](https://github.com/YuuzukiRin/nonebot_plugin_impart) 移植到 MaiBot 平台，保留了全部功能并适配了 MaiBot 的组件化架构。

## 功能介绍

本插件移植自 nonebot-plugin-impart（基于 [nonebot_plugin_impact](https://github.com/Special-Week/nonebot_plugin_impact) 改进的 NoneBot2 ~~银趴~~插件），增添了更多~~让群友眼前一亮的实用~~功能。

### 核心机制

- **PK 胜率系统**：初始胜率 50%，胜利方 -1%，失败方 +1%，影响下一次 PK 胜负概率
- **登神挑战**：jj_length >= 25cm 自动触发，胜率变为 80%，锁定打胶/嗦指令；>= 30cm 挑战成功获得称号；跌出 25cm 则挑战失败并惩罚
- **反透机制**：长度 < 5cm 时执行透群友有 50% 概率被反透（自己给自己注入），长度 <= 0 时必被反透
- **排行榜分群过滤**：排行榜只展示同群互动过的用户数据，图例显示群昵称，无昵称时显示 QQ 号
- **白名单系统**：透群友时自动过滤白名单用户
- **CD 限制**：各指令独立冷却时间
- **不活跃惩罚**：可选功能，超过 24h 未活跃的用户长度减少

## 安装

将 `maibot-plugin-impart/` 目录放入 MaiBot 的插件目录中，确保已安装依赖：

```bash
pip install sqlalchemy aiosqlite Pillow
```

插件首次启动时会自动在数据目录下创建 `config.toml` 配置文件。

## 配置

编辑 `config.toml` 文件：

```toml
[plugin]
enabled = true
db_path = "data/impart.db"
not_allow = "群内还未开启impart游戏，请管理员或群主发送\"开始银趴\"，\"禁止银趴\"以开启/关闭该功能"
jj_variable = "牛子,牛牛,newnew"
bot_name = "BOT"

[commands]
dj_cd_time = 300
pk_cd_time = 60
suo_cd_time = 300
fuck_cd_time = 3600
isalive = false

[security]
ban_id_list = ""

[challenge]
challenge_threshold = 25
success_threshold = 30
fail_penalty = 5
win_rate_multiplier = 1.25
```

| 配置项 | 默认值 | 说明 |
|:-----:|:-----:|:----:|
| `plugin.db_path` | `data/impart.db` | 数据库文件路径 |
| `plugin.jj_variable` | `牛子,牛牛,newnew` | 牛牛变量名列表 |
| `commands.dj_cd_time` | `300` | 打胶冷却时间（秒） |
| `commands.pk_cd_time` | `60` | PK 冷却时间（秒） |
| `commands.suo_cd_time` | `300` | 嗦冷却时间（秒） |
| `commands.fuck_cd_time` | `3600` | 透群友冷却时间（秒） |
| `commands.isalive` | `false` | 是否开启不活跃惩罚 |
| `security.ban_id_list` | `""` | 透群友白名单（逗号分隔的 QQ 号） |

## 指令表

| 指令 | 说明 |
|:----:|:----:|
| `开启银趴` / `禁止银趴` | 管理员/群主开启或关闭插件的群功能 |
| `日` / `透` | 短命令格式，`日@用户` / `透@用户` 等同 `透群友@用户` |
| `日群友` / `透群友` | 与群友互动（可 @ 指定目标）。无 @ 时根据长度：>5cm 提示@指定目标；xnn 时 50% 概率触发反透自注入；≤0 时直接反透 |
| `日群主` / `透群主` / `日管理` / `透管理` | 合并进透群友逻辑，行为等同 `透群友`，不再区分角色前缀 |
| `pk` / `对决` | 与 @ 用户进行牛子对决 |
| `打胶` / `开导` | 增加自己的长度 |
| `嗦牛子` / `嗦` | 增加 @ 用户的长度（未 @ 则为自己） |
| `查询` | 查询 @ 用户的长度（未 @ 则为自己） |
| `jj排行榜` / `jjrank` | 展示前 5/后 5 排名及自己的排名（分群过滤，图例显示群昵称或 QQ 号） |
| `注入查询` | 查询 @ 用户被注入量（后接 `历史`/`全部` 查看折线图，单日也支持出图） |
| `银趴帮助` / `impart帮助` | 显示使用说明 |

## 数据库迁移

如果你先前使用 nonebot-plugin-impart 并想要迁移数据：

1. 找到原插件数据库文件（通常为 `impart.db`）
2. 将其复制到 `config.toml` 中 `plugin.db_path` 配置的路径下（默认 `maibot-plugin-impart/data/impart.db`）
3. 重启 MaiBot 即可

数据库表结构保持 100% 兼容，无需额外迁移步骤。

## 与原插件差异

| 项目 | 原 NoneBot 版 | MaiBot 移植版 |
|:----:|:------------:|:------------:|
| 架构 | NoneBot 2 + OneBot v11 | MaiBot 组件化架构 |
| 命令 | `on_command()` / `on_regex()` | `BaseCommand` 正则匹配 |
| 配置 | `.env` + pydantic Config | `config.toml` + ConfigField |
| 定时任务 | APScheduler | asyncio 协程 |
| 数据库 | SQLAlchemy + aiosqlite | 保持完全兼容 |
| @ 解析 | OneBot 消息段 | Seg 树递归遍历 + 正则 fallback |

## 致谢

- [nonebot-plugin-impart](https://github.com/YuuzukiRin/nonebot_plugin_impart) — 源项目
- [nonebot_plugin_impact](https://github.com/Special-Week/nonebot_plugin_impact) — 原始灵感与代码支持
