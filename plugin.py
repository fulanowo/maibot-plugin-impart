"""
MaiBot 银趴插件 (maibot-plugin-impart) v2.0

从 nonebot-plugin-impart 移植至 MaiBot 平台，使用 maibot_sdk 新 API。
包含 9 个命令和数据库自动初始化。
"""

import asyncio
import base64
import os
import random
import re
import time
from datetime import datetime, timedelta
from random import choice

from maibot_sdk import Command, EventHandler, Field, MaiBotPlugin, PluginConfigBase
from maibot_sdk.types import EventType

from . import database as db
from .draw_chart import draw_bar_chart

# 模块级 CD 缓存：按命令类型分组，每项存 {user_id: last_timestamp}
# 在 on_unload 中清理，插件重载后不残留旧状态
_cd_cache = {
    "dajiao": {},
    "pk": {},
    "suo": {},
    "fuck": {},
}


def _check_cd(cd_type, uid, cd_time):
    """检查冷却：已过 cd_time 返回 (True, 0)，否则返回 (False, 剩余秒数)"""
    cache = _cd_cache[cd_type]
    last_time = cache.get(uid, 0)
    elapsed = time.time() - last_time
    return (True, 0) if elapsed > cd_time else (False, cd_time - elapsed)


def _update_cd(cd_type, uid):
    """记录用户本次使用时间戳"""
    _cd_cache[cd_type][uid] = time.time()


def _delete_cd(cd_type, uid):
    """删除用户的 CD 记录（用于创建新用户等需回退 CD 的场景）"""
    _cd_cache[cd_type].pop(uid, None)


def _get_random_num():
    """
    带偏置的随机增量生成器：
    - 90% 概率返回 [0, 1) 之间的值
    - 10% 概率返回 [1, 2) 之间的值（小概率大涨）
    """
    rand = random.random()
    return round(random.uniform(0, 1) if rand > 0.1 else random.uniform(1, 2), 3)


def _get_jj_variable(config_str):
    """从逗号分隔的配置串中随机选一个牛牛变量名"""
    parts = [p.strip() for p in config_str.split(",") if p.strip()]
    return choice(parts) if parts else "牛子"


def _get_ban_id_set(config_str):
    """将逗号分隔的 QQ 号串解析为 set，用于 ban/admin 列表"""
    if not config_str:
        return set()
    return set(x.strip() for x in config_str.split(",") if x.strip())


# ── 配置模型 ──────────────────────────────────────────────────────────
# 四层嵌套：plugin / commands / security / challenge
# SDK 自动从 config.toml 读取并合并为 ImpartPluginConfig 实例

class PluginSectionConfig(PluginConfigBase):
    """插件基本配置：开关、数据库路径、提示文本等"""
    __ui_label__ = "插件基本配置"
    __ui_icon__ = "package"
    __ui_order__ = 0

    config_version: str = Field(default="1.0.0", description="配置文件版本号")
    enabled: bool = Field(default=True, description="是否启用插件")
    not_allow: str = Field(
        default='群内还未开启impart游戏, 请管理员或群主发送"开始银趴", "禁止银趴"以开启/关闭该功能',
        description="未开启时的提示消息",
    )
    jj_variable: str = Field(default="牛子,牛牛,newnew", description="牛牛变量名列表（逗号分隔）")
    bot_name: str = Field(default="BOT", description="机器人称呼")
    db_path: str = Field(default="data/impart.db", description="数据库文件路径（相对于插件目录或绝对路径）")


class CommandsSectionConfig(PluginConfigBase):
    """命令配置：各命令的 CD 时间和不活跃惩罚开关"""
    __ui_label__ = "命令配置"
    __ui_icon__ = "terminal"
    __ui_order__ = 1

    dj_cd_time: int = Field(default=300, description="打胶冷却时间（秒）")
    pk_cd_time: int = Field(default=60, description="PK冷却时间（秒）")
    suo_cd_time: int = Field(default=300, description="嗦冷却时间（秒）")
    fuck_cd_time: int = Field(default=3600, description="透群友冷却时间（秒）")
    isalive: bool = Field(default=False, description="是否开启不活跃惩罚")


class SecuritySectionConfig(PluginConfigBase):
    """安全配置：ban 名单、管理员 ID 列表"""
    __ui_label__ = "安全与白名单"
    __ui_icon__ = "shield"
    __ui_order__ = 2

    ban_id_list: str = Field(default="", description="禁止名单（逗号分隔的QQ号）")
    admin_ids: str = Field(default="", description="管理员QQ号列表（逗号分隔），留空则仅依赖 OneBot 原生 role 判断")


class ChallengeSectionConfig(PluginConfigBase):
    """登神挑战配置：阈值、惩罚、倍率"""
    __ui_label__ = "登神挑战"
    __ui_icon__ = "trophy"
    __ui_order__ = 3

    challenge_threshold: int = Field(default=25, description="登神挑战触发长度（cm）")
    success_threshold: int = Field(default=30, description="登神挑战完成长度（cm）")
    fail_penalty: int = Field(default=5, description="挑战失败惩罚缩减长度（cm）")
    win_rate_multiplier: float = Field(default=1.25, description="挑战失败胜率恢复倍率")


