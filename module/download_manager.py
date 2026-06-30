"""
下载管理模块

负责音频文件的下载、FFmpeg 转码封装以及临时文件清理。
所有耗时操作均通过线程执行，避免阻塞主 UI 线程。
"""

import os
import re
import subprocess
import threading
import tempfile
from typing import Callable

import requests

from tools.config import HTTP_HEADERS, BILI_VIDEO_BASE_URL


# 下载任务状态常量
STATUS_PENDING: str = "未下载"
"""等待下载"""
STATUS_DOWNLOADING: str = "下载中..."
"""正在下载中"""
STATUS_DOWNLOADED: str = "已下载 ✓"
"""下载成功"""
STATUS_FAILED: str = "下载失败 ✗"
"""下载失败"""


def _sanitize_filename(filename: str) -> str:
    """
    清理文件名中的非法字符，确保可安全用于文件系统。

    Args:
        filename: 原始文件名

    Returns:
        清理后的安全文件名（仅保留字母、数字、空格、中文、横线和下划线）
    """
    # 保留中文、英文、数字、空格、-、_，其余字符移除
    cleaned = re.sub(r'[^\w\s\-]', '', filename, flags=re.UNICODE)
    # 压缩连续空格
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned if cleaned else "audio"


def _check_ffmpeg_available() -> bool:
    """
    检测系统环境中是否安装了 FFmpeg。

    Returns:
        True 表示 FFmpeg 可用
    """
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return True
    except FileNotFoundError:
        return False


