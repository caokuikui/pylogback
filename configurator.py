import logging.config
import os
from typing import Dict, Any
from .handlers import AsyncLogbackHandler, BaseLogbackHandler
from .policies import TimeBasedRollingPolicy, SizeBasedTriggeringPolicy
from .filters import ContextFilter

class LogbackConfigurator:
    """Logback配置器"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._setup_defaults()
        
    def _setup_defaults(self):
        """设置默认配置"""
        self.config.setdefault('log_dir', './logs')
        self.config.setdefault('app_name', 'app')
        self.config.setdefault('max_file_size', 100*1024*1024)
        self.config.setdefault('max_history', 15)
        self.config.setdefault('total_size_cap', 1024*1024*1024)
        self.config.setdefault('async_logging', False)
        self.config.setdefault('compression', False)
        self.config.setdefault('buffer_size', 64*1024)
        self.config.setdefault('metrics_enabled', True)
        
    def configure(self):
        """配置日志系统"""
        os.makedirs(self.config['log_dir'], exist_ok=True)
        
        # 创建基本配置
        log_config = {
            'version': 1,
            'disable_existing_loggers': False,
            'formatters': {
                'detailed': {
                    'format': '%(asctime)s %(levelname)s [%(pathname)s] '
                             '[%(module)s.%(funcName)s:%(lineno)s] '
                             '[%(threadName)s]: %(message)s'
                }
            },
            'handlers': {
                'console': {
                    'class': 'logging.StreamHandler',
                    'level': 'DEBUG',
                    'formatter': 'detailed'
                }
            },
            'root': {
                'level': 'DEBUG',
                'handlers': ['console']
            }
        }
        
        # 创建文件处理器
        handlers = self._create_handlers()
        log_config['handlers'].update(handlers)
        log_config['root']['handlers'].extend(handlers.keys())
        
        # 应用配置
        logging.config.dictConfig(log_config)
        
        # 添加上下文过滤器
        logger = logging.getLogger()
        logger.addFilter(ContextFilter(self.config['app_name']))
        
        return logger
        
    def _create_handlers(self) -> Dict[str, Dict]:
        """创建日志处理器配置"""
        handlers = {}
        
        # 常规日志处理器
        log_file = os.path.join(self.config['log_dir'], 
                               f"{self.config['app_name']}_log.log")
        
        rolling_policy = TimeBasedRollingPolicy(
            pattern=log_file,
            max_history=self.config['max_history'],
            total_size_cap=self.config['total_size_cap'],
            compress=self.config['compression']
        )
        
        triggering_policy = SizeBasedTriggeringPolicy(
            max_size=self.config['max_file_size']
        )
        
        handler_class = AsyncLogbackHandler if self.config['async_logging'] \
                       else BaseLogbackHandler
                       
        handlers['file'] = {
            'class': handler_class.__module__ + '.' + handler_class.__name__,
            'level': 'INFO',
            'formatter': 'detailed',
            'filename': log_file,
            'rolling_policy': rolling_policy,
            'triggering_policy': triggering_policy,
            'encoding': 'utf8',
            'buffer_size': self.config['buffer_size'],
            'metrics_enabled': self.config['metrics_enabled']
        }
        
        # 错误日志处理器
        error_log_file = os.path.join(self.config['log_dir'],
                                     f"{self.config['app_name']}_error.log")
        
        handlers['error_file'] = {
            'class': handler_class.__module__ + '.' + handler_class.__name__,
            'level': 'ERROR',
            'formatter': 'detailed',
            'filename': error_log_file,
            'rolling_policy': TimeBasedRollingPolicy(
                pattern=error_log_file,
                max_history=self.config['max_history'],
                total_size_cap=self.config['total_size_cap'],
                compress=self.config['compression']
            ),
            'triggering_policy': SizeBasedTriggeringPolicy(
                max_size=self.config['max_file_size']
            ),
            'encoding': 'utf8',
            'buffer_size': self.config['buffer_size'],
            'metrics_enabled': self.config['metrics_enabled']
        }
        
        return handlers 