# API 参考

## 插件架构

插件采用**单类设计**，所有命令和事件处理器都集中在 `ImpartPlugin` 类中，通过装饰器注册。

```
ImpartPlugin (MaiBotPlugin)
├── 配置模型: ImpartPluginConfig (四层嵌套)
│   ├── PluginSectionConfig       # 基本配置
│   ├── CommandsSectionConfig     # 命令 CD
│   ├── SecuritySectionConfig     # 安全配置
│   └── ChallengeSectionConfig    # 登神挑战
├── 生命周期
│   ├── on_load()                 # 初始化数据库 + 定时任务
│   ├── on_unload()               # 清理资源 + CD 缓存
│   └── on_config_update()        # 热更新配置
├── 辅助方法
│   ├── _get_user_id()            # 提取用户 QQ
│   ├── _get_group_id()           # 提取群号
│   ├── _get_nick()               # 提取昵称
│   ├── _get_role()               # 提取群角色
│   └── _parse_at_target()        # 提取 @ 目标
├── 后台任务
│   └── _daily_loop()             # 每日不活跃惩罚
├── 命令 (9 个)
│   ├── handle_help               # 帮助
│   ├── handle_query              # 查询
│   ├── handle_jjrank             # 排行榜
│   ├── handle_injection_query    # 注入查询
│   ├── handle_dajiao             # 打胶
│   ├── handle_suo                # 嗦牛子
│   ├── handle_toggle             # 开关银趴
│   ├── handle_pk                 # PK / 对决
│   └── handle_yinpa              # 透群友
└── 事件 (1 个)
    └── handle_init               # ON_START
```

## 配置模型

### ImpartPluginConfig

四层嵌套的 Pydantic 配置模型，由 `maibot_sdk` 从 `config.toml` 自动加载。

```python
class ImpartPluginConfig(PluginConfigBase):
    plugin: PluginSectionConfig
    commands: CommandsSectionConfig
    security: SecuritySectionConfig
    challenge: ChallengeSectionConfig
```

在命令 handler 中通过 `self.config` 访问：

```python
self.config.plugin.db_path        # str
self.config.commands.dj_cd_time   # int
self.config.security.ban_id_list  # str
self.config.challenge.threshold   # int
```

### PluginSectionConfig

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `config_version` | `str` | `"1.0.0"` | 配置文件版本号 |
| `enabled` | `bool` | `True` | 是否启用插件 |
| `not_allow` | `str` | 见代码 | 未开启时的提示消息 |
| `jj_variable` | `str` | `"牛子,牛牛,newnew"` | 牛牛变量名列表，逗号分隔 |
| `bot_name` | `str` | `"BOT"` | 机器人称呼 |
| `db_path` | `str` | `"data/impart.db"` | 数据库文件路径 |

### CommandsSectionConfig

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `dj_cd_time` | `int` | `300` | 打胶冷却时间（秒） |
| `pk_cd_time` | `int` | `60` | PK 冷却时间（秒） |
| `suo_cd_time` | `int` | `300` | 嗦冷却时间（秒） |
| `fuck_cd_time` | `int` | `3600` | 透群友冷却时间（秒） |
| `isalive` | `bool` | `False` | 是否开启不活跃惩罚 |

### SecuritySectionConfig

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `ban_id_list` | `str` | `""` | 禁止名单（逗号分隔的 QQ 号） |
| `admin_ids` | `str` | `""` | 管理员 QQ 号列表（逗号分隔） |

### ChallengeSectionConfig

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `challenge_threshold` | `int` | `25` | 登神挑战触发长度（cm） |
| `success_threshold` | `int` | `30` | 登神挑战完成长度（cm） |
| `fail_penalty` | `int` | `5` | 挑战失败惩罚缩减长度（cm） |
| `win_rate_multiplier` | `float` | `1.25` | 挑战失败胜率恢复倍率 |

## 数据库层

### 模块函数

所有数据库操作接收 `db_path` 参数，引擎采用全局懒初始化模式。

| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `init_db(db_path)` | `str` | `None` | 创建表 + 迁移旧列 |
| `reset_engine()` | 无 | `None` | 重置全局引擎（配置变更 / 测试用） |
| `add_new_user(db_path, userid)` | `str, int` | `None` | 创建用户，初始 10cm / 0.5 胜率 |
| `is_in_table(db_path, userid)` | `str, int` | `bool` | 用户是否存在 |
| `get_jj_length(db_path, userid)` | `str, int` | `float` | 获取牛牛长度 |
| `set_jj_length(db_path, userid, length)` | `str, int, float` | `None` | 增减牛牛长度（length 可为负） |
| `get_win_probability(db_path, userid)` | `str, int` | `float` | 获取 PK 胜率 |
| `set_win_probability(db_path, userid, change)` | `str, int, float` | `None` | 调整 PK 胜率 |
| `update_activity(db_path, userid)` | `str, int` | `None` | 更新用户最后活跃时间 |
| `update_challenge_status(db_path, userid)` | `str, int` | `str` | 登神挑战状态机，返回状态码 |
| `check_group_allow(db_path, groupid)` | `str, int` | `bool` | 检查群是否开启银趴 |
| `set_group_allow(db_path, groupid, allow)` | `str, int, bool` | `None` | 设置群开关 |
| `insert_ejaculation(db_path, userid, volume)` | `str, int, float` | `None` | 记录注入量 |
| `get_ejaculation_data(db_path, userid)` | `str, int` | `List[Dict]` | 获取用户全部注入记录 |
| `get_today_ejaculation_data(db_path, userid)` | `str, int` | `float` | 获取用户当日注入量 |
| `punish_all_inactive_users(db_path)` | `str` | `None` | 对所有超过 24h 未活跃的用户缩减长度 |
| `ensure_user_in_group(db_path, userid, groupid, nickname)` | `str, int, int, str` | `None` | 维护用户 — 群关系 |
| `get_group_nickname(db_path, userid, groupid)` | `str, int, int` | `Optional[str]` | 获取用户在群中的昵称 |
| `get_sorted(db_path, group_id)` | `str, int` | `List[Dict]` | 获取指定群内的排行榜（降序） |

### update_challenge_status 返回值

登神挑战状态机返回以下字符串：

| 返回值 | 含义 |
|--------|------|
| `challenge_started_low_win` | 挑战开始，length ≥ 25cm，胜率 ×0.8 |
| `challenge_completed` | 挑战完成，length ≥ 30cm |
| `challenge_failed_high_win` | 挑战中跌出 25cm，胜率 ×1.25，减 5cm |
| `challenge_success_high_win` | 挑战中达到 30cm，胜率 ×1.25 |
| `is_challenging` | 正在挑战中（25cm ≤ length < 30cm） |
| `challenge_completed_reduce` | 已完成后再次跌出 25cm，减 5cm |
| `length_near_zero` | 0 < length ≤ 5cm，首次标记 |
| `length_zero_or_negative` | length ≤ 0，首次标记 |
| `user_not_found` | 用户不存在 |

## CD 缓存模块

模块级别的内存缓存 `_cd_cache`，按命令类型分组，每个类型存 `{user_id: timestamp}`。

| 函数 | 参数 | 说明 |
|------|------|------|
| `_check_cd(cd_type, uid, cd_time)` | `str, str, int` | 检查冷却，返回 `(是否通过, 剩余秒数)` |
| `_update_cd(cd_type, uid)` | `str, str` | 记录当前时间戳 |
| `_delete_cd(cd_type, uid)` | `str, str` | 删除指定用户的 CD 记录 |

CD 缓存在 `on_unload()` 时通过 `_cd_cache.clear()` 清空，确保插件重载后 CD 状态不残留。

## 工具函数

| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `_get_random_num()` | 无 | `float` | 90% 概率 [0, 1)，10% 概率 [1, 2) |
| `_get_jj_variable(config_str)` | `str` | `str` | 从逗号分隔列表中随机选一个变量名 |
| `_get_ban_id_set(config_str)` | `str` | `set` | 将逗号分隔的 QQ 号串解析为集合 |

## kwargs 结构

Command handler 收到的 `kwargs` 由 MaiBot SDK 的 `_build_command_executor` 构造：

| 键 | 类型 | 来源 | 示例 |
|----|------|------|------|
| `text` | `str` | `message.processed_plain_text` | `"suo"` |
| `stream_id` | `str` | `message.session_id` | `"abc123..."` |
| `group_id` | `str` | `group_info.group_id` | `"123456"` |
| `platform` | `str` | `message.platform` | `"qq"` |
| `user_id` | `str` | `user_info.user_id` | `"10001"` |
| `matched_groups` | `dict` | SDK 正则捕获组 | `{"all": "历史"}` |
| `message` | `dict` | `_session_message_to_dict` | 完整 SessionMessage 字典 |
| `plugin_config` | `dict` | 插件配置字典 | `{"plugin": {...}}` |

`message` 字典结构：

```python
{
    "message_id": "...",
    "platform": "qq",
    "message_info": {
        "user_info": {
            "user_id": "...",
            "user_nickname": "...",
            "user_cardname": "..."
        },
        "group_info": {
            "group_id": "...",
            "group_name": "..."
        },
        "additional_config": {
            "self_id": "...",
            "user_role": "owner"
        }
    },
    "raw_message": [
        {"type": "text", "data": "..."},
        {"type": "at", "data": {"target_user_id": "..."}}
    ],
    "session_id": "...",
    "processed_plain_text": "..."
}
```

## 绘图模块

`draw_chart.py` 使用 Pillow 生成排行榜柱状图和注入量折线图。

| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `draw_bar_chart(data)` | `dict` (label → value) | `bytes` | 生成柱状图 PNG 字节流 |
| `draw_line_chart(data)` | `dict` (date → volume) | `bytes` | 生成折线图 PNG 字节流 |