class DownloadManager:
    """
    音频下载管理器。

    负责在后台线程中执行音频下载与转码任务，
    并通过回调函数向 UI 层报告进度与结果。

    Attributes:
        download_dir: 当前设置的下载保存目录
        _ffmpeg_available: 系统是否安装了 FFmpeg
    """

    def __init__(self) -> None:
        """初始化下载管理器，检测 FFmpeg 并设置默认下载目录。"""
        self.download_dir: str = os.path.abspath(".")
        """音频文件保存目录，默认为当前工作目录"""

        self._ffmpeg_available: bool = _check_ffmpeg_available()
        """标记 FFmpeg 是否可用"""

        if not self._ffmpeg_available:
            print("[下载管理器] 未检测到 FFmpeg，将直接保存 m4a 文件（无法嵌入封面）")

    def set_download_dir(self, directory: str) -> None:
        """
        设置音频文件的下载保存目录。

        Args:
            directory: 目标文件夹路径
        """
        self.download_dir = os.path.abspath(directory)
        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir, exist_ok=True)

    def download_audio(
        self,
        bvid: str,
        cid: int,
        title: str,
        author: str,
        cover_url: str,
        audio_url: str,
        status_callback: Callable[[str], None],
        complete_callback: Callable[[bool, str], None],
    ) -> None:
        """
        在后台线程中下载音频并转码为 MP3 文件。

        下载流程：
        1. 下载 m4a 音频流
        2. 下载封面图片（若可用）
        3. 使用 FFmpeg 将 m4a + 封面 封装为 MP3（若 FFmpeg 不可用则保留 m4a）
        4. 清理临时文件

        Args:
            bvid: 视频 BV 号（用于 Referer）
            cid: 分P内容 ID
            title: 歌曲标题（用于输出文件名）
            author: UP 主名称（用于 ID3 标签）
            cover_url: 封面图片 URL
            audio_url: DASH 音频流直链
            status_callback: 状态更新回调，接收状态描述字符串
            complete_callback: 完成回调，接收 (是否成功, 结果描述)
        """
        thread = threading.Thread(
            target=self._download_worker,
            args=(bvid, cid, title, author, cover_url, audio_url,
                  status_callback, complete_callback),
            daemon=True,
        )
        """后台下载工作线程，设为守护线程以避免阻塞进程退出"""
        thread.start()

    def _download_worker(
        self,
        bvid: str,
        cid: int,
        title: str,
        author: str,
        cover_url: str,
        audio_url: str,
        status_callback: Callable[[str], None],
        complete_callback: Callable[[bool, str], None],
    ) -> None:
        """
        下载工作的实际执行体（在后台线程中运行）。

        通过 status_callback 向 UI 报告进度，
        完成后通过 complete_callback 通知结果。

        Args:
            bvid: 视频 BV 号
            cid: 分P内容 ID
            title: 歌曲标题
            author: UP 主名称
            cover_url: 封面图片 URL
            audio_url: DASH 音频流直链
            status_callback: 状态更新回调
            complete_callback: 完成回调
        """
        headers = dict(HTTP_HEADERS)
        headers["Referer"] = f"{BILI_VIDEO_BASE_URL}{bvid}"

        safe_title = _sanitize_filename(title)
        """清理后的安全文件名"""

        output_ext = ".mp3" if self._ffmpeg_available else ".m4a"
        """输出文件扩展名：有 FFmpeg 时输出 mp3，否则保留 m4a"""

        output_path = os.path.join(self.download_dir, f"{safe_title}{output_ext}")
        """输出文件的完整路径"""

        # 处理重名：若文件已存在则追加序号
        counter = 1
        while os.path.exists(output_path):
            output_path = os.path.join(
                self.download_dir,
                f"{safe_title}_{counter}{output_ext}"
            )
            counter += 1

        # 临时文件路径提前声明，确保 finally 块可安全引用
        tmp_audio_path: str | None = None
        """临时音频文件路径"""
        tmp_cover_path: str | None = None
        """临时封面文件路径"""

        try:
            # ---- 1. 下载音频流 ----
            status_callback("下载音频中...")
            audio_resp = requests.get(audio_url, headers=headers, timeout=300)
            audio_resp.raise_for_status()
            audio_data: bytes = audio_resp.content
            """下载到的 m4a 音频二进制数据"""

            # ---- 2. 下载封面图片 ----
            cover_data: bytes | None = None
            """封面图片二进制数据，下载失败时为 None"""
            if cover_url and self._ffmpeg_available:
                status_callback("下载封面中...")
                try:
                    cover_resp = requests.get(cover_url, headers=headers, timeout=30)
                    cover_resp.raise_for_status()
                    cover_data = cover_resp.content
                except requests.RequestException:
                    # 封面下载失败不影响主流程
                    pass

            # ---- 3. 写入临时文件 ----
            status_callback("写入文件中...")

            # 使用 tempfile 创建临时文件
            with tempfile.NamedTemporaryFile(
                suffix=".m4a", delete=False
            ) as tmp_audio:
                tmp_audio.write(audio_data)
                tmp_audio_path = tmp_audio.name

            if cover_data:
                with tempfile.NamedTemporaryFile(
                    suffix=".jpg", delete=False
                ) as tmp_cover:
                    tmp_cover.write(cover_data)
                    tmp_cover_path = tmp_cover.name

            # ---- 4. FFmpeg 转码 ----
            if self._ffmpeg_available and tmp_cover_path:
                status_callback("转码封装中...")
                ffmpeg_cmd = [
                    "ffmpeg",
                    "-i", tmp_audio_path,
                    "-i", tmp_cover_path,
                    "-map", "0:a",
                    "-map", "1:v",
                    "-metadata", f"title={title}",
                    "-metadata", f"artist={author}",
                    "-id3v2_version", "3",
                    "-codec:a", "libmp3lame",
                    "-q:a", "2",
                    "-y",
                    output_path,
                ]
                """FFmpeg 命令行参数列表"""

                result = subprocess.run(
                    ffmpeg_cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                if result.returncode != 0:
                    # FFmpeg 失败时回退到直接保存 m4a
                    m4a_path = output_path.replace(".mp3", ".m4a")
                    with open(tmp_audio_path, "rb") as src:
                        with open(m4a_path, "wb") as dst:
                            dst.write(src.read())
                    output_path = m4a_path
                    complete_callback(
                        True,
                        f"FFmpeg 转码失败，已保存为 m4a 格式: {os.path.basename(output_path)}"
                    )
                else:
                    complete_callback(
                        True,
                        f"下载完成: {os.path.basename(output_path)}"
                    )
            elif self._ffmpeg_available and not tmp_cover_path:
                # 有 FFmpeg 但无封面时仅转码音频
                status_callback("转码中（无封面）...")
                ffmpeg_cmd = [
                    "ffmpeg",
                    "-i", tmp_audio_path,
                    "-metadata", f"title={title}",
                    "-metadata", f"artist={author}",
                    "-codec:a", "libmp3lame",
                    "-q:a", "2",
                    "-y",
                    output_path,
                ]
                subprocess.run(
                    ffmpeg_cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                complete_callback(
                    True,
                    f"下载完成（无封面）: {os.path.basename(output_path)}"
                )
            else:
                # 无 FFmpeg：直接保存 m4a
                with open(output_path, "wb") as f:
                    f.write(audio_data)
                complete_callback(
                    True,
                    f"下载完成（m4a 格式）: {os.path.basename(output_path)}"
                )

        except requests.RequestException as e:
            complete_callback(False, f"网络请求失败: {e}")
        except OSError as e:
            complete_callback(False, f"文件写入失败: {e}")
        except Exception as e:
            complete_callback(False, f"下载异常: {e}")
        finally:
            # ---- 5. 清理临时文件 ----
            try:
                if tmp_audio_path and os.path.exists(tmp_audio_path):
                    os.remove(tmp_audio_path)
                if tmp_cover_path and os.path.exists(tmp_cover_path):
                    os.remove(tmp_cover_path)
            except OSError:
                pass
