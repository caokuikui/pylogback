import os
import time
from abc import ABC, abstractmethod
from datetime import datetime
from threading import Lock
from typing import Dict, List, Tuple
import re


class RollingPolicy(ABC):
    """滚动策略基类"""

    def __init__(self, pattern: str, max_history: int = 15,
                 total_size_cap: int = 1024 * 1024 * 1024,
                 compress: bool = False):
        self.pattern = pattern
        self.max_history = max_history
        self.total_size_cap = total_size_cap
        self.compress = compress
        self._cache_lock = Lock()
        self._file_cache: Dict[str, List[Tuple[str, os.stat_result]]] = {}
        self._last_cleanup = 0

    @abstractmethod
    def get_active_file_name(self) -> str:
        pass

    @abstractmethod
    def get_rolled_file_name(self, active_file: str) -> str:
        pass

    @abstractmethod
    def roll_over(self, active_file: str):
        pass

    def _clean_cache(self, force: bool = False):
        """清理文件缓存"""
        current_time = time.time()
        with self._cache_lock:
            if force or current_time - self._last_cleanup >= 3600:
                self._file_cache.clear()
                self._last_cleanup = current_time


class TimeBasedRollingPolicy(RollingPolicy):
    """基于时间的滚动策略"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._current_date = datetime.now().strftime('%Y-%m-%d')
        self._current_index = 0
        self._pattern_regex = self._compile_pattern(self.pattern)

    def _compile_pattern(self, pattern: str) -> re.Pattern:
        """编译文件名模式"""
        pattern = pattern.replace('%d', r'\d{2}')
        pattern = pattern.replace('%m', r'\d{2}')
        pattern = pattern.replace('%Y', r'\d{4}')
        return re.compile(pattern)

    def get_active_file_name(self) -> str:
        return datetime.now().strftime(self.pattern)

    def get_rolled_file_name(self, active_file: str) -> str:
        with self._cache_lock:
            current_date = datetime.now().strftime('%Y-%m-%d')
            if current_date != self._current_date:
                self._current_date = current_date
                self._current_index = 0
            self._current_index += 1

            if self.compress:
                return f"{active_file}.{self._current_date}.{self._current_index}.gz"
            return f"{active_file}.{self._current_date}.{self._current_index}"

    def roll_over(self, active_file: str):
        self._clean_history_files(active_file)

    def _clean_history_files(self, active_file: str):
        """清理历史文件"""
        try:
            dir_name = os.path.dirname(active_file)
            current_time = time.time()

            with self._cache_lock:
                if dir_name in self._file_cache and \
                        current_time - self._last_cleanup < 3600:
                    files_info = self._file_cache[dir_name]
                else:
                    files_info = []
                    with os.scandir(dir_name) as entries:
                        for entry in entries:
                            if self._pattern_regex.match(entry.name):
                                files_info.append((entry.path, entry.stat()))

                    self._file_cache[dir_name] = files_info
                    self._last_cleanup = current_time

            files_to_delete = []
            total_size = 0

            for file_path, stat in sorted(files_info,
                                          key=lambda x: x[1].st_mtime,
                                          reverse=True):
                file_age_days = (current_time - stat.st_mtime) / (24 * 3600)
                if file_age_days > self.max_history or \
                        total_size + stat.st_size > self.total_size_cap:
                    files_to_delete.append(file_path)
                else:
                    total_size += stat.st_size

            if files_to_delete:
                for file_path in files_to_delete:
                    try:
                        os.remove(file_path)
                    except OSError:
                        pass
                self._clean_cache(force=True)

        except Exception:
            pass


class SizeBasedTriggeringPolicy:
    """基于大小的触发策略"""

    def __init__(self, max_size: int, check_interval: float = 1.0):
        self.max_size = max_size
        self.check_interval = check_interval
        self._last_size = 0
        self._last_check = 0
        self._lock = Lock()

    def is_triggered(self, current_file: str, record) -> bool:
        current_time = time.time()

        with self._lock:
            if current_time - self._last_check < self.check_interval:
                self._last_size += len(record.getMessage()) + 100
                return self._last_size >= self.max_size

            try:
                size = os.path.getsize(current_file)
                self._last_size = size
                self._last_check = current_time
                return size >= self.max_size
            except OSError:
                return False
