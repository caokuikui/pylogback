import fcntl
import gzip
import os
import time
from io import StringIO
from logging.handlers import BaseRotatingHandler
from queue import Queue, Full
from threading import Thread, Event
from typing import Dict


class BaseLogbackHandler(BaseRotatingHandler):
    """基础Logback处理器"""

    def __init__(self, filename, rolling_policy, triggering_policy,
                 encoding=None, buffer_size=64 * 1024, metrics_enabled=True):
        super().__init__(filename, 'a', encoding=encoding)
        self.rolling_policy = rolling_policy
        self.triggering_policy = triggering_policy
        self._buffer = StringIO()
        self._buffer_size = 0
        self._max_buffer_size = buffer_size
        self._file_lock = None
        self._metrics = {} if metrics_enabled else None
        self._init_metrics()

    def _init_metrics(self):
        """初始化性能指标"""
        if self._metrics is not None:
            self._metrics.update({
                'written_bytes': 0,
                'written_records': 0,
                'rollover_count': 0,
                'write_time': 0,
                'last_write': 0,
                'errors': 0
            })

    def get_metrics(self) -> Dict:
        """获取性能指标"""
        return self._metrics.copy() if self._metrics else {}

    def shouldRollover(self, record) -> bool:
        return self.triggering_policy.is_triggered(self.baseFilename, record)

    def doRollover(self):
        """执行日志滚动"""
        if self._file_lock:
            fcntl.flock(self._file_lock, fcntl.LOCK_UN)

        if self.stream:
            self.stream.close()
            self.stream = None

        rolled_file = self.rolling_policy.get_rolled_file_name(self.baseFilename)

        if os.path.exists(self.baseFilename):
            try:
                if self.rolling_policy.compress:
                    with open(self.baseFilename, 'rb') as f_in:
                        with gzip.open(f"{rolled_file}.gz", 'wb') as f_out:
                            f_out.writelines(f_in)
                    os.remove(self.baseFilename)
                else:
                    os.rename(self.baseFilename, rolled_file)
            except OSError:
                self._handle_error()

        self.rolling_policy.roll_over(self.baseFilename)

        if not self.delay:
            self.stream = self._open()
            self._file_lock = self.stream.fileno()

        if self._metrics:
            self._metrics['rollover_count'] += 1

    def _handle_error(self):
        """错误处理与恢复"""
        if self._metrics:
            self._metrics['errors'] += 1

        backup_dir = getattr(self, 'backup_dir', '/tmp/pylogback_backup')
        os.makedirs(backup_dir, exist_ok=True)

        backup_file = os.path.join(backup_dir, f'backup_{time.time()}.log')
        try:
            with open(backup_file, 'a') as f:
                f.write(self._buffer.getvalue())
        except Exception:
            pass

    def emit(self, record):
        """发送日志记录"""
        try:
            start_time = time.time()
            msg = self.format(record) + self.terminator
            msg_size = len(msg.encode(self.encoding or 'utf-8'))

            if self._buffer_size + msg_size > self._max_buffer_size:
                self.flush()

            self._buffer.write(msg)
            self._buffer_size += msg_size

            if self._metrics:
                self._metrics['written_bytes'] += msg_size
                self._metrics['written_records'] += 1
                self._metrics['write_time'] += time.time() - start_time
                self._metrics['last_write'] = time.time()

        except Exception:
            self._handle_error()

    def flush(self):
        """刷新缓冲区"""
        if self._buffer_size == 0:
            return

        try:
            if self.shouldRollover(None):
                self.doRollover()

            if self.stream:
                fcntl.flock(self._file_lock, fcntl.LOCK_EX)
                try:
                    self.stream.write(self._buffer.getvalue())
                    self.stream.flush()
                finally:
                    fcntl.flock(self._file_lock, fcntl.LOCK_UN)

            self._buffer = StringIO()
            self._buffer_size = 0

        except Exception:
            self._handle_error()


class AsyncLogbackHandler(BaseLogbackHandler):
    """异步Logback处理器"""

    def __init__(self, *args, queue_size=10000, batch_size=100, **kwargs):
        super().__init__(*args, **kwargs)
        self._queue = Queue(maxsize=queue_size)
        self._batch_size = batch_size
        self._stop_event = Event()
        self._worker = Thread(target=self._async_writer, daemon=True)
        self._worker.start()

    def emit(self, record):
        """异步发送日志记录"""
        try:
            self._queue.put_nowait(record)
        except Full:
            self._handle_error()

    def _async_writer(self):
        """异步写入工作线程"""
        batch = []

        while not self._stop_event.is_set() or not self._queue.empty():
            try:
                record = self._queue.get(timeout=0.1)
                batch.append(record)

                # 批量处理
                if len(batch) >= self._batch_size or self._queue.empty():
                    for rec in batch:
                        super().emit(rec)
                    self.flush()
                    batch = []

            except Exception:
                batch = []
                continue

    def close(self):
        """关闭处理器"""
        self._stop_event.set()
        self._worker.join()
        super().close()
