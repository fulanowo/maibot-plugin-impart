import asyncio
import base64
import random
import re
import time
from datetime import datetime, timedelta
from random import choice
from typing import Any, ClassVar, Dict, List, Optional, Tuple, Type

from src.plugin_system import (
    BasePlugin,
    register_plugin,
    BaseCommand,
    BaseEventHandler,
    ComponentInfo,
    ConfigField,
    EventType,
    MaiMessages,
)
from src.common.logger import get_logger

import database as db
from draw_chart import draw_bar_chart

logger = get_logger("mai_plugin_impart")

_cd_cache: Dict[str, Dict[str, float]] = {
    "dajiao": {},
    "pk": {},
    "suo": {},
    "fuck": {},
}


def _check_cd(cd_type: str, uid: str, cd_time: int) -> Tuple[bool, float]:
    cache = _cd_cache[cd_type]
    last_time = cache.get(uid, 0)
    elapsed = time.time() - last_time
    return (True, 0) if elapsed > cd_time else (False, cd_time - elapsed)


def _update_cd(cd_type: str, uid: str) -> None:
    _cd_cache[cd_type][uid] = time.time()


def _delete_cd(cd_type: str, uid: str) -> None:
    _cd_cache[cd_type].pop(uid, None)


def _get_random_num() -> float:
    rand = random.random()
    return round(random.uniform(0, 1) if rand > 0.1 else random.uniform(1, 2), 3)


def _parse_at(raw_message: str) -> Optional[str]:
    m = re.search(r"@(\d+)", raw_message)
    return m.group(1) if m else None


def _get_jj_variable(config_str: str) -> str:
    parts = [p.strip() for p in config_str.split(",") if p.strip()]
    return choice(parts) if parts else "牛子"


def _get_ban_id_set(config_str: str) -> set:
    if not config_str:
        return set()
    return set(x.strip() for x in config_str.split(",") if x.strip())


def _get_db_path(config_getter) -> str:
    return config_getter("plugin.db_path", "data/impart.db")


class HelpCommand(BaseCommand):
    command_name = "help"
    command_description = "银趴帮助 - 显示使用说明"
    command_pattern = r"^(银趴|impart)(介绍|帮助)$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        usage_text = (
            "impart功能说明:\n"
            "[日群友|透群友|日群主|透群主|日管理|透管理]\n"
            "字面意思,使用<透群友>时可@用户\n"
            "[pk|对决]\n"
            "通过random实现pk,胜方获取败方随机数/2的牛牛长度;\n"
            "初始胜率为50%,pk后胜方胜率-1%,败方胜率+1%\n"
            "<牛牛长度超过25时会触发神秘任务>\n"
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
        await self.send_text(usage_text)
        return True, "帮助信息已发送", True


class QueryCommand(BaseCommand):
    command_name = "query"
    command_description = "查询 - 查询用户牛子长度"
    command_pattern = r"^查询(\s+@?(?P<target>\d+))?$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        db_path = _get_db_path(self.get_config)
        target_str = self.matched_groups.get("target")
        target_uid = int(target_str) if target_str else int(self.user_id)
        pronoun = "你" if str(target_uid) == self.user_id else "TA"
        jj_var = _get_jj_variable(self.get_config("plugin.jj_variable", "牛子,牛牛,newnew"))

        if not await db.is_in_table(db_path, target_uid):
            await db.add_new_user(db_path, target_uid)
            await self.send_text(f"{pronoun}还没有创建{jj_var}喵, 咱帮{pronoun}创建了喵, 目前长度是10cm喵")
            return True, "创建成功", True

        length = await db.get_jj_length(db_path, target_uid)

        if length >= 30:
            msg = f"✨牛々の神✨\n{pronoun}的{jj_var}目前长度为{length}cm喵"
        elif 30 > length > 5:
            msg = f"{pronoun}的{jj_var}目前长度为{length}cm喵"
        elif 5 >= length > 1:
            msg = f"{pronoun}已经是xnn啦！\n{pronoun}的{jj_var}目前长度为{length}cm喵"
        elif 1 >= length > 0:
            msg = f"{pronoun}快要变成女孩子啦！\n{pronoun}的{jj_var}目前长度为{length}cm喵"
        else:
            msg = f"{pronoun}已经是女孩子啦！\n{pronoun}的{jj_var}目前长度为{length}cm喵"

        await self.send_text(msg)
        return True, "查询成功", True


