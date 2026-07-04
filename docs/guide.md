# 使用指南

## 简介

**maibot-plugin-impart** 是基于 MaiBot 平台的群聊互动插件，提供 PK 对决、打胶、排行榜等群内娱乐功能。本插件从 nonebot-plugin-impart 移植而来，保留了全部功能并适配了 MaiBot 的组件化架构。

## 环境要求

- Python >= 3.10
- MaiBot >= 1.0.0
- maibot_sdk >= 2.5.1
- SQLAlchemy >= 2.0.0
- aiosqlite >= 0.17.0
- Pillow >= 9.0.0

## 安装

### 手动安装

将 `maibot-plugin-impart` 目录放入 MaiBot 的 `plugins/` 目录下，然后安装依赖：

```bash
pip install sqlalchemy aiosqlite Pillow
```

### 依赖配置

插件的依赖声明在 `_manifest.json` 中，Host 会自动检查：

```json
{
  "dependencies": [
    {"type": "python_package", "name": "sqlalchemy", "version_spec": ">=2.0.0"},
    {"type": "python_package", "name": "aiosqlite", "version_spec": ">=0.17.0"},
    {"type": "python_package", "name": "Pillow", "version_spec": ">=9.0.0"}
  ]
}
```

## 配置

插件首次加载时会自动在插件目录下生成 `config.toml`。配置文件分为四个模块：

### plugin — 基本配置

```toml
[plugin]
config_version = "1.0.0"
enabled = true
not_allow = "群内还未开启impart游戏, 请管理员或群主发送\"开始银趴\", \"禁止银趴\"以开启/关闭该功能"
jj_variable = "牛子,牛牛,newnew"
bot_name = "BOT"
db_path = "data/impart.db"
```

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `config_version` | `1.0.0` | 配置文件版本号 |
| `enabled` | `true` | 是否启用插件 |
| `not_allow` | 见上方 | 群功能未开启时的提示消息 |
| `jj_variable` | `牛子,牛牛,newnew` | 牛牛变量名列表，逗号分隔，每次随机选用 |
| `bot_name` | `BOT` | 机器人在消息中的称呼 |
| `db_path` | `data/impart.db` | 数据库文件路径，相对于插件目录 |

### commands — 命令配置

```toml
[commands]
dj_cd_time = 30
pk_cd_time = 6
suo_cd_time = 30
fuck_cd_time = 36
isalive = false
```

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `dj_cd_time` | `30` | 打胶冷却时间（秒） |
| `pk_cd_time` | `6` | PK 冷却时间（秒） |
| `suo_cd_time` | `30` | 嗦冷却时间（秒） |
| `fuck_cd_time` | `36` | 透群友冷却时间（秒） |
| `isalive` | `false` | 是否开启不活跃惩罚，开启后每日凌晨对超过 24h 未活跃的用户随机缩减长度 |

### security — 安全配置

```toml
[security]
ban_id_list = ""
admin_ids = ""
```

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `ban_id_list` | `""` | 禁止名单，逗号分隔的 QQ 号，被列入的用户无法被透 |
| `admin_ids` | `""` | 管理员 QQ 号列表，逗号分隔。留空时仅依赖 OneBot 原生 `role` 判断 |

### challenge — 登神挑战配置

```toml
[challenge]
challenge_threshold = 25
success_threshold = 30
fail_penalty = 5
win_rate_multiplier = 1.25
```

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `challenge_threshold` | `25` | 触发登神挑战的长度阈值（cm） |
| `success_threshold` | `30` | 完成登神挑战的长度阈值（cm） |
| `fail_penalty` | `5` | 挑战失败时缩减的长度（cm） |
| `win_rate_multiplier` | `1.25` | 挑战失败后胜率恢复倍率 |

### 配置热更新

插件支持配置热更新（`on_config_update`），修改 `config.toml` 后无需重启插件即可生效：

- **CD 时间**、**ban 列表**、**admin 列表** 在每次命令执行时从 `self.config` 动态读取，天然支持热更新
- **数据库路径**（`db_path`）变更时，插件会自动重置数据库引擎并重新初始化，无需重启

