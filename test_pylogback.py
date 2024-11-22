import unittest
import tempfile
import shutil
import os
from pylogback import LogbackConfigurator


class TestPyLogback(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.config = {
            'log_dir': self.test_dir,
            'app_name': 'test_app',
            'max_file_size': 1024,
            'max_history': 2,
            'total_size_cap': 4096,
            'async_logging': False,
            'compression': False,
            'buffer_size': 512,
            'metrics_enabled': True
        }

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_basic_logging(self):
        configurator = LogbackConfigurator(self.config)
        logger = configurator.configure()

        logger.info("Test message")
        log_file = os.path.join(self.test_dir, 'test_app_log.log')

        self.assertTrue(os.path.exists(log_file))
        with open(log_file, 'r') as f:
            content = f.read()
            self.assertIn("Test message", content)


if __name__ == '__main__':
    unittest.main()