class JjRankCommand(BaseCommand):
    command_name = "jjrank"
    command_description = "jj排行榜 - 查看牛子排行榜"
    command_pattern = r"^(jj|牛牛)(排行榜|排名|榜单|rank)$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        db_path = _get_db_path(self.get_config)
        uid = int(self.user_id)
        jj_var = _get_jj_variable(self.get_config("plugin.jj_variable", "牛子,牛牛,newnew"))

        rankdata = await db.get_sorted(db_path)
        if len(rankdata) < 5:
            await self.send_text("目前记录的数据量小于5, 无法显示rank喵")
            return True, "数据不足", True

        top5 = rankdata[:5]
        last5 = rankdata[-5:]

        index = [i for i in range(len(rankdata)) if rankdata[i]["userid"] == uid]
        if not index:
            await db.add_new_user(db_path, uid)
            await self.send_text(f"你还没有创建{jj_var}看不到rank喵, 咱帮你创建了喵, 目前长度是10cm喵")
            return True, "创建成功", True

        user_rank = index[0] + 1

        data = {}
        for i, entry in enumerate(top5):
            data[f"TOP{i+1}"] = entry["jj_length"]
        for i, entry in enumerate(last5):
            data[f"LAST{len(last5)-i}"] = entry["jj_length"]

        img_bytes = await draw_bar_chart.draw_bar_chart(data)
        img_b64 = base64.b64encode(img_bytes).decode("utf-8")
        await self.send_image(img_b64)
        await self.send_text(f"你的排名为{user_rank}喵")
        return True, "排行榜已发送", True


class InjectionQueryCommand(BaseCommand):
    command_name = "injection_query"
    command_description = "注入查询 - 查询被注入量"
    command_pattern = r"^注入查询(\s+@?(?P<target>\d+))?(\s+(?P<all>历史|全部))?$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        db_path = _get_db_path(self.get_config)
        target_str = self.matched_groups.get("target")
        target_id = int(target_str) if target_str else int(self.user_id)
        is_all = self.matched_groups.get("all") in ("历史", "全部")
        replay1 = "该用户" if target_str else "您"

        if is_all:
            data = await db.get_ejaculation_data(db_path, target_id)
            if not data:
                await self.send_text(f"{replay1}历史总被注射量为0ml")
                return True, "查询成功", True
            ejaculation = 0.0
            inject_data = {}
            for item in data:
                ejaculation += item["volume"]
                inject_data[item["date"]] = item["volume"]
            if len(inject_data) < 2:
                await self.send_text(f"{replay1}历史总被注射量为{ejaculation}ml")
                return True, "查询成功", True

            img_bytes = await draw_bar_chart.draw_line_chart(inject_data)
            img_b64 = base64.b64encode(img_bytes).decode("utf-8")
            await self.send_text(f"{replay1}历史总被注射量为{ejaculation}ml")
            await self.send_image(img_b64)
        else:
            ejaculation = await db.get_today_ejaculation_data(db_path, target_id)
            await self.send_text(f"{replay1}当日总被注射量为{ejaculation}ml")

        return True, "查询成功", True


class DajiaoCommand(BaseCommand):
    command_name = "dajiao"
    command_description = "打胶/开导 - 增加自己的牛子长度"
    command_pattern = r"^(打胶|开导)$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        db_path = _get_db_path(self.get_config)
        uid = int(self.user_id)
        uid_str = str(uid)
        jj_var = _get_jj_variable(self.get_config("plugin.jj_variable", "牛子,牛牛,newnew"))

        cd_allowed, remaining = _check_cd("dajiao", uid_str, self.get_config("commands.dj_cd_time", 300))
        if not cd_allowed:
            await self.send_text(f"你已经打不动了喵, 请等待{round(remaining, 3)}秒后再打喵")
            return True, "CD中", True

        _update_cd("dajiao", uid_str)

        if not await db.is_in_table(db_path, uid):
            await db.add_new_user(db_path, uid)
            await self.send_text(f"你还没有创建{jj_var}, 咱帮你创建了喵, 目前长度是10cm喵")
            return True, "创建成功", True

        uid_length = await db.get_jj_length(db_path, uid)
        random_num = _get_random_num()
        uid_status = await db.update_challenge_status(db_path, uid)

        if "is_challenging" in uid_status:
            await self.send_text(f"你的{jj_var}长度在任务范围内，不允许打胶，请专心与群友pk！")
            return True, "挑战中", True

        await db.set_jj_length(db_path, uid, random_num)
        new_length = await db.get_jj_length(db_path, uid)

        bot_name = self.get_config("plugin.bot_name", "BOT")
        if uid_length < 25 <= new_length:
            await db.update_challenge_status(db_path, uid)
            msg = (f"打胶结束喵, 你的{jj_var}很满意喵, 长了{random_num}cm喵"
                   f"\n由于你无休止的打胶，触犯到了神秘的禁忌，{bot_name}检测到你的{jj_var}长度超过25cm，"
                   f"已为你开启✨\"登神长阶\"✨"
                   f"\n你现在的获胜概率变为当前的80%，且无法使用\"打胶\"与\"嗦\"指令，"
                   f"请以将{jj_var}长度提升至30cm为目标与他人pk吧！")
        else:
            msg = f"打胶结束喵, 你的{jj_var}很满意喵, 长了{random_num}cm喵, 目前长度为{new_length}cm喵"

        await self.send_text(msg)
        return True, "打胶成功", True


