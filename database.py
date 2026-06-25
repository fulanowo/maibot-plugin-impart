"""
数据库操作层 - SQLAlchemy 异步 ORM

保持与原始 nonebot-plugin-impart 完全兼容的表结构，
同时通过 ALTER TABLE 迁移支持旧数据库中缺少的新列。
新增 user_group 表用于排行榜分群过滤。

所有数据库操作接收 db_path 参数，内部通过全局懒初始化的引擎执行。
"""

import os
import random
import time
from typing import Dict, List, Optional
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import Boolean, Column, Float, Integer, String, select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base

_engine = None
_async_session_cls = None
Base = declarative_base()


class UserData(Base):
    """用户数据表 - 存储每个用户的牛子长度、胜率、登神挑战状态"""

    __tablename__ = "userdata"
    userid = Column(Integer, primary_key=True, index=True)
    jj_length = Column(Float, nullable=False)
    last_masturbation_time = Column(Integer, nullable=False, default=0)
    win_probability = Column(Float, nullable=False, default=0.5)
    is_challenging = Column(Boolean, nullable=False, default=False)
    challenge_completed = Column(Boolean, nullable=False, default=False)
    is_near_zero = Column(Boolean, nullable=False, default=False)
    is_zero_or_neg = Column(Boolean, nullable=False, default=False)


class GroupData(Base):
    """群数据表 - 记录每个群的银趴功能开关状态"""

    __tablename__ = "groupdata"
    groupid = Column(Integer, primary_key=True, index=True)
    allow = Column(Boolean, nullable=False)


class EjaculationData(Base):
    """注入记录表 - 记录每次透操作产生的注入量（ml），按日期聚合"""

    __tablename__ = "ejaculation_data"
    id = Column(Integer, primary_key=True)
    userid = Column(Integer, nullable=False, index=True)
    date = Column(String(20), nullable=False)
    volume = Column(Float, nullable=False)


class UserGroup(Base):
    """用户-群关系表 - 记录用户在群中的昵称，用于排行榜分群过滤和图例显示"""

    __tablename__ = "user_group"
    userid = Column(Integer, primary_key=True)
    groupid = Column(Integer, primary_key=True)
    nickname = Column(String(100), nullable=True)


def get_engine(db_path: str):
    """懒初始化 SQLAlchemy 异步引擎，第一次调用时创建数据库目录和引擎"""
    global _engine
    if _engine is None:
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        _engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    return _engine


def get_session_cls(db_path: str):
    """懒初始化异步 session 工厂，使用 expire_on_commit=False 避免提交后属性过期"""
    global _async_session_cls
    if _async_session_cls is None:
        engine = get_engine(db_path)
        _async_session_cls = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    return _async_session_cls


def reset_engine():
    """重置引擎（用于测试或配置变更后的重新初始化）"""
    global _engine, _async_session_cls
    if _engine:
        _engine = None
    _async_session_cls = None


async def init_db(db_path: str):
    """初始化数据库：创建所有表 + 检查并迁移旧表缺少的列"""
    engine = get_engine(db_path)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await check_and_add_column(db_path)


async def check_and_add_column(db_path: str):
    """检查旧数据库中 userdata 表是否缺少新列，逐条 ALTER TABLE 补充"""
    engine = get_engine(db_path)
    async with engine.begin() as conn:
        result = await conn.execute(sa.text("PRAGMA table_info(userdata)"))
        columns = [row[1] for row in result]
        if "win_probability" not in columns:
            await conn.execute(sa.text("ALTER TABLE userdata ADD COLUMN win_probability FLOAT DEFAULT 0.5"))
        if "is_challenging" not in columns:
            await conn.execute(sa.text("ALTER TABLE userdata ADD COLUMN is_challenging BOOLEAN DEFAULT FALSE"))
        if "challenge_completed" not in columns:
            await conn.execute(sa.text("ALTER TABLE userdata ADD COLUMN challenge_completed BOOLEAN DEFAULT FALSE"))
        if "is_near_zero" not in columns:
            await conn.execute(sa.text("ALTER TABLE userdata ADD COLUMN is_near_zero BOOLEAN DEFAULT FALSE"))
        if "is_zero_or_neg" not in columns:
            await conn.execute(sa.text("ALTER TABLE userdata ADD COLUMN is_zero_or_neg BOOLEAN DEFAULT FALSE"))


async def add_new_user(db_path: str, userid: int) -> None:
    """创建新用户，初始 jj_length=10cm，胜率 0.5"""
    session_cls = get_session_cls(db_path)
    async with session_cls() as s:
        s.add(UserData(userid=userid, jj_length=10.0, last_masturbation_time=int(time.time()), win_probability=0.5))
        await s.commit()


async def is_in_table(db_path: str, userid: int) -> bool:
    """检查用户是否已在 userdata 表中存在"""
    session_cls = get_session_cls(db_path)
    async with session_cls() as s:
        result = await s.execute(select(UserData).where(UserData.userid == userid))
        return result.scalar() is not None


