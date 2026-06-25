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
    __tablename__ = "groupdata"
    groupid = Column(Integer, primary_key=True, index=True)
    allow = Column(Boolean, nullable=False)


class EjaculationData(Base):
    __tablename__ = "ejaculation_data"
    id = Column(Integer, primary_key=True)
    userid = Column(Integer, nullable=False, index=True)
    date = Column(String(20), nullable=False)
    volume = Column(Float, nullable=False)


class UserGroup(Base):
    __tablename__ = "user_group"
    userid = Column(Integer, primary_key=True)
    groupid = Column(Integer, primary_key=True)
    nickname = Column(String(100), nullable=True)


def get_engine(db_path: str):
    global _engine
    if _engine is None:
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        _engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    return _engine


def get_session_cls(db_path: str):
    global _async_session_cls
    if _async_session_cls is None:
        engine = get_engine(db_path)
        _async_session_cls = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    return _async_session_cls


def reset_engine():
    global _engine, _async_session_cls
    if _engine:
        _engine = None
    _async_session_cls = None


async def init_db(db_path: str):
    engine = get_engine(db_path)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await check_and_add_column(db_path)


async def check_and_add_column(db_path: str):
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
    session_cls = get_session_cls(db_path)
    async with session_cls() as s:
        s.add(UserData(userid=userid, jj_length=10.0, last_masturbation_time=int(time.time()), win_probability=0.5))
        await s.commit()


async def is_in_table(db_path: str, userid: int) -> bool:
    session_cls = get_session_cls(db_path)
    async with session_cls() as s:
        result = await s.execute(select(UserData).where(UserData.userid == userid))
        return result.scalar() is not None


async def get_jj_length(db_path: str, userid: int) -> float:
    session_cls = get_session_cls(db_path)
    async with session_cls() as s:
        result = await s.execute(select(UserData.jj_length).filter(UserData.userid == userid))
        return result.scalar() or 0.0


async def set_jj_length(db_path: str, userid: int, length: float) -> None:
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
    session_cls = get_session_cls(db_path)
    async with session_cls() as s:
        result = await s.execute(select(UserData.win_probability).filter(UserData.userid == userid))
        return result.scalar() or 0.5


async def set_win_probability(db_path: str, userid: int, probability_change: float) -> None:
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
    session_cls = get_session_cls(db_path)
    async with session_cls() as s:
        result = await s.execute(select(GroupData.allow).filter(GroupData.groupid == groupid))
        return result.scalar() or False


async def set_group_allow(db_path: str, groupid: int, allow: bool) -> None:
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
    return time.strftime("%Y-%m-%d", time.localtime())


async def insert_ejaculation(db_path: str, userid: int, volume: float) -> None:
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
    session_cls = get_session_cls(db_path)
    async with session_cls() as s:
        result = await s.execute(select(EjaculationData).filter(EjaculationData.userid == userid))
        return [{"date": row.date, "volume": row.volume} for row in result.scalars()]


async def get_today_ejaculation_data(db_path: str, userid: int) -> float:
    session_cls = get_session_cls(db_path)
    async with session_cls() as s:
        result = await s.execute(
            select(EjaculationData.volume)
            .filter(EjaculationData.userid == userid, EjaculationData.date == get_today())
        )
        return result.scalar() or 0.0


async def punish_all_inactive_users(db_path: str) -> None:
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
    session_cls = get_session_cls(db_path)
    async with session_cls() as s:
        subquery = select(UserGroup.userid).where(UserGroup.groupid == group_id)
        result = await s.execute(
            select(UserData.userid, UserData.jj_length)
            .where(UserData.userid.in_(subquery))
            .order_by(UserData.jj_length.desc())
        )
        return [{"userid": row.userid, "jj_length": row.jj_length} for row in result]