class SuoCommand(BaseCommand):
    command_name = "suo"
    command_description = "嗦牛子/嗦 - 增加目标用户的牛子长度"
    command_pattern = r"^嗦(?:牛子)?(\s+@?(?P<target>\d+))?$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        db_path = _get_db_path(self.get_config)
        uid = int(self.user_id)
        uid_str = str(uid)
        jj_var = _get_jj_variable(self.get_config("plugin.jj_variable", "牛子,牛牛,newnew"))

        cd_allowed, remaining = _check_cd("suo", uid_str, self.get_config("commands.suo_cd_time", 300))
        if not cd_allowed:
            await self.send_text(f"你已经嗦不动了喵, 请等待{round(remaining, 3)}秒后再嗦喵")
            return True, "CD中", True

        _update_cd("suo", uid_str)

        raw_message = self.message.raw_message if hasattr(self.message, "raw_message") else ""
        target_str = self.matched_groups.get("target") or _parse_at(raw_message)
        target_id = int(target_str) if target_str else uid
        pronoun = "你" if target_id == uid else "TA"

        if not await db.is_in_table(db_path, target_id):
            await db.add_new_user(db_path, target_id)
            _delete_cd("suo", uid_str)
            await self.send_text(f"{pronoun}还没有创建{jj_var}喵, 咱帮{pronoun}创建了喵, 目前长度是10cm喵")
            return True, "创建成功", True

        current_length = await db.get_jj_length(db_path, target_id)
        random_num = _get_random_num()
        target_status = await db.update_challenge_status(db_path, target_id)

        if "is_challenging" in target_status:
            await self.send_text(f"{pronoun}的{jj_var}长度在任务范围内，不准嗦！请专心与群友pk！")
            return True, "挑战中", True

        await db.set_jj_length(db_path, target_id, random_num)
        new_length = await db.get_jj_length(db_path, target_id)

        bot_name = self.get_config("plugin.bot_name", "BOT")
        if current_length < 25 <= new_length:
            await db.update_challenge_status(db_path, target_id)
            msg = (f"{pronoun}的{jj_var}很满意喵, 嗦长了{random_num}cm喵"
                   f"\n由于{pronoun}无休止的嗦与被嗦，触犯到了神秘的禁忌，{bot_name}检测到{pronoun}的{jj_var}长度超过25cm，"
                   f"\n已为{pronoun}开启✨\"登神长阶\"✨，{pronoun}现在的获胜概率变为80%，且无法使用\"打胶\"与\"嗦\"指令，"
                   f"请以将{jj_var}长度提升至30cm为目标与他人pk吧！")
        else:
            msg = f"{pronoun}的{jj_var}很满意喵, 嗦长了{random_num}cm喵, 目前长度为{new_length}cm喵"

        await self.send_text(msg)
        return True, "嗦成功", True


class ToggleCommand(BaseCommand):
    command_name = "toggle"
    command_description = "开启/关闭银趴 - 管理员开关impart功能"
    command_pattern = r"^(开始|开启|关闭|禁止)(银趴|impart)$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        db_path = _get_db_path(self.get_config)
        raw_message = self.message.raw_message if hasattr(self.message, "raw_message") else ""
        m = re.match(r"^(开始|开启|关闭|禁止)", raw_message)
        if not m:
            return True, "无法解析命令", True
        command = m.group(1)
        group_id = int(self.group_id) if self.group_id else 0

        if "开启" in command or "开始" in command:
            await db.set_group_allow(db_path, group_id, True)
            await self.send_text("功能已开启喵")
        elif "禁止" in command or "关闭" in command:
            await db.set_group_allow(db_path, group_id, False)
            await self.send_text("功能已禁用喵")

        return True, "操作成功", True


