import logging
import uuid


class ContextFilter(logging.Filter):
    """自定义过滤器来添加应用名称和链路 ID."""

    def __init__(self, application_name='MyApp'):
        super().__init__()
        self.application_name = application_name

    def filter(self, record):
        record.application = self.application_name
        record.link_id = str(uuid.uuid4())
        return True
