# 开发指南

## 项目结构

```
maibot-plugin-impart/
├── plugin.py                  # 插件入口，MaiBotPlugin 子类 + 9 个命令
├── database.py                # 数据库操作层，SQLAlchemy 异步 ORM
├── draw_chart.py              # 图表绘制，Pillow 实现
├── config.toml                # 配置文件（自动生成）
├── _manifest.json             # 插件清单
├── fonts/                     # 中文字体文件（图表用）
├── docs/                      # 文档
│   ├── guide.md               # 使用指南
│   ├── api.md                 # API 参考
│   ├── faq.md                 # 常见问题
│   └── dev.md                 # 开发指南
├── TEST_CASES.md              # 测试用例
├── README.md                  # 项目说明
├── LICENSE                    # MIT 协议
└── requirements.txt           # 依赖列表
```

## 架构概览

### 分层设计

```
┌─────────────────────────────┐
│  plugin.py (命令 + 事件)     │  业务层 - 命令路由、用户交互
├─────────────────────────────┤
│  database.py (ORM 操作)      │  数据层 - 数据库读写
├─────────────────────────────┤
│  draw_chart.py (Pillow)      │  展示层 - 图表生成
└─────────────────────────────┘
```

### 关键设计决策

1. **单类设计**：MaiBot SDK 要求 `@Command` 装饰器在 `MaiBotPlugin` 子类方法上使用，无法拆分为多个子类。因此全部 9 个命令和 1 个事件处理器集中在 `ImpartPlugin` 单类中。

2. **数据库独立 ORM**：SDK 的 `ctx.db` 仅支持 Host 预定义模型。自定义表（`userdata`、`groupdata`、`ejaculation_data`、`user_group`）保持独立的 SQLAlchemy ORM。

3. **@ 目标解析**：由于 NapCat 适配器将 @ 段构建为 `@用户名`（非 QQ 号），不再使用正则 `(?P<target>\d+)` 捕获组，改用 `@[^\s]+` 接受任意 @ 后缀，再从 `raw_message` 段提取真实 `user_id`。

4. **权限双通道**：适配器注入的 `additional_config["user_role"]` + 配置中的 `admin_ids` 列表兜底。

## 添加新的命令

### 步骤

1. 在 `ImpartPlugin` 类中添加一个 `@Command` 装饰器方法：

```python
@Command(
    "command_name",
    description="命令说明",
    pattern=r"^触发词(\s*@[^\s]+)?\s*$",
    aliases=["别名1", "别名2"],
)
async def handle_my_command(self, **kwargs):
    stream_id = kwargs["stream_id"]
    # ... 业务逻辑 ...
    await self.ctx.send.text("回复内容", stream_id)
    return True, "操作成功", 2
```

### 装饰器参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| 第一个参数 | `str` | 是 | 命令唯一标识名 |
| `description` | `str` | 否 | 命令描述 |
| `pattern` | `str` | 是 | 正则匹配模式 |
| `aliases` | `List[str]` | 否 | 命令别名列表 |

### Handler 返回值

Handler 必须返回 `(bool, str, int)` 三元组：

| 位置 | 类型 | 说明 |
|------|------|------|
| 第 1 位 | `bool` | 是否拦截消息继续传递 |
| 第 2 位 | `str` | 操作描述（用于日志） |
| 第 3 位 | `int` | 拦截等级 |

## 命令 Pattern 编写规范

### @ 用户匹配

所有需要 @ 用户的命令，pattern 中应使用 `@[^\s]+` 而非 `(?P<target>\d+)`：

```python
# 正确
pattern=r"^(pk|对决)(\s*@[^\s]+)?\s*$"

# 错误
pattern=r"^(pk|对决)(\s*(?P<target>\d+))?\s*$"
```

原因：NapCat 适配器构建的 `processed_plain_text` 中 @ 段格式为 `@用户名` 或 `@QQ号`，不是纯数字。

### @ 目标提取

从 handler 中提取 @ 目标时，使用 `_parse_at_target(kwargs)` 而非 `kwargs["matched_groups"]["target"]`：

```python
# 正确
at_target = self._parse_at_target(kwargs)
target_uid = int(at_target) if at_target else int(self._get_user_id(kwargs))

# 错误
target = kwargs.get("matched_groups", {}).get("target")  # matched_groups 取到的是 @后缀 而非 QQ 号
```

`_parse_at_target` 从 `kwargs["message"]["raw_message"]` 段中提取 `target_user_id`，不受 @ 格式影响。

## kwargs 工具方法

| 方法 | 返回值 | 说明 |
|------|--------|------|
| `_get_user_id(kwargs)` | `str` | 触发用户 QQ 号，异常时返回 `"0"` |
| `_get_group_id(kwargs)` | `int` | 群号，异常或私聊时返回 `0` |
| `_get_nick(kwargs)` | `str` | 用户昵称，优先 cardname，异常时返回 `"用户"` |
| `_get_role(kwargs)` | `str` | 群角色（owner / admin / member / ""） |
| `_parse_at_target(kwargs)` | `Optional[str]` | 第一个 @ 目标的 QQ 号，无 @ 时返回 `None` |