class PKCommand(BaseCommand):
    command_name = "pk"
    command_description = "PK/对决 - 与群友进行牛子对决"
    command_pattern = r"^(pk|对决)(\s+@?(?P<target>\d+))?$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        db_path = _get_db_path(self.get_config)
        uid = int(self.user_id)
        uid_str = str(uid)
        jj_var = _get_jj_variable(self.get_config("plugin.jj_variable", "牛子,牛牛,newnew"))

        group_id = int(self.group_id) if self.group_id else 0
        if not await db.check_group_allow(db_path, group_id):
            await self.send_text(self.get_config("plugin.not_allow", "群内还未开启impart游戏, 请管理员或群主发送\"开始银趴\", \"禁止银趴\"以开启/关闭该功能"))
            return True, "未开启", True

        cd_allowed, remaining = _check_cd("pk", uid_str, self.get_config("commands.pk_cd_time", 60))
        if not cd_allowed:
            await self.send_text(f"你已经pk不动了喵, 请等待{round(remaining, 3)}秒后再pk喵")
            return True, "CD中", True

        _update_cd("pk", uid_str)

        raw_message = self.message.raw_message if hasattr(self.message, "raw_message") else ""
        target_str = self.matched_groups.get("target") or _parse_at(raw_message)
        if not target_str:
            await self.send_text("请指定要PK的对象喵，例如: pk @用户")
            return True, "无目标", True

        at = target_str
        if at == uid_str:
            await self.send_text("你不能pk自己喵")
            return True, "无法pk自己", True

        bot_name = self.get_config("plugin.bot_name", "BOT")

        if await db.is_in_table(db_path, uid) and await db.is_in_table(db_path, int(at)):
            win_rand = random.random()
            win = win_rand < await db.get_win_probability(db_path, uid)
            rn = _get_random_num()
            length_increase = round(rn / 2, 3)
            length_decrease = rn

            if win:
                await db.set_win_probability(db_path, uid, -0.01)
                await db.set_win_probability(db_path, int(at), 0.01)
                await db.set_jj_length(db_path, uid, rn / 2)
                await db.set_jj_length(db_path, int(at), -rn)
                msg = await self._handle_pk_win(db_path, uid, at, length_increase, length_decrease, jj_var, bot_name)
            else:
                await db.set_win_probability(db_path, uid, 0.01)
                await db.set_win_probability(db_path, int(at), -0.01)
                await db.set_jj_length(db_path, uid, -rn)
                await db.set_jj_length(db_path, int(at), rn / 2)
                msg = await self._handle_pk_loss(db_path, uid, at, length_increase, length_decrease, jj_var, bot_name)

            await self.send_text(msg)
        else:
            if not await db.is_in_table(db_path, uid):
                await db.add_new_user(db_path, uid)
            if not await db.is_in_table(db_path, int(at)):
                await db.add_new_user(db_path, int(at))
            _delete_cd("pk", uid_str)
            await self.send_text(f"你或对面还没有创建{jj_var}喵, 咱全帮你创建了喵, 你们的{jj_var}长度都是10cm喵")

        return True, "PK完成", True

    async def _handle_pk_win(self, db_path: str, uid: str, at: str, length_increase: float, length_decrease: float, jj_var: str, bot_name: str) -> str:
        uid_status = await db.update_challenge_status(db_path, int(uid))
        at_status = await db.update_challenge_status(db_path, int(at))

        uid_msg = f"对决胜利喵, 你的{jj_var}增加了{length_increase}cm喵, 对面则在你的阴影笼罩下减小了{length_decrease}cm喵"

        if "challenge_started_low_win" in uid_status:
            uid_msg += (f"\n{bot_name}检测到你的{jj_var}长度超过25cm，已为你开启✨\"登神长阶\"✨"
                        f"\n你现在的获胜概率变为当前的80%，且无法使用\"打胶\"与\"嗦\"指令，"
                        f"请以将{jj_var}长度提升至30cm为目标与他人pk吧!")
        elif "challenge_success_high_win" in uid_status:
            uid_msg += (f"\n🎉恭喜你完成登神挑战🎉\n你的{jj_var}长度已超过30cm，授予你🎊\"牛々の神\"🎊称号"
                        f"\n你的获胜概率已恢复，\"打胶\"与\"嗦\"指令已重新开放，切记不忘初心，继续冲击更高的境界喵！")

        if "challenge_failed_high_win" in at_status:
            uid_msg += (f"\n由于你对决的胜利，{bot_name}检测到TA的{jj_var}长度已不足25cm，很遗憾，TA的登神挑战失败，{bot_name}替TA感谢你的鞭策喵！"
                        f"\nTA的{jj_var}长度缩短了5cm喵，获胜概率已恢复，\"打胶\"与\"嗦\"指令已重新开放喵！")
        elif "challenge_completed_reduce" in at_status:
            uid_msg += (f"\n由于你对决的胜利，{bot_name}检测到TA的{jj_var}长度已不足25cm，很遗憾，TA跌落神坛，{bot_name}替TA感谢你的鞭策喵！"
                        f"\nTA的{jj_var}长度缩短了5cm喵，请不忘初心，再次冲击更高的境界喵！")
        elif "length_near_zero" in at_status:
            uid_msg += f"\n由于你对决的胜利，{bot_name}检测到TA已经变成xnn了喵！"
        elif "length_zero_or_negative" in at_status:
            uid_msg += f"\n由于你对决的胜利，{bot_name}检测到TA已经变成女孩子了喵！"

        probability_msg = f"\n你的胜率现在为{await db.get_win_probability(db_path, int(uid)):.0%}喵"
        return f"{uid_msg}{probability_msg}"

    async def _handle_pk_loss(self, db_path: str, uid: str, at: str, length_increase: float, length_decrease: float, jj_var: str, bot_name: str) -> str:
        uid_status = await db.update_challenge_status(db_path, int(uid))
        at_status = await db.update_challenge_status(db_path, int(at))

        uid_msg = f"对决失败喵, 在对面{jj_var}的阴影笼罩下你的{jj_var}减小了{length_decrease}cm喵, 对面增加了{length_increase}cm喵"

        if "challenge_failed_high_win" in uid_status:
            uid_msg += (f"\n很遗憾，登神挑战失败，别气馁啦！"
                        f"\n你的{jj_var}长度缩短了5cm喵，获胜概率已恢复，\"打胶\"与\"嗦\"指令已重新开放喵！")
        elif "challenge_completed_reduce" in uid_status:
            uid_msg += (f"\n很遗憾，你跌落神坛，别气馁啦！"
                        f"\n你的{jj_var}长度缩短了5cm喵，请不忘初心，再次冲击更高的境界喵！")
        elif "length_near_zero" in uid_status:
            uid_msg += f"\n你醒啦, 你已经变成xnn了！"
        elif "length_zero_or_negative" in uid_status:
            uid_msg += f"\n你醒啦, 你已经变成女孩子了！"

        if "challenge_started_low_win" in at_status:
            uid_msg += (f"\n由于你对决的失败，触犯到了神秘的禁忌，{bot_name}检测到TA的{jj_var}长度超过25cm，已为TA开启✨\"登神长阶\"✨"
                        f"\n现在TA的获胜概率变为当前的80%，且无法使用\"打胶\"与\"嗦\"指令，"
                        f"请通知TA以将{jj_var}长度提升至30cm为目标与群友pk吧！")
        elif "challenge_success_high_win" in at_status:
            uid_msg += (f"\n🎉恭喜你帮助TA完成登神挑战🎉\nTA的{jj_var}长度超过30cm，授予TA🎊\"牛々の神\"🎊称号"
                        f"\nTA的获胜概率已恢复，\"打胶\"与\"嗦\"指令已重新开放，请提醒TA不忘初心，继续冲击更高的境界喵！")

        probability_msg = f"\n你的胜率现在为{await db.get_win_probability(db_path, int(uid)):.0%}喵"
        return f"{uid_msg}{probability_msg}"


