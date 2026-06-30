"""
B站 API 交互模块

封装与哔哩哔哩 API 的交互逻辑，包括 BV 号解析、视频信息获取、
音频下载地址获取等功能。
"""

import re
from typing import Any

import requests

from tools.config import (
    HTTP_HEADERS,
    BILI_VIDEO_INFO_API,
    BILI_PLAYURL_API,
    BILI_VIDEO_BASE_URL,
)


def parse_bvid(input_str: str) -> str | None:
    """
    从用户输入的字符串中解析出 BV 号。

    支持两种输入格式：
    - 纯 BV 号，如 ``BV1xx2xx3xx4xx``
    - 视频链接 URL，如 ``https://www.bilibili.com/video/BV1xx2xx3xx4xx``

    Args:
        input_str: 用户输入的原始字符串

    Returns:
        解析到的 BV 号字符串，解析失败返回 None
    """
    # 去除首尾空白字符
    input_str = input_str.strip()

    # 尝试从 URL 中提取 BV 号
    match = re.search(r"bilibili\.com/video/(BV[a-zA-Z0-9]+)", input_str)
    if match:
        return match.group(1)

    # 尝试匹配纯 BV 号格式
    match = re.search(r"^(BV[a-zA-Z0-9]+)$", input_str)
    if match:
        return match.group(1)

    return None


def get_video_info(bvid: str) -> dict[str, Any] | None:
    """
    根据 BV 号获取视频完整信息。

    调用 B站 Web API 获取视频的标题、作者、封面以及所有分P信息。

    Args:
        bvid: 视频的 BV 号

    Returns:
        视频信息字典，包含以下字段：
        - bvid: BV 号
        - title: 视频标题
        - author: UP 主名称
        - cover_url: 封面图片 URL
        - pages: 分P列表，每项包含 page/cid/part/duration
        请求失败时返回 None
    """
    url = BILI_VIDEO_INFO_API.format(bvid=bvid)
    # 为当前请求构建专用的 headers（含 Referer）
    headers = dict(HTTP_HEADERS)
    headers["Referer"] = f"{BILI_VIDEO_BASE_URL}{bvid}"

    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        data: dict[str, Any] = response.json()
    except (requests.RequestException, ValueError) as e:
        print(f"[API 错误] 获取视频信息失败: {e}")
        return None

    if data.get("code") != 0:
        print(f"[API 错误] 返回码异常: code={data.get('code')}, "
              f"message={data.get('message', '未知错误')}")
        return None

    video_data: dict[str, Any] = data["data"]

    # print(video_data)

    # 提取分P信息
    pages: list[dict[str, Any]] = []
    for p in video_data.get("pages", []):
        pages.append({
            "page": p.get("page", 1),
            "cid": p.get("cid", 0),
            "part": p.get("part", video_data.get("title", "")),
            "duration": p.get("duration", 0),
        })

    return {
        "bvid": bvid,
        "title": video_data.get("title", ""),
        "author": video_data.get("owner", {}).get("name", ""),
        "face": video_data.get("owner", {}).get("face", ""),
        "view": video_data.get("stat", {}).get("view", ""),
        "favorite": video_data.get("stat", {}).get("favorite", ""),
        "coin": video_data.get("stat", {}).get("coin", ""),
        "share": video_data.get("stat", {}).get("share", ""),
        "like": video_data.get("stat", {}).get("like", ""),
        "cover_url": video_data.get("pic", ""),
        "pages": pages,
    }


def get_audio_url(bvid: str, cid: int) -> str | None:
    """
    获取指定分P的 DASH 音频流下载地址。

    通过 B站播放器 API 请求 DASH 格式的媒体流，
    从中提取音频流的 baseUrl。

    Args:
        bvid: 视频的 BV 号
        cid:  分P的内容 ID

    Returns:
        音频文件的直链下载地址，获取失败返回 None
    """
    url = BILI_PLAYURL_API.format(bvid=bvid, cid=cid)
    headers = dict(HTTP_HEADERS)
    headers["Referer"] = f"{BILI_VIDEO_BASE_URL}{bvid}"

    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        data: dict[str, Any] = response.json()
    except (requests.RequestException, ValueError) as e:
        print(f"[API 错误] 获取音频地址失败: {e}")
        return None

    if data.get("code") != 0:
        print(f"[API 错误] 播放地址返回码异常: code={data.get('code')}")
        return None

    # 从 DASH 音频流中提取第一个可用链接
    try:
        audio_list: list[dict[str, Any]] = data["data"]["dash"]["audio"]
        if audio_list:
            return audio_list[0].get("baseUrl", None)
    except (KeyError, IndexError, TypeError) as e:
        print(f"[API 错误] 解析音频流数据失败: {e}")
        return None

    return None


def get_cover_bytes(cover_url: str) -> bytes | None:
    """
    下载封面图片并返回其二进制数据。

    Args:
        cover_url: 封面图片的 URL

    Returns:
        图片的二进制字节数据，下载失败返回 None
    """
    headers = dict(HTTP_HEADERS)
    headers["Referer"] = "https://www.bilibili.com"

    try:
        response = requests.get(cover_url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.content
    except (requests.RequestException, ValueError) as e:
        print(f"[API 错误] 下载封面失败: {e}")
        return None


def format_duration(seconds: int) -> str:
    """
    将秒数格式化为 ``MM:SS`` 或 ``HH:MM:SS`` 格式的时长字符串。

    Args:
        seconds: 时长秒数

    Returns:
        格式化后的时长字符串
    """
    if seconds <= 0:
        return "--:--"

    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)

    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"