class ImpartPluginConfig(PluginConfigBase):
    """顶层配置模型，聚合四个子节"""
    plugin: PluginSectionConfig = Field(default_factory=PluginSectionConfig)
    commands: CommandsSectionConfig = Field(default_factory=CommandsSectionConfig)
    security: SecuritySectionConfig = Field(default_factory=SecuritySectionConfig)
    challenge: ChallengeSectionConfig = Field(default_factory=ChallengeSectionConfig)


# ── 插件主类 ──────────────────────────────────────────────────────────

class ImpartPlugin(MaiBotPlugin):
    """银趴插件入口，挂载 9 个命令 + 1 个 ON_START 事件处理器"""
    config_model = ImpartPluginConfig

    # ── 生命周期 ──────────────────────────────────────────────────────

    async def on_load(self) -> None:
        """插件加载时初始化数据库连接和每日惩罚循环"""
        self._db_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), self.config.plugin.db_path
        )
        try:
            await db.init_db(self._db_path)
            self.ctx.logger.info("数据库初始化完成: %s", self._db_path)
        except Exception:
            self.ctx.logger.exception("数据库初始化失败")

        self._daily_task = asyncio.create_task(self._daily_loop())
        self.ctx.logger.info("银趴插件已加载")

    async def on_unload(self) -> None:
        """插件卸载时清理后台任务、数据库引擎和 CD 缓存"""
        if hasattr(self, "_daily_task"):
            self._daily_task.cancel()
        db.reset_engine()
        _cd_cache.clear()
        self.ctx.logger.info("银趴插件已卸载")

    async def on_config_update(self, scope: str, config_data: dict, version: str) -> None:
        """
        配置热更新回调：
        - db_path 变动时重置数据库引擎并重新初始化
        - CD 时间/ban 列表等在 handler 中动态读取 self.config，天然支持热更新
        """
        new_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), self.config.plugin.db_path
        )
        if new_path != self._db_path:
            self._db_path = new_path
            db.reset_engine()
            await db.init_db(self._db_path)
            self.ctx.logger.info("数据库路径已变更，已重新初始化: %s", self._db_path)
        self.ctx.logger.info("配置已更新: scope=%s, version=%s", scope, version)

    # ── kwargs 提取工具 ──────────────────────────────────────────────

    def _get_user_id(self, kwargs):
        """从 kwargs 中提取触发用户的 QQ 号，异常安全"""
        try:
            msg = kwargs.get("message", {})
            return str(msg.get("message_info", {}).get("user_info", {}).get("user_id", "0"))
        except Exception:
            return "0"

    def _get_group_id(self, kwargs):
        """从 kwargs 中提取群号"""
        try:
            msg = kwargs.get("message", {})
            gi = msg.get("message_info", {}).get("group_info")
            return int(gi.get("group_id", 0)) if gi else 0
        except Exception:
            return 0

    def _get_nick(self, kwargs):
        """从 kwargs 中提取用户昵称（优先 cardname > nickname）"""
        try:
            msg = kwargs.get("message", {})
            info = msg.get("message_info", {}).get("user_info", {})
            return info.get("user_nickname") or info.get("user_cardname") or "用户"
        except Exception:
            return "用户"

    def _get_role(self, kwargs):
        """
        从 kwargs 的 additional_config 中提取用户群身份（owner/admin/member）。
        身份由 NapCat 适配器在入站消息编解码时注入。
        """
        try:
            msg = kwargs.get("message", {})
            add_cfg = msg.get("message_info", {}).get("additional_config", {})
            if isinstance(add_cfg, dict):
                role = add_cfg.get("user_role", "")
                if role:
                    return str(role)
        except Exception:
            pass
        return ""

    def _parse_at_target(self, kwargs):
        """
        从 raw_message 段中提取第一个 @ 目标的 user_id，
        不依赖 processed_plain_text 中的 @ 后缀格式。
        """
        msg = kwargs.get("message", {})
        raw = msg.get("raw_message", [])
        for seg in raw:
            if isinstance(seg, dict) and seg.get("type") == "at":
                data = seg.get("data", {}) if isinstance(seg.get("data"), dict) else {}
                uid = str(data.get("target_user_id", "") or "")
                if uid:
                    return uid
        return None

    # ── 后台任务 ──────────────────────────────────────────────────────

    async def _daily_loop(self):
        """
        每日凌晨定时任务：
        如果 isalive 开启，对所有不活跃用户执行长度缩减惩罚。
        """
        while True:
            now = datetime.now()
            next_run = now.replace(hour=0, minute=0, second=0) + timedelta(days=1)
            await asyncio.sleep((next_run - now).total_seconds())

            if self.config.commands.isalive:
                try:
                    await db.punish_all_inactive_users(self._db_path)
                    self.ctx.logger.info("每日不活跃惩罚已执行")
                except Exception:
                    self.ctx.logger.exception("每日惩罚执行失败")

    # ── 帮助 ──────────────────────────────────────────────────────────

    @Command(
        "help",
        description="银趴帮助 - 显示使用说明",
        pattern=r"^(银趴|impart)(介绍|帮助)$",
        aliases=["银趴帮助", "impart帮助", "银趴介绍", "impart介绍"],
    )
    async def handle_help(self, **kwargs):
        """输出全部命令的使用说明"""
        threshold = self.config.challenge.challenge_threshold
        stream_id = kwargs["stream_id"]
        usage_text = (
            "impart功能说明:\n"
            "[日/透]\n"
            "使用<日/透@用户>与群友互动\n"
            "[pk|对决]\n"
            "通过random实现pk,胜方获取败方随机数/2的牛牛长度;\n"
            "初始胜率为50%,pk后胜方胜率-1%,败方胜率+1%\n"
            f"<牛牛长度超过{threshold}时会触发神秘任务>\n"
            "[打胶|开导]\n"
            "增加自己长度\n"
            "[嗦牛子|嗦]\n"
            "增加@用户长度(若未@则为自己)\n"
            "[查询]\n"
            "查询@用户长度(若未@则为自己)\n"
            "[jj排行榜|jj排名|jj榜单|jjrank]\n"
            "输出倒数五位/前五位/自己的排名\n"
            "[注入查询|摄入查询|射入查询]\n"
            "查询@用户被透注入的量(后接<历史/全部>可查看总被摄入的量)(若未@则为自己)\n"
            "[开启银趴|禁止银趴|开始impart|关闭impart]\n"
            "由管理员|群主开启或者关闭impart\n"
            "[银趴介绍|impart介绍]\n"
            "输出impart插件的命令列表\n"
        )
        await self.ctx.send.text(usage_text, stream_id)
        return True, "帮助信息已发送", 2

    # ── 查询 ──────────────────────────────────────────────────────────

    @Command(
        "query",
        description="查询 - 查询用户牛子长度",
        pattern=r"^查询(\s*@[^\s]+)?\s*$",
    )
    async def handle_query(self, **kwargs):
        """
        查询目标用户的当前牛牛长度。
        未 @ 则查自己。新用户自动创建并初始化为 10cm。
        按长度区间输出不同段位的提示文案。
        """
        at_target = self._parse_at_target(kwargs)
        target_uid = int(at_target) if at_target else int(self._get_user_id(kwargs))
        pronoun = "你" if str(target_uid) == self._get_user_id(kwargs) else "TA"
        jj_var = _get_jj_variable(self.config.plugin.jj_variable)
        stream_id = kwargs["stream_id"]
        group_id = self._get_group_id(kwargs)

        if not await db.check_group_allow(self._db_path, group_id):
            await self.ctx.send.text(self.config.plugin.not_allow, stream_id)
            return True, "未开启", 2

        if not await db.is_in_table(self._db_path, target_uid):
            await db.add_new_user(self._db_path, target_uid)
            await self.ctx.send.text(
                f"{pronoun}还没有创建{jj_var}喵, 咱帮{pronoun}创建了喵, 目前长度是10cm喵",
                stream_id,
            )
            return True, "创建成功", 2

        length = await db.get_jj_length(self._db_path, target_uid)

        if length >= 30:
            msg = f"✨牛々の神✨\n{pronoun}的{jj_var}目前长度为{length}cm喵"
        elif 5 < length < 30:
            msg = f"{pronoun}的{jj_var}目前长度为{length}cm喵"
        elif 1 < length <= 5:
            msg = f"{pronoun}已经是xnn啦！\n{pronoun}的{jj_var}目前长度为{length}cm喵"
        elif 0 < length <= 1:
            msg = f"{pronoun}快要变成女孩子啦！\n{pronoun}的{jj_var}目前长度为{length}cm喵"
        else:
            msg = f"{pronoun}已经是女孩子啦！\n{pronoun}的{jj_var}目前长度为{length}cm喵"

        await self.ctx.send.text(msg, stream_id)
        return True, "查询成功", 2

    # ── 排行榜 ────────────────────────────────────────────────────────

    @Command(
        "jjrank",
        description="jj排行榜 - 查看牛子排行榜（分群过滤，图例显示昵称）",
        pattern=r"^(jj|牛牛)(排行榜|排名|榜单|rank)$",
        aliases=["牛牛排行榜", "牛牛排名", "牛牛榜单"],
    )
    async def handle_jjrank(self, **kwargs):
        """
        输出当前群内的前五 / 后五排名柱状图（图片），
        并附带用户自身排名文本。数据不足 5 条时提示。
        """
        uid = int(self._get_user_id(kwargs))
        jj_var = _get_jj_variable(self.config.plugin.jj_variable)
        group_id = self._get_group_id(kwargs)
        stream_id = kwargs["stream_id"]

        if not await db.check_group_allow(self._db_path, group_id):
            await self.ctx.send.text(self.config.plugin.not_allow, stream_id)
            return True, "未开启", 2

        await db.ensure_user_in_group(self._db_path, uid, group_id, self._get_nick(kwargs))

        rankdata = await db.get_sorted(self._db_path, group_id)
        if len(rankdata) < 5:
            await self.ctx.send.text("目前记录的数据量小于5, 无法显示rank喵", stream_id)
            return True, "数据不足", 2

        top5 = rankdata[:5]
        last5 = rankdata[-5:]

        index = [i for i in range(len(rankdata)) if rankdata[i]["userid"] == uid]
        if not index:
            await db.add_new_user(self._db_path, uid)
            await self.ctx.send.text(
                f"你还没有创建{jj_var}看不到rank喵, 咱帮你创建了喵, 目前长度是10cm喵",
                stream_id,
            )
            return True, "创建成功", 2

        user_rank = index[0] + 1

        data = {}
        for entry in top5 + last5:
            nick = await db.get_group_nickname(self._db_path, entry["userid"], group_id)
            key = nick if nick else f"用户{entry['userid']}"
            data[key] = entry["jj_length"]

        img_bytes = await draw_bar_chart.draw_bar_chart(data)
        img_b64 = base64.b64encode(img_bytes).decode("utf-8")
        await self.ctx.send.image(img_b64, stream_id)
        await self.ctx.send.text(f"你的排名为{user_rank}喵", stream_id)
        return True, "排行榜已发送", 2

    # ── 注入查询 ──────────────────────────────────────────────────────

    @Command(
        "injection_query",
        description="注入查询 - 查询被注入量（后接历史/全部查看折线图）",
        pattern=r"^(注入查询|摄入查询|射入查询)(\s+(?P<all>历史|全部))?$",
    )
    async def handle_injection_query(self, **kwargs):
        """
        查询用户被透的总注入量：
        - 不加后缀：只显示当日累计量
        - 后接"历史"/"全部"：显示历史总量 + 折线图
        """
        at_target = self._parse_at_target(kwargs)
        target_id = int(at_target) if at_target else int(self._get_user_id(kwargs))
        matched = kwargs.get("matched_groups", {})
        is_all = matched.get("all") in ("历史", "全部")
        replay1 = "该用户" if at_target else "您"
        stream_id = kwargs["stream_id"]
        group_id = self._get_group_id(kwargs)

        if not await db.check_group_allow(self._db_path, group_id):
            await self.ctx.send.text(self.config.plugin.not_allow, stream_id)
            return True, "未开启", 2

        if is_all:
            data = await db.get_ejaculation_data(self._db_path, target_id)
            if not data:
                await self.ctx.send.text(f"{replay1}历史总被注射量为0ml", stream_id)
                return True, "查询成功", 2

            ejaculation = 0.0
            inject_data = {}
            for item in data:
                ejaculation += item["volume"]
                inject_data[item["date"]] = item["volume"]

            if len(inject_data) < 1:
                await self.ctx.send.text(f"{replay1}历史总被注射量为{ejaculation}ml", stream_id)
                return True, "查询成功", 2

            img_bytes = await draw_bar_chart.draw_line_chart(inject_data)
            img_b64 = base64.b64encode(img_bytes).decode("utf-8")
            await self.ctx.send.text(f"{replay1}历史总被注射量为{ejaculation}ml", stream_id)
            await self.ctx.send.image(img_b64, stream_id)
        else:
            ejaculation = await db.get_today_ejaculation_data(self._db_path, target_id)
            await self.ctx.send.text(f"{replay1}当日总被注射量为{ejaculation}ml", stream_id)

        return True, "查询成功", 2

    # ── 打胶 ──────────────────────────────────────────────────────────

    @Command(
        "dajiao",
        description="打胶/开导 - 增加自己的牛子长度",
        pattern=r"^(打胶|开导)$",
    )
    async def handle_dajiao(self, **kwargs):
        """
        打胶 / 开导：随机增加自己的牛牛长度。
        - 有 CD（默认 300 秒）
        - 处于登神挑战状态时禁止打胶
        - 打胶后若长度 ≥25cm 触发登神挑战开启
        """
        uid_str = self._get_user_id(kwargs)
        uid = int(uid_str)
        jj_var = _get_jj_variable(self.config.plugin.jj_variable)
        stream_id = kwargs["stream_id"]
        group_id = self._get_group_id(kwargs)

        if not await db.check_group_allow(self._db_path, group_id):
            await self.ctx.send.text(self.config.plugin.not_allow, stream_id)
            return True, "未开启", 2

        cd_allowed, remaining = _check_cd("dajiao", uid_str, self.config.commands.dj_cd_time)
        if not cd_allowed:
            await self.ctx.send.text(
                f"你已经打不动了喵, 请等待{round(remaining, 3)}秒后再打喵",
                stream_id,
            )
            return True, "CD中", 2

        _update_cd("dajiao", uid_str)

        if not await db.is_in_table(self._db_path, uid):
            await db.add_new_user(self._db_path, uid)
            await self.ctx.send.text(
                f"你还没有创建{jj_var}, 咱帮你创建了喵, 目前长度是10cm喵",
                stream_id,
            )
            return True, "创建成功", 2

        uid_length = await db.get_jj_length(self._db_path, uid)
        random_num = _get_random_num()
        uid_status = await db.update_challenge_status(self._db_path, uid)

        if "is_challenging" in uid_status:
            await self.ctx.send.text(
                f"你的{jj_var}长度在任务范围内，不允许打胶，请专心与群友pk！",
                stream_id,
            )
            return True, "挑战中", 2

        await db.set_jj_length(self._db_path, uid, random_num)
        gid = self._get_group_id(kwargs)
        await db.ensure_user_in_group(self._db_path, uid, gid, self._get_nick(kwargs))
        new_length = await db.get_jj_length(self._db_path, uid)

        bot_name = self.config.plugin.bot_name
        if uid_length < 25 <= new_length:
            await db.update_challenge_status(self._db_path, uid)
            msg = (
                f"打胶结束喵, 你的{jj_var}很满意喵, 长了{random_num}cm喵"
                f"\n由于你无休止的打胶，触犯到了神秘的禁忌，{bot_name}检测到你的{jj_var}长度超过25cm，"
                f"已为你开启✨\"登神长阶\"✨"
                f"\n你现在的获胜概率变为当前的80%，且无法使用\"打胶\"与\"嗦\"指令，"
                f"请以将{jj_var}长度提升至30cm为目标与他人pk吧！"
            )
        else:
            msg = f"打胶结束喵, 你的{jj_var}很满意喵, 长了{random_num}cm喵, 目前长度为{new_length}cm喵"

        await self.ctx.send.text(msg, stream_id)
        return True, "打胶成功", 2

    # ── 嗦牛子 ────────────────────────────────────────────────────────

    @Command(
        "suo",
        description="嗦牛子/嗦 - 增加目标用户的牛子长度",
        pattern=r"^嗦(?:牛子)?(\s*@[^\s]+)?\s*$",
    )
    async def handle_suo(self, **kwargs):
        """
        嗦牛子：为@目标（或自己）增加牛牛长度。
        - 有 CD（默认 300 秒）
        - 若目标不存在则创建，同时回退 CD
        - 目标处于挑战状态时禁止嗦
        - 嗦后若目标长度 ≥25cm 触发登神挑战
        """
        uid_str = self._get_user_id(kwargs)
        uid = int(uid_str)
        jj_var = _get_jj_variable(self.config.plugin.jj_variable)
        stream_id = kwargs["stream_id"]
        group_id = self._get_group_id(kwargs)

        if not await db.check_group_allow(self._db_path, group_id):
            await self.ctx.send.text(self.config.plugin.not_allow, stream_id)
            return True, "未开启", 2

        cd_allowed, remaining = _check_cd("suo", uid_str, self.config.commands.suo_cd_time)
        if not cd_allowed:
            await self.ctx.send.text(
                f"你已经嗦不动了喵, 请等待{round(remaining, 3)}秒后再嗦喵",
                stream_id,
            )
            return True, "CD中", 2

        _update_cd("suo", uid_str)

        at_target = self._parse_at_target(kwargs)
        target_id = int(at_target) if at_target else uid
        pronoun = "你" if target_id == uid else "TA"

        if not await db.is_in_table(self._db_path, target_id):
            await db.add_new_user(self._db_path, target_id)
            _delete_cd("suo", uid_str)
            await self.ctx.send.text(
                f"{pronoun}还没有创建{jj_var}喵, 咱帮{pronoun}创建了喵, 目前长度是10cm喵",
                stream_id,
            )
            return True, "创建成功", 2

        current_length = await db.get_jj_length(self._db_path, target_id)
        random_num = _get_random_num()
        target_status = await db.update_challenge_status(self._db_path, target_id)

        if "is_challenging" in target_status:
            await self.ctx.send.text(
                f"{pronoun}的{jj_var}长度在任务范围内，不准嗦！请专心与群友pk！",
                stream_id,
            )
            return True, "挑战中", 2

        await db.set_jj_length(self._db_path, target_id, random_num)
        gid = self._get_group_id(kwargs)
        nick = self._get_nick(kwargs)
        await db.ensure_user_in_group(self._db_path, uid, gid, nick)
        await db.ensure_user_in_group(
            self._db_path, target_id, gid,
            nick if target_id == uid else f"用户{target_id}",
        )
        new_length = await db.get_jj_length(self._db_path, target_id)

        bot_name = self.config.plugin.bot_name
        if current_length < 25 <= new_length:
            await db.update_challenge_status(self._db_path, target_id)
            msg = (
                f"{pronoun}的{jj_var}很满意喵, 嗦长了{random_num}cm喵"
                f"\n由于{pronoun}无休止的嗦与被嗦，触犯到了神秘的禁忌，{bot_name}检测到{pronoun}的{jj_var}长度超过25cm，"
                f"\n已为{pronoun}开启✨\"登神长阶\"✨，{pronoun}现在的获胜概率变为当前的80%，且无法使用\"打胶\"与\"嗦\"指令，"
                f"请以将{jj_var}长度提升至30cm为目标与他人pk吧！"
            )
        else:
            msg = f"{pronoun}的{jj_var}很满意喵, 嗦长了{random_num}cm喵, 目前长度为{new_length}cm喵"

        await self.ctx.send.text(msg, stream_id)
        return True, "嗦成功", 2

    # ── 开关银趴 ──────────────────────────────────────────────────────

    @Command(
        "toggle",
        description="开启/关闭银趴 - 管理员开关impart功能",
        pattern=r"^(开始|开启|关闭|禁止)(银趴|impart)$",
    )
    async def handle_toggle(self, **kwargs):
        """
        群管理员 / owner 开关本群的 impart 功能。
        权限判断：先检查 OneBot 原生角色（owner/admin），
        再 fallback 到配置中的 admin_ids 列表。
        """
        uid = self._get_user_id(kwargs)
        stream_id = kwargs["stream_id"]

        role = self._get_role(kwargs)
        is_admin = role in ("owner", "admin")
        if not is_admin:
            admin_ids_str = self.config.security.admin_ids
            if admin_ids_str:
                is_admin = uid in _get_ban_id_set(admin_ids_str)
        if not is_admin:
            await self.ctx.send.text("你没有权限使用此命令喵", stream_id)
            return True, "权限不足", 2

        text = kwargs.get("text", "")
        m = re.match(r"^(开始|开启|关闭|禁止)", text)
        if not m:
            return True, "无法解析命令", 2
        command = m.group(1)
        group_id = self._get_group_id(kwargs)

        if "开启" in command or "开始" in command:
            await db.set_group_allow(self._db_path, group_id, True)
            await self.ctx.send.text("功能已开启喵", stream_id)
        else:
            await db.set_group_allow(self._db_path, group_id, False)
            await self.ctx.send.text("功能已禁用喵", stream_id)

        return True, "操作成功", 2

    # ── PK / 对决 ─────────────────────────────────────────────────────

    @Command(
        "pk",
        description="PK/对决 - 与群友进行牛子对决",
        pattern=r"^(pk|对决)(\s*@[^\s]+)?\s*$",
    )
    async def handle_pk(self, **kwargs):
        """
        PK 对决：双方基于胜率判定胜负。
        胜方：长度 + (rn/2)，胜率 -1%
        败方：长度 - rn，胜率 +1%
        需要 @ 指定对手，不能 pk 自己。
        若任何一方不存在则自动创建双方，并回退 CD。
        """
        uid_str = self._get_user_id(kwargs)
        uid = int(uid_str)
        jj_var = _get_jj_variable(self.config.plugin.jj_variable)
        group_id = self._get_group_id(kwargs)
        stream_id = kwargs["stream_id"]

        if not await db.check_group_allow(self._db_path, group_id):
            await self.ctx.send.text(self.config.plugin.not_allow, stream_id)
            return True, "未开启", 2

        cd_allowed, remaining = _check_cd("pk", uid_str, self.config.commands.pk_cd_time)
        if not cd_allowed:
            await self.ctx.send.text(
                f"你已经pk不动了喵, 请等待{round(remaining, 3)}秒后再pk喵",
                stream_id,
            )
            return True, "CD中", 2

        _update_cd("pk", uid_str)

        at = self._parse_at_target(kwargs)
        if not at:
            await self.ctx.send.text("请指定要PK的对象喵，例如: pk @用户", stream_id)
            return True, "无目标", 2
        if at == uid_str:
            await self.ctx.send.text("你不能pk自己喵", stream_id)
            return True, "无法pk自己", 2

        bot_name = self.config.plugin.bot_name

        if await db.is_in_table(self._db_path, uid) and await db.is_in_table(self._db_path, int(at)):
            win_rand = random.random()
            win = win_rand < await db.get_win_probability(self._db_path, uid)
            rn = _get_random_num()
            length_increase = round(rn / 2, 3)
            length_decrease = rn

            if win:
                await db.set_win_probability(self._db_path, uid, -0.01)
                await db.set_win_probability(self._db_path, int(at), 0.01)
                await db.set_jj_length(self._db_path, uid, rn / 2)
                await db.set_jj_length(self._db_path, int(at), -rn)
                msg = await self._handle_pk_win(uid, at, length_increase, length_decrease, jj_var, bot_name)
            else:
                await db.set_win_probability(self._db_path, uid, 0.01)
                await db.set_win_probability(self._db_path, int(at), -0.01)
                await db.set_jj_length(self._db_path, uid, -rn)
                await db.set_jj_length(self._db_path, int(at), rn / 2)
                msg = await self._handle_pk_loss(uid, at, length_increase, length_decrease, jj_var, bot_name)

            gid = self._get_group_id(kwargs)
            await db.ensure_user_in_group(self._db_path, uid, gid, self._get_nick(kwargs))
            await db.ensure_user_in_group(self._db_path, int(at), gid, f"用户{at}")
            await self.ctx.send.text(msg, stream_id)
        else:
            if not await db.is_in_table(self._db_path, uid):
                await db.add_new_user(self._db_path, uid)
            if not await db.is_in_table(self._db_path, int(at)):
                await db.add_new_user(self._db_path, int(at))
            _delete_cd("pk", uid_str)
            await self.ctx.send.text(
                f"你或对面还没有创建{jj_var}喵, 咱全帮你创建了喵, 你们的{jj_var}长度都是10cm喵",
                stream_id,
            )

        return True, "PK完成", 2

    async def _handle_pk_win(self, uid, at, length_increase, length_decrease, jj_var, bot_name):
        """
        PK 胜利后处理双方的登神挑战状态更新：
        胜方：可能开启挑战 / 完成挑战
        败方：可能挑战失败 / 跌落神坛 / 变成 xnn / 变成女孩子
        """
        uid_status = await db.update_challenge_status(self._db_path, int(uid))
        at_status = await db.update_challenge_status(self._db_path, int(at))

        uid_msg = (
            f"对决胜利喵, 你的{jj_var}增加了{length_increase}cm喵, "
            f"对面则在你的阴影笼罩下减小了{length_decrease}cm喵"
        )

        if "challenge_started_low_win" in uid_status:
            uid_msg += (
                f"\n{bot_name}检测到你的{jj_var}长度超过25cm，已为你开启✨\"登神长阶\"✨"
                f"\n你现在的获胜概率变为当前的80%，且无法使用\"打胶\"与\"嗦\"指令，"
                f"请以将{jj_var}长度提升至30cm为目标与他人pk吧!"
            )
        elif "challenge_success_high_win" in uid_status:
            uid_msg += (
                f"\n🎉恭喜你完成登神挑战🎉\n你的{jj_var}长度已超过30cm，授予你🎊\"牛々の神\"🎊称号"
                f"\n你的获胜概率已恢复，\"打胶\"与\"嗦\"指令已重新开放，切记不忘初心，继续冲击更高的境界喵！"
            )

        if "challenge_failed_high_win" in at_status:
            uid_msg += (
                f"\n由于你对决的胜利，{bot_name}检测到TA的{jj_var}长度已不足25cm，很遗憾，TA的登神挑战失败，{bot_name}替TA感谢你的鞭策喵！"
                f"\nTA的{jj_var}长度缩短了5cm喵，获胜概率已恢复，\"打胶\"与\"嗦\"指令已重新开放喵！"
            )
        elif "challenge_completed_reduce" in at_status:
            uid_msg += (
                f"\n由于你对决的胜利，{bot_name}检测到TA的{jj_var}长度已不足25cm，很遗憾，TA跌落神坛，{bot_name}替TA感谢你的鞭策喵！"
                f"\nTA的{jj_var}长度缩短了5cm喵，请不忘初心，再次冲击更高的境界喵！"
            )
        elif "length_near_zero" in at_status:
            uid_msg += f"\n由于你对决的胜利，{bot_name}检测到TA已经变成xnn了喵！"
        elif "length_zero_or_negative" in at_status:
            uid_msg += f"\n由于你对决的胜利，{bot_name}检测到TA已经变成女孩子了喵！"

        probability_msg = f"\n你的胜率现在为{await db.get_win_probability(self._db_path, int(uid)):.0%}喵"
        return f"{uid_msg}{probability_msg}"

    async def _handle_pk_loss(self, uid, at, length_increase, length_decrease, jj_var, bot_name):
        """
        PK 失败后处理双方的登神挑战状态更新：
        胜方（对手）：可能开启挑战 / 完成挑战
        败方（己方）：可能挑战失败 / 跌落神坛 / 变成 xnn / 变成女孩子
        """
        uid_status = await db.update_challenge_status(self._db_path, int(uid))
        at_status = await db.update_challenge_status(self._db_path, int(at))

        uid_msg = (
            f"对决失败喵, 在对面{jj_var}的阴影笼罩下你的{jj_var}减小了{length_decrease}cm喵, "
            f"对面增加了{length_increase}cm喵"
        )

        if "challenge_failed_high_win" in uid_status:
            uid_msg += (
                f"\n很遗憾，登神挑战失败，别气馁啦！"
                f"\n你的{jj_var}长度缩短了5cm喵，获胜概率已恢复，\"打胶\"与\"嗦\"指令已重新开放喵！"
            )
        elif "challenge_completed_reduce" in uid_status:
            uid_msg += (
                f"\n很遗憾，你跌落神坛，别气馁啦！"
                f"\n你的{jj_var}长度缩短了5cm喵，请不忘初心，再次冲击更高的境界喵！"
            )
        elif "length_near_zero" in uid_status:
            uid_msg += f"\n你醒啦, 你已经变成xnn了！"
        elif "length_zero_or_negative" in uid_status:
            uid_msg += f"\n你醒啦, 你已经变成女孩子了！"

        if "challenge_started_low_win" in at_status:
            uid_msg += (
                f"\n由于你对决的失败，触犯到了神秘的禁忌，{bot_name}检测到TA的{jj_var}长度超过25cm，已为TA开启✨\"登神长阶\"✨"
                f"\n现在TA的获胜概率变为当前的80%，且无法使用\"打胶\"与\"嗦\"指令，"
                f"请通知TA以将{jj_var}长度提升至30cm为目标与群友pk吧！"
            )
        elif "challenge_success_high_win" in at_status:
            uid_msg += (
                f"\n🎉恭喜你帮助TA完成登神挑战🎉\nTA的{jj_var}长度超过30cm，授予TA🎊\"牛々の神\"🎊称号"
                f"\nTA的获胜概率已恢复，\"打胶\"与\"嗦\"指令已重新开放，请提醒TA不忘初心，继续冲击更高的境界喵！"
            )

        probability_msg = f"\n你的胜率现在为{await db.get_win_probability(self._db_path, int(uid)):.0%}喵"
        return f"{uid_msg}{probability_msg}"

    # ── 日群友 / 透群友 ──────────────────────────────────────────────

    @Command(
        "yinpa",
        description="日群友/透群友 - 透群友互动，支持短命令 日/透@用户",
        pattern=r"^(日|透)(?:群友|群主|管理)?(\s*@[^\s]+)?\s*$",
    )
    async def handle_yinpa(self, **kwargs):
        """
        透群友：核心互动命令。
        - 有 CD（默认 3600 秒）
        - 若未 @ 目标：牛牛 >5cm 要求指定目标；≤5cm 时 50% 概率随机送给群友
        - 检查 ban_id_list 白名单
        - 生成随机注入量（1-100ml），记录到 ejaculation_data 表
        - xnn 或负长度时反透自己
        """
        uid_str = self._get_user_id(kwargs)
        uid = int(uid_str)
        jj_var = _get_jj_variable(self.config.plugin.jj_variable)
        bot_name = self.config.plugin.bot_name
        group_id = self._get_group_id(kwargs)
        stream_id = kwargs["stream_id"]

        if not await db.check_group_allow(self._db_path, group_id):
            await self.ctx.send.text(self.config.plugin.not_allow, stream_id)
            return True, "未开启", 2

        cd_allowed, remaining = _check_cd("fuck", uid_str, self.config.commands.fuck_cd_time)
        if not cd_allowed:
            await self.ctx.send.text(
                f"你已经榨不出来任何东西了, 请先休息{round(remaining, 3)}秒",
                stream_id,
            )
            return True, "CD中", 2

        user_nick = self._get_nick(kwargs) or f"用户{uid}"
        random_nn = random.uniform(0, 1)
        at_target = self._parse_at_target(kwargs)

        if not at_target:
            jj_len = await db.get_jj_length(self._db_path, uid)
            if jj_len > 5:
                await self.ctx.send.text("请使用@指定目标喵", stream_id)
                return True, "需指定目标", 2
            elif 1 <= jj_len <= 5:
                if random_nn < 0.5:
                    await self.ctx.send.text(
                        f"{bot_name}发现你是xnn~现在咱将{user_nick}\n送给随机一位幸运群友色色！",
                        stream_id,
                    )
                else:
                    await self.ctx.send.text("请使用@指定目标喵", stream_id)
                    return True, "需指定目标", 2

        if at_target:
            ban_ids = _get_ban_id_set(self.config.security.ban_id_list)
            if at_target in ban_ids:
                await self.ctx.send.text("该用户无法被透喵", stream_id)
                return True, "白名单用户", 2

        _update_cd("fuck", uid_str)
        if at_target:
            lucky_user = int(at_target)
            await self.ctx.send.text(f"现在咱将把目标\n送给{user_nick}色色！", stream_id)
        else:
            lucky_user = uid

        await asyncio.sleep(2)
        await db.update_activity(self._db_path, lucky_user)
        await db.update_activity(self._db_path, uid)
        await db.ensure_user_in_group(self._db_path, uid, group_id, user_nick)
        await db.ensure_user_in_group(self._db_path, lucky_user, group_id, f"用户{lucky_user}")

        jj_length = await db.get_jj_length(self._db_path, uid)
        if jj_length <= 0 or (1 <= jj_length <= 5 and random_nn < 0.5):
            ejaculation = round(random.uniform(1, 100), 3)
            await db.insert_ejaculation(self._db_path, uid, ejaculation)
            repo = (
                f"好欸！然而{user_nick}({uid})反透了自己呢~\n"
                f"{user_nick}({uid}) 被注入了{ejaculation}毫升的脱氧核糖核酸, "
                f"当日总被注入量为：{await db.get_today_ejaculation_data(self._db_path, uid)}毫升"
            )
        else:
            ejaculation = round(random.uniform(1, 100), 3)
            await db.insert_ejaculation(self._db_path, lucky_user, ejaculation)
            repo = (
                f"好欸！{user_nick}({uid})用时{random.randint(1, 20)}秒 \n"
                f"给 用户{lucky_user} 注入了{ejaculation}毫升的脱氧核糖核酸, "
                f"当日总注入量为：{await db.get_today_ejaculation_data(self._db_path, lucky_user)}毫升"
            )

        await self.ctx.send.text(repo, stream_id)
        return True, "透成功", 2

    # ── ON_START 事件 ─────────────────────────────────────────────────

    @EventHandler(
        "impart_init",
        description="启动时初始化数据库",
        event_type=EventType.ON_START,
    )
    async def handle_init(self, **kwargs):
        """ON_START 事件：数据库初始化实际已在 on_load 中完成，此为确认日志"""
        self.ctx.logger.info("ON_START 事件触发: 数据库初始化已在 on_load 中完成")


def create_plugin():
    """SDK 要求的工厂函数，返回插件实例"""
    return ImpartPlugin()