class YinpaCommand(BaseCommand):
    command_name = "yinpa"
    command_description = "日群友/透群友 - 透群友互动"
    command_pattern = r"^(日|透)(群友|群主|管理)$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        db_path = _get_db_path(self.get_config)
        uid = int(self.user_id)
        uid_str = str(uid)
        jj_var = _get_jj_variable(self.get_config("plugin.jj_variable", "牛子,牛牛,newnew"))
        ban_id_str = self.get_config("security.ban_id_list", "")
        ban_set = _get_ban_id_set(ban_id_str)
        bot_name = self.get_config("plugin.bot_name", "BOT")

        group_id = int(self.group_id) if self.group_id else 0
        if not await db.check_group_allow(db_path, group_id):
            await self.send_text(self.get_config("plugin.not_allow", "群内还未开启impart游戏"))
            return True, "未开启", True

        cd_allowed, remaining = _check_cd("fuck", uid_str, self.get_config("commands.fuck_cd_time", 3600))
        if not cd_allowed:
            await self.send_text(f"你已经榨不出来任何东西了, 请先休息{round(remaining, 3)}秒")
            return True, "CD中", True
        _update_cd("fuck", uid_str)

        raw_message = self.message.raw_message if hasattr(self.message, "raw_message") else ""
        command_match = re.match(r"^(日|透)(群友|群主|管理)", raw_message)
        if not command_match:
            return True, "无法解析命令", True
        command_type = command_match.group(2)
        user_nick = self.user_nickname or f"用户{uid}"

        random_nn = random.uniform(0, 1)
        at_target = _parse_at(raw_message)

        if command_type == "群友":
            if at_target:
                lucky_user = int(at_target)
                await self.send_text(f"现在咱将把目标\n送给{user_nick}色色！")
            else:
                lucky_user = uid
                jj_len = await db.get_jj_length(db_path, uid)
                if jj_len > 5:
                    await self.send_text(f"现在咱将随机抽取一位幸运群友\n送给{user_nick}色色！\n（使用@指定目标效果更佳）")
                elif 5 >= jj_len > 0:
                    if random_nn < 0.5:
                        await self.send_text(f"{bot_name}发现你是xnn~现在咱将{user_nick}\n送给随机一位幸运群友色色！\n（使用@指定目标）")
                    else:
                        await self.send_text(f"现在咱将随机抽取一位幸运群友\n送给{user_nick}色色！\n（使用@指定目标）")
                else:
                    await self.send_text(f"唔...你透不了哦~\n现在咱将{user_nick}\n送给随机一位幸运群友色色！\n（使用@指定目标）")
                return True, "需指定目标", True
        else:
            if at_target:
                lucky_user = int(at_target)
                role_name = "群主" if command_type == "群主" else "管理"
                await self.send_text(f"现在咱将把{role_name}\n送给{user_nick}色色！")
            else:
                await self.send_text(f"无法确定{'群主' if command_type == '群主' else '管理'}身份，请@指定目标喵")
                return True, "需指定目标", True

        await asyncio.sleep(2)
        await db.update_activity(db_path, lucky_user)
        await db.update_activity(db_path, uid)

        jj_length = await db.get_jj_length(db_path, uid)
        if jj_length <= 0 or (5 >= jj_length > 0 and random_nn < 0.5):
            ejaculation = round(random.uniform(1, 100), 3)
            await db.insert_ejaculation(db_path, uid, ejaculation)
            repo = (f"好欸！{user_nick}({uid})用时{random.randint(1, 20)}秒 \n"
                    f"给 {user_nick}({uid}) 注入了{ejaculation}毫升的脱氧核糖核酸, "
                    f"当日总注入量为：{await db.get_today_ejaculation_data(db_path, uid)}毫升")
        else:
            ejaculation = round(random.uniform(1, 100), 3)
            await db.insert_ejaculation(db_path, lucky_user, ejaculation)
            repo = (f"好欸！{user_nick}({uid})用时{random.randint(1, 20)}秒 \n"
                    f"给 {user_nick}({uid}) 注入了{ejaculation}毫升的脱氧核糖核酸, "
                    f"当日总注入量为：{await db.get_today_ejaculation_data(db_path, lucky_user)}毫升")

        await self.send_text(repo)
        return True, "透成功", True