## 命令列表

### 管理员命令

| 命令 | 权限 | 说明 |
|------|------|------|
| `开启银趴` / `开始银趴` / `开启impart` / `开始impart` | `owner` / `admin` | 开启当前群的银趴功能 |
| `关闭银趴` / `禁止银趴` / `关闭impart` / `禁止impart` | `owner` / `admin` | 关闭当前群的银趴功能 |

权限判断顺序：先检查 OneBot 原生 `sender.role`（owner / admin），再 fallback 到配置中的 `admin_ids` 列表。

### 用户命令

| 命令 | 别名 | 说明 |
|------|------|------|
| `银趴帮助` | `impart帮助`、`银趴介绍`、`impart介绍` | 显示全部命令的使用说明 |
| `查询` | — | 查询 @ 用户的牛牛长度（未 @ 时查自己） |
| `jj排行榜` | `jjrank`、`jj排名`、`jj榜单`、`牛牛排行榜`、`牛牛排名`、`牛牛榜单` | 输出前 5 / 后 5 排名柱状图，附带自身排名（分群过滤） |
| `打胶` | `开导` | 随机增加自己的牛牛长度，默认 CD 30 秒 |
| `嗦` | `嗦牛子` | 增加 @ 用户的长度（未 @ 时为自己），默认 CD 30 秒 |
| `pk` | `对决` | 与 @ 用户进行对决，胜率决定胜负，默认 CD 6 秒 |
| `透群友` | `日群友`、`日`、`透` | 与 @ 用户互动，生成随机注入量，默认 CD 36 秒 |
| `注入查询` | `摄入查询`、`射入查询` | 查询 @ 用户的被注入量，后接 `历史` / `全部` 查看折线图 |

## 核心机制

### PK 胜率系统

- 初始胜率为 50%
- 胜利方胜率 -1%，失败方胜率 +1%
- 胜率影响后续 PK 的胜负概率

### 登神挑战

当用户牛牛长度达到 25cm 时，自动触发「登神挑战」：

| 状态 | 条件 | 效果 |
|------|------|------|
| 挑战开始 | 25cm ≤ length < 30cm | 胜率变为 80%，锁定打胶和嗦指令 |
| 挑战成功 | length ≥ 30cm | 胜率恢复并 ×1.25，打胶和嗦解锁，获得「牛々の神」称号 |
| 挑战失败 | 挑战中跌回 < 25cm | 长度再减 5cm，胜率恢复并 ×1.25，打胶和嗦解锁 |
| 跌落神坛 | 已完成后再次 < 25cm | 长度再减 5cm，挑战完成标记清除 |

### 反透机制

执行透群友时，根据发起者长度决定行为：

- length > 5cm：必须 @ 指定目标
- 1cm < length ≤ 5cm：50% 概率反透自己（自己给自己注入）
- length ≤ 0：强制反透自己

### 排行榜分群过滤

排行榜只展示当前群内互动过的用户数据，跨群用户互不干扰。图例优先显示用户在群中的昵称，无昵称记录时显示 `用户{QQ号}`。

### CD 冷却

各命令有独立的 CD 时间，配置在 `commands` 模块中。CD 在服务端以内存缓存方式记录，插件卸载时自动清空。

## 数据库

插件使用 SQLAlchemy + aiosqlite 作为数据库引擎，数据库文件默认保存在 `data/impart.db`。

### 表结构

| 表名 | 用途 |
|------|------|
| `userdata` | 用户数据（牛牛长度、胜率、挑战状态） |
| `groupdata` | 群开关状态 |
| `ejaculation_data` | 注入记录（按日期聚合） |
| `user_group` | 用户 — 群关系（排行榜分群过滤） |

### 数据迁移

从 nonebot-plugin-impart 迁移数据：

1. 找到原插件的 `impart.db` 文件
2. 复制到当前配置的 `db_path` 路径下
3. 重启 MaiBot，插件会自动检测并补充缺少的列（通过 `ALTER TABLE`）

数据库表结构与原 NoneBot 版保持完全兼容，无需额外迁移步骤。