async def get_jj_length(db_path: str, userid: int) -> float:
    """获取用户当前牛子长度，不存在时返回 0.0"""
    session_cls = get_session_cls(db_path)
    async with session_cls() as s:
        result = await s.execute(select(UserData.jj_length).filter(UserData.userid == userid))
        return result.scalar() or 0.0


async def set_jj_length(db_path: str, userid: int, length: float) -> None:
    """在用户当前长度基础上增加/减少指定值（length 可为负），并更新活跃时间"""
    session_cls = get_session_cls(db_path)
    async with session_cls() as s:
        current_length = await get_jj_length(db_path, userid)
        await s.execute(
            update(UserData).where(UserData.userid == userid).values(
                jj_length=round(current_length + length, 3),
                last_masturbation_time=int(time.time()),
            )
        )
        await s.commit()


async def get_win_probability(db_path: str, userid: int) -> float:
    """获取用户当前 PK 胜率，不存在时返回 0.5"""
    session_cls = get_session_cls(db_path)
    async with session_cls() as s:
        result = await s.execute(select(UserData.win_probability).filter(UserData.userid == userid))
        return result.scalar() or 0.5


async def set_win_probability(db_path: str, userid: int, probability_change: float) -> None:
    """调整用户 PK 胜率（±0.01），更新活跃时间"""
    session_cls = get_session_cls(db_path)
    async with session_cls() as s:
        current_probability = await get_win_probability(db_path, userid)
        await s.execute(
            update(UserData).where(UserData.userid == userid).values(
                win_probability=round(current_probability + probability_change, 3),
                last_masturbation_time=int(time.time()),
            )
        )
        await s.commit()


async def update_activity(db_path: str, userid: int) -> None:
    """更新用户最后活跃时间戳（用于不活跃惩罚判断），用户不存在时自动创建"""
    if not await is_in_table(db_path, userid):
        await add_new_user(db_path, userid)
    session_cls = get_session_cls(db_path)
    async with session_cls() as s:
        await s.execute(
            update(UserData).where(UserData.userid == userid).values(
                last_masturbation_time=int(time.time())
            )
        )
        await s.commit()


async def update_challenge_status(db_path: str, userid: int) -> str:
    """
    登神挑战状态机 - 10 种分支判断。

    状态说明：
      - challenge_started_low_win  : 25≤len<30, 挑战开始, 胜率×0.8
      - challenge_completed         : len≥30 完成挑战
      - challenge_failed_high_win   : 挑战中跌出 25, 胜率×1.25, 减 5cm
      - challenge_success_high_win  : 挑战中达 30, 胜率×1.25, 标记完成
      - is_challenging              : 正在挑战中
      - challenge_completed_reduce  : 已完成后再次跌出 25, 减 5cm, 重置标记
      - length_near_zero            : 0<len≤5 首次标记
      - length_zero_or_negative     : len≤0 首次标记
    """
    session_cls = get_session_cls(db_path)
    async with session_cls() as s:
        result = await s.execute(select(UserData).where(UserData.userid == userid))
        user = result.scalar()
        if not user:
            return "user_not_found"

        jj_length = user.jj_length
        is_challenging = user.is_challenging
        challenge_completed = user.challenge_completed
        win_probability = user.win_probability
        is_near_zero = user.is_near_zero
        is_zero_or_neg = user.is_zero_or_neg

        response = ""

        if not is_challenging and not challenge_completed and 25 <= jj_length < 30:
            user.is_challenging = True
            user.win_probability *= 0.8
            response = "challenge_started_low_win"
        elif not is_challenging and not challenge_completed and jj_length >= 30:
            user.challenge_completed = True
            response = "challenge_completed"
        elif is_challenging and not challenge_completed and jj_length < 25:
            user.win_probability *= 1.25
            user.jj_length -= 5
            user.is_challenging = False
            response = "challenge_failed_high_win"
        elif is_challenging and not challenge_completed and jj_length >= 30:
            user.win_probability *= 1.25
            user.is_challenging = False
            user.challenge_completed = True
            response = "challenge_success_high_win"
        elif is_challenging and 25 <= jj_length < 30:
            response = "is_challenging"
        elif challenge_completed and 25 <= jj_length < 30:
            response = "challenge_completed"
        elif challenge_completed and jj_length < 25:
            user.jj_length -= 5
            user.challenge_completed = False
            response = "challenge_completed_reduce"
        elif not is_near_zero and 0 < jj_length <= 5:
            user.is_near_zero = True
            response = "length_near_zero"
        elif is_near_zero and (jj_length <= 0 or jj_length > 5):
            user.is_near_zero = False
        elif not is_zero_or_neg and jj_length <= 0:
            user.is_zero_or_neg = True
            response = "length_zero_or_negative"
        elif is_zero_or_neg and jj_length > 0:
            user.is_zero_or_neg = False

        await s.commit()
        return response