这些方法都有异常安全处理，不会抛出异常导致命令中断。

## 数据库操作

### 添加新的数据库表

1. 在 `database.py` 中定义新的 `Base` 子类：

```python
class NewTable(Base):
    __tablename__ = "new_table"
    id = Column(Integer, primary_key=True)
    # ... 其他字段 ...
```

2. 表会自动在下次 `init_db` 时创建（`create_all`）。

### 添加新的数据库操作函数

```python
async def my_query(db_path: str, param: int) -> List[Dict]:
    session_cls = get_session_cls(db_path)
    async with session_cls() as s:
        result = await s.execute(select(MyModel).where(MyModel.field == param))
        return [{"field": row.field} for row in result.scalars()]
```

注意：所有数据库操作都必须接收 `db_path` 参数，因为引擎是全局懒初始化的。

### 引擎管理

- 引擎在第一次调用 `get_engine(db_path)` 时创建，全局唯一
- 调用 `reset_engine()` 可重置引擎（用于配置变更或测试）
- 每次 `on_config_update` 检测到 `db_path` 变化时会自动重置并重新初始化

## 模块级函数说明

`plugin.py` 中的模块级函数（非类方法）：

| 函数 | 说明 |
|------|------|
| `_check_cd(cd_type, uid, cd_time)` | 检查冷却，返回 `(bool, remaining)` |
| `_update_cd(cd_type, uid)` | 记录 CD 时间戳 |
| `_delete_cd(cd_type, uid)` | 删除 CD 记录（用于回退 CD 场景） |
| `_get_random_num()` | 带偏置的随机数：90% [0,1)，10% [1,2) |
| `_get_jj_variable(config_str)` | 从 CSV 串中随机选一个变量名 |
| `_get_ban_id_set(config_str)` | 将 CSV 串解析为 `set` |

这些函数设计为模块级而非类方法，是因为它们不依赖 `self` 状态，便于测试和独立使用。

## 事件处理器

插件注册了一个 `ON_START` 事件处理器：

```python
@EventHandler(
    "impart_init",
    description="启动时初始化数据库",
    event_type=EventType.ON_START,
)
async def handle_init(self, **kwargs):
    self.ctx.logger.info("ON_START 事件触发: 数据库初始化已在 on_load 中完成")
```

数据库初始化实际在 `on_load` 中完成，`handle_init` 主要用于确认 SDK 事件机制正常工作。

## 绘图模块

`draw_chart.py` 使用 Pillow 生成图片：

- `draw_bar_chart(data)` — 排行榜柱状图，接收 `{label: value}` 字典，返回 PNG 字节流
- `draw_line_chart(data)` — 注入量折线图，接收 `{date: volume}` 字典，返回 PNG 字节流

使用 `base64.b64encode` 编码后通过 `self.ctx.send.image()` 发送。

## 本地开发

### 环境准备

```bash
# 克隆项目
git clone <repository-url>
cd maibot-plugin-impart

# 安装依赖
pip install sqlalchemy aiosqlite Pillow

# 如果使用 .venv，确保 MaiBot SDK 可用
# 或 symlink 到 MaiBot 的插件目录
```

### 代码规范

- 类型提示：函数参数和返回值应标注类型
- 异常安全：kwargs 提取方法使用 `try/except` 兜底
- 日志：使用 `self.ctx.logger` 而非 `print`
- 注释：公共方法和复杂逻辑应包含文档字符串

### 测试

手动测试用例见 `TEST_CASES.md`，覆盖以下场景：

- 基础环境加载（9 个用例）
- 帮助命令
- 银趴开关（管理员功能）
- 查询命令（含 5 个长度段位）
- 打胶 / 嗦牛子 / PK
- 透群友（含反透机制）
- 排行榜（分群过滤）
- 注入查询（单日 / 历史）
- 登神挑战完整流程
- CD 冷却测试
- 白名单测试
- 边界情况（15 个用例）

### 构建与部署

```bash
# 复制到 MaiBot 插件目录
Copy-Item -Path "maibot-plugin-impart" -Destination "MaiBot/plugins/" -Recurse

# 或使用 symlink（开发用）
New-Item -ItemType Junction -Path "MaiBot/plugins/maibot-plugin-impart" -Target "path/to/maibot-plugin-impart"
```

### 调试提示

- 插件日志通过 `self.ctx.logger` 输出到 MaiBot 控制台
- 数据库文件默认在 `data/impart.db`，可用 SQLite 工具直接查看
- CD 缓存是内存态，插件重载后自动清空

## 已知限制

1. **SDK `ctx.paths` 未实现**：数据库路径改用 `os.path.join(os.path.dirname(__file__), "data", "impart.db")`，待 SDK 版本更新后可切换回 `ctx.paths.data_dir`

2. **模块导入 workaround**：`sys.path.insert(0, os.path.dirname(__file__))` 必须保留，Runner 的 importlib 加载不将插件目录加入搜索路径

3. **NapCat 适配器依赖**：`user_role` 权限判断依赖适配器注入 `additional_config`，如果适配器不实现则 fallback 到 `admin_ids` 配置