class InitHandler(BaseEventHandler):
    event_type = EventType.ON_START
    handler_name = "impart_init_handler"
    handler_description = "启动时初始化数据库"

    async def execute(self, message: Optional[Any]) -> Tuple[bool, bool, Optional[str], None, None]:
        db_path = self.get_config("plugin.db_path", "data/impart.db")
        try:
            await db.init_db(db_path)
            logger.info(f"[mai_plugin_impart] 数据库初始化完成: {db_path}")
        except Exception as e:
            logger.error(f"[mai_plugin_impart] 数据库初始化失败: {e}")
        return True, True, None, None, None


class DailyResetHandler(BaseEventHandler):
    event_type = EventType.ON_START
    handler_name = "impart_daily_reset_handler"
    handler_description = "启动每日不活跃惩罚定时任务"

    async def execute(self, message: Optional[Any]) -> Tuple[bool, bool, Optional[str], None, None]:
        self._task = asyncio.create_task(self._daily_loop())
        logger.info("[mai_plugin_impart] 每日重置任务已启动")
        return True, True, None, None, None

    async def _daily_loop(self):
        while True:
            now = datetime.now()
            next_run = now.replace(hour=0, minute=0, second=0) + timedelta(days=1)
            sleep_seconds = (next_run - now).total_seconds()
            await asyncio.sleep(sleep_seconds)

            db_path = self.get_config("plugin.db_path", "data/impart.db")
            isalive = self.get_config("commands.isalive", False)
            if isalive:
                try:
                    await db.punish_all_inactive_users(db_path)
                    logger.info("[mai_plugin_impart] 每日不活跃惩罚已执行")
                except Exception as e:
                    logger.error(f"[mai_plugin_impart] 每日惩罚执行失败: {e}")