async def check_group_allow(db_path: str, groupid: int) -> bool:
    """检查群是否已开启银趴功能，未找到记录时返回 False"""
    session_cls = get_session_cls(db_path)
    async with session_cls() as s:
        result = await s.execute(select(GroupData.allow).filter(GroupData.groupid == groupid))
        return result.scalar() or False


async def set_group_allow(db_path: str, groupid: int, allow: bool) -> None:
    """设置群的银趴开关状态，群不存在则创建记录"""
    session_cls = get_session_cls(db_path)
    async with session_cls() as s:
        result = await s.execute(select(GroupData).where(GroupData.groupid == groupid))
        existing_group = result.scalar_one_or_none()
        if existing_group is None:
            s.add(GroupData(groupid=groupid, allow=allow))
        else:
            existing_group.allow = allow
        await s.commit()


def get_today() -> str:
    """返回当前日期字符串 YYYY-MM-DD"""
    return time.strftime("%Y-%m-%d", time.localtime())


async def insert_ejaculation(db_path: str, userid: int, volume: float) -> None:
    """记录注入量：同日数据累加，跨日新增记录"""
    now_date = get_today()
    session_cls = get_session_cls(db_path)
    async with session_cls() as s:
        result = await s.execute(
            select(EjaculationData.volume)
            .filter(EjaculationData.userid == userid, EjaculationData.date == now_date)
        )
        current_volume = result.scalar()
        if current_volume is not None:
            await s.execute(
                update(EjaculationData)
                .where(EjaculationData.userid == userid, EjaculationData.date == now_date)
                .values(volume=round(current_volume + volume, 3))
            )
        else:
            s.add(EjaculationData(userid=userid, date=now_date, volume=volume))
        await s.commit()


async def get_ejaculation_data(db_path: str, userid: int) -> List[Dict]:
    """获取用户所有注入记录（按日期聚合），用于折线图展示"""
    session_cls = get_session_cls(db_path)
    async with session_cls() as s:
        result = await s.execute(select(EjaculationData).filter(EjaculationData.userid == userid))
        return [{"date": row.date, "volume": row.volume} for row in result.scalars()]


async def get_today_ejaculation_data(db_path: str, userid: int) -> float:
    """获取用户当日注入总量，未记录时返回 0.0"""
    session_cls = get_session_cls(db_path)
    async with session_cls() as s:
        result = await s.execute(
            select(EjaculationData.volume)
            .filter(EjaculationData.userid == userid, EjaculationData.date == get_today())
        )
        return result.scalar() or 0.0


async def punish_all_inactive_users(db_path: str) -> None:
    """每日不活跃惩罚：超过 24h 未活跃且 jj_length > 1 的用户减少 0~1 随机长度"""
    session_cls = get_session_cls(db_path)
    async with session_cls() as s:
        result = await s.execute(
            select(UserData).filter(
                UserData.last_masturbation_time < (time.time() - 86400),
                UserData.jj_length > 1
            )
        )
        for user in result.scalars():
            user.jj_length = round(user.jj_length - random.random(), 3)
        await s.commit()


async def ensure_user_in_group(db_path: str, userid: int, groupid: int, nickname: str) -> None:
    """确保用户-群关系记录存在，用于排行榜分群过滤。groupid=0（私聊）时跳过"""
    if groupid == 0:
        return
    session_cls = get_session_cls(db_path)
    async with session_cls() as s:
        result = await s.execute(
            select(UserGroup).where(
                UserGroup.userid == userid,
                UserGroup.groupid == groupid
            )
        )
        existing = result.scalar()
        if existing:
            if nickname:
                existing.nickname = nickname
        else:
            s.add(UserGroup(userid=userid, groupid=groupid, nickname=nickname or None))
        await s.commit()


async def get_group_nickname(db_path: str, userid: int, groupid: int) -> Optional[str]:
    """获取用户在群中的昵称（用于排行榜图例），无记录时返回 None"""
    if groupid == 0:
        return None
    session_cls = get_session_cls(db_path)
    async with session_cls() as s:
        result = await s.execute(
            select(UserGroup.nickname).where(
                UserGroup.userid == userid,
                UserGroup.groupid == groupid
            )
        )
        return result.scalar()


async def get_sorted(db_path: str, group_id: int) -> List[Dict]:
    """获取指定群内的用户长度排行榜（降序），通过 user_group 表过滤同群用户"""
    session_cls = get_session_cls(db_path)
    async with session_cls() as s:
        subquery = select(UserGroup.userid).where(UserGroup.groupid == group_id)
        result = await s.execute(
            select(UserData.userid, UserData.jj_length)
            .where(UserData.userid.in_(subquery))
            .order_by(UserData.jj_length.desc())
        )
        return [{"userid": row.userid, "jj_length": row.jj_length} for row in result]
