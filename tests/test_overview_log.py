"""Журнал синку дашборда (4d-4c, Д8): один для всіх просторів — `<DEAI_HOME>/logs/dashboard-sync.log`."""
import inspect
import os
import stat
import sys
import tempfile
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
for _p in ('app', 'bin'):
    sys.path.insert(0, os.path.join(os.path.dirname(_HERE), _p))
import serve  # noqa: E402


class OverviewLog(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory(prefix='ovlog-')
        self.addCleanup(d.cleanup)
        self.tmp = os.path.realpath(d.name)
        p = mock.patch.dict(os.environ, {'HOME': self.tmp, 'DEAI_HOME': os.path.join(self.tmp, '.deai')})
        p.start()
        self.addCleanup(p.stop)

    def test_the_log_is_under_the_deai_home_with_private_modes(self):
        path = serve._overview_log_path()
        self.assertEqual(path, os.path.join(self.tmp, '.deai', 'logs', 'dashboard-sync.log'))
        self.assertEqual(stat.S_IMODE(os.stat(os.path.dirname(path)).st_mode), 0o700)

    def test_there_is_no_legacy_log_and_no_legacy_parameter(self):
        self.assertFalse(hasattr(serve, 'OVERVIEW_LOG'))
        self.assertEqual(list(inspect.signature(serve._overview_spawn).parameters), ['target', 'note'])
        self.assertEqual(list(inspect.signature(serve._overview_launch).parameters), ['key', 'target'])
        self.assertEqual(list(inspect.signature(serve._overview_log_path).parameters), [])

    def test_spawn_writes_to_that_log_with_0600(self):
        with mock.patch.object(serve.subprocess, 'Popen') as popen:
            serve._overview_spawn(['--space', 'x'], note='n')
        path = serve._overview_log_path()
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        self.assertEqual(popen.call_args[0][0][-2:], ['--space', 'x'])
        with open(path, encoding='utf-8') as f:
            self.assertEqual(f.read(), 'n\n')

    def test_nothing_is_written_to_the_old_pipeline_feedback_log(self):
        # Старий файл ЛІГИ не розгортається й не відкривається: усі шляхи в `<DEAI_HOME>`, а `HOME` тесту порожній.
        with mock.patch.object(serve.subprocess, 'Popen'):
            serve._overview_spawn(['--legacy'])
        self.assertFalse(os.path.exists(os.path.join(self.tmp, '.claude')))


if __name__ == '__main__':
    unittest.main()
