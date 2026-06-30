"""
数据管理模块

负责音乐记录数据的增删改查操作，以及数据持久化相关的业务逻辑。
"""

import json
import os
from datetime import datetime
from typing import Any


class DataManager:
    """
    数据管理器

    管理音乐记录列表的增删清操作，并提供数据导入导出功能。

    Attributes:
        records: 内部记录列表，每条记录为一个 dict
        _id_counter: 自增 ID 计数器
    """

    def __init__(self) -> None:
        """初始化数据管理器，创建空的记录列表并重置 ID 计数器。"""
        self.records: list[dict[str, Any]] = []
        """存储所有音乐记录的列表，每条记录包含 id/title/artist/album/duration/source"""

        self._id_counter: int = 1
        """自增 ID 计数器，每添加一条记录自动递增"""

    def add_record(
        self,
        title: str,
        artist: str,
        album: str,
        duration: str,
        source: str,
    ) -> dict[str, Any]:
        """
        添加一条新的音乐记录。

        Args:
            title: 歌曲标题
            artist: 艺术家名称
            album: 所属专辑
            duration: 时长（格式如 "3:45"）
            source: 来源平台（如 "B站"、"网易云"）

        Returns:
            新添加的记录字典
        """
        record: dict[str, Any] = {
            "id": self._id_counter,
            "title": title,
            "artist": artist,
            "album": album,
            "duration": duration,
            "source": source,
        }
        self.records.append(record)
        self._id_counter += 1
        return record

    def delete_record(self, record_id: int) -> bool:
        """
        根据 ID 删除一条记录。

        Args:
            record_id: 待删除记录的 ID

        Returns:
            是否成功删除
        """
        for i, rec in enumerate(self.records):
            if rec["id"] == record_id:
                self.records.pop(i)
                return True
        return False

    def clear_all(self) -> None:
        """清空所有记录并重置 ID 计数器。"""
        self.records.clear()
        self._id_counter = 1

    def get_all_records(self) -> list[dict[str, Any]]:
        """
        获取所有记录。

        Returns:
            所有音乐记录的列表（浅拷贝）
        """
        return list(self.records)

    def get_record_by_id(self, record_id: int) -> dict[str, Any] | None:
        """
        根据 ID 查找记录。

        Args:
            record_id: 要查找的记录 ID

        Returns:
            找到的记录 dict，未找到则返回 None
        """
        for rec in self.records:
            if rec["id"] == record_id:
                return rec
        return None

    def export_to_json(self, filepath: str) -> int:
        """
        将当前所有记录导出为 JSON 文件。

        Args:
            filepath: 导出文件路径

        Returns:
            导出的记录条数
        """
        data: dict[str, Any] = {
            "export_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total": len(self.records),
            "records": self.records,
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return len(self.records)

    def import_from_json(self, filepath: str) -> int:
        """
        从 JSON 文件导入记录（追加模式）。

        Args:
            filepath: 待导入的 JSON 文件路径

        Returns:
            新导入的记录条数

        Raises:
            FileNotFoundError: 文件不存在
            json.JSONDecodeError: JSON 格式错误
        """
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"文件不存在: {filepath}")

        with open(filepath, "r", encoding="utf-8") as f:
            data: dict[str, Any] = json.load(f)

        imported_count: int = 0
        for rec in data.get("records", []):
            rec_copy: dict[str, Any] = {
                "id": self._id_counter,
                "title": rec.get("title", ""),
                "artist": rec.get("artist", ""),
                "album": rec.get("album", ""),
                "duration": rec.get("duration", ""),
                "source": rec.get("source", ""),
            }
            self.records.append(rec_copy)
            self._id_counter += 1
            imported_count += 1

        return imported_count

    @property
    def count(self) -> int:
        """
        获取当前记录总数。

        Returns:
            记录数量
        """
        return len(self.records)
