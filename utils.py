"""
mai_plugin_impart 工具函数模块

通用工具函数，可被 plugin.py 中的各个 Command 复用。
当前为 MaiBot Plugin Kit 模板保留，可根据需要扩展。
"""

import asyncio
import datetime
from typing import Optional, Dict, Any


def format_time(timestamp: Optional[float] = None, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """格式化时间戳为字符串，timestamp=None 时使用当前时间"""
    if timestamp is None:
        dt = datetime.datetime.now()
    else:
        dt = datetime.datetime.fromtimestamp(timestamp)
    return dt.strftime(fmt)


def truncate_text(text: str, max_len: int = 100, suffix: str = "...") -> str:
    """截断过长的文本，超出 max_len 时以 suffix 结尾"""
    if len(text) <= max_len:
        return text
    return text[: max_len - len(suffix)] + suffix


async def safe_http_get(url: str, timeout: int = 10) -> Optional[Dict[str, Any]]:
    """
    安全的 HTTP GET 请求（需要额外安装 aiohttp）

    使用前需在 _manifest.json 的 dependencies 中添加 aiohttp。
    返回 JSON 响应字典，失败时返回 None。
    """
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                if resp.status == 200:
                    return await resp.json()
                return None
    except ImportError:
        raise ImportError("请先安装 aiohttp：pip install aiohttp")
    except Exception as e:
        return None