@register_plugin
class ImpartPlugin(BasePlugin):
    plugin_name: str = "mai_plugin_impart"
    enable_plugin: bool = True
    dependencies: List[str] = []
    python_dependencies: List[str] = ["sqlalchemy", "aiosqlite", "Pillow"]
    config_file_name: str = "config.toml"

    config_section_descriptions = {
        "plugin": "插件基本配置",
        "commands": "命令配置（CD 时间等）",
        "security": "安全与白名单",
        "challenge": "登神挑战配置",
    }

    config_schema: dict = {
        "plugin": {
            "enabled": ConfigField(type=bool, default=True, description="是否启用插件"),
            "db_path": ConfigField(type=str, default="data/impart.db", description="数据库文件路径"),
            "not_allow": ConfigField(type=str, default="群内还未开启impart游戏, 请管理员或群主发送\"开始银趴\", \"禁止银趴\"以开启/关闭该功能", description="未开启时的提示消息"),
            "jj_variable": ConfigField(type=str, default="牛子,牛牛,newnew", description="牛牛变量名列表（逗号分隔）"),
            "bot_name": ConfigField(type=str, default="BOT", description="机器人称呼"),
        },
        "commands": {
            "dj_cd_time": ConfigField(type=int, default=300, description="打胶冷却时间（秒）"),
            "pk_cd_time": ConfigField(type=int, default=60, description="PK冷却时间（秒）"),
            "suo_cd_time": ConfigField(type=int, default=300, description="嗦冷却时间（秒）"),
            "fuck_cd_time": ConfigField(type=int, default=3600, description="透群友冷却时间（秒）"),
            "isalive": ConfigField(type=bool, default=False, description="是否开启不活跃惩罚"),
        },
        "security": {
            "ban_id_list": ConfigField(type=str, default="", description="禁止名单（逗号分隔的QQ号）"),
        },
        "challenge": {
            "challenge_threshold": ConfigField(type=int, default=25, description="登神挑战触发长度"),
            "success_threshold": ConfigField(type=int, default=30, description="登神挑战完成长度"),
            "fail_penalty": ConfigField(type=int, default=5, description="挑战失败惩罚缩减长度"),
            "win_rate_multiplier": ConfigField(type=float, default=1.25, description="挑战失败胜率恢复倍率"),
        },
    }

    def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:
        return [
            (HelpCommand.get_command_info(), HelpCommand),
            (QueryCommand.get_command_info(), QueryCommand),
            (JjRankCommand.get_command_info(), JjRankCommand),
            (InjectionQueryCommand.get_command_info(), InjectionQueryCommand),
            (DajiaoCommand.get_command_info(), DajiaoCommand),
            (SuoCommand.get_command_info(), SuoCommand),
            (ToggleCommand.get_command_info(), ToggleCommand),
            (PKCommand.get_command_info(), PKCommand),
            (YinpaCommand.get_command_info(), YinpaCommand),
            (InitHandler.get_handler_info(), InitHandler),
            (DailyResetHandler.get_handler_info(), DailyResetHandler),
        ]
