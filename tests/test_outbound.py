"""Вихідні дії вирішує запис ролі `vcs`, а не прапорець простору (етап 4d-4c): предикат `vcs_outbound` і його споживачі."""
import contextlib
import json
import os
import subprocess
import sys
import threading
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
for _p in ('app', 'bin'):
    sys.path.insert(0, os.path.join(os.path.dirname(_HERE), _p))
import liga_fixture as lf  # noqa: E402
import spaces_guard  # noqa: E402
import deai_modules  # noqa: E402
import spaces  # noqa: E402
import serve  # noqa: E402

_REAL = None


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


def _liga(fx):
    return {'id': 'legacy', 'path': fx.space_dir, 'legacy': True}


class VcsOutbound(unittest.TestCase):
    def test_a_migrated_liga_is_outbound(self):
        fx = lf.LigaFixture(self).env().build()
        self.assertIs(deai_modules.vcs_outbound(_liga(fx)), True)

    def test_no_record_is_closed(self):
        fx = lf.LigaFixture(self).env().build(roles=())
        self.assertIs(deai_modules.vcs_outbound(_liga(fx)), False)

    def test_a_disabled_record_is_closed(self):
        fx = lf.LigaFixture(self).env().build(overrides={'vcs': {'enabled': False}})
        self.assertIs(deai_modules.vcs_outbound(_liga(fx)), False)

    def test_git_sync_without_the_liga_scheme_is_closed(self):
        fx = lf.LigaFixture(self).env().build(overrides={'vcs': {'settings': {'compat': ''}}})
        self.assertIs(deai_modules.vcs_outbound(_liga(fx)), False)

    def test_unreadable_space_json_is_closed(self):
        fx = lf.LigaFixture(self).env().build()
        with open(os.path.join(fx.space_dir, 'space.json'), 'w') as f:
            f.write('{not json')
        deai_modules.reset_caches()
        self.assertIs(deai_modules.vcs_outbound(_liga(fx)), False)

    def test_nobody_layer_off_and_the_implicit_space_are_closed(self):
        fx = lf.LigaFixture(self).env().build()
        for sp in (None, {}, dict(spaces.IMPLICIT)):
            self.assertIs(deai_modules.vcs_outbound(sp), False, sp)
        with mock.patch.object(spaces, 'layer_on', return_value=False):
            self.assertIs(deai_modules.vcs_outbound(_liga(fx)), False)

    def test_it_is_the_same_fact_as_the_client_reads(self):
        """Той самий факт, що `serve.vcs_legacy_texts` (і JS `isLegacyVcs`): рішення не розходяться."""
        for kw in ({}, {'roles': ()}, {'overrides': {'vcs': {'settings': {'compat': ''}}}}):
            fx = lf.LigaFixture(self).env().build(**kw)
            sp = _liga(fx)
            self.assertIs(deai_modules.vcs_outbound(sp),
                          serve.vcs_legacy_texts(deai_modules.provider('vcs', sp), sp), kw)

    def test_the_second_call_does_not_walk_the_catalog_again(self):
        fx = lf.LigaFixture(self).env().build()
        sp = _liga(fx)
        self.assertIs(deai_modules.vcs_outbound(sp), True)
        with mock.patch.object(deai_modules, 'catalog', side_effect=AssertionError('каталог')):
            self.assertIs(deai_modules.vcs_outbound(sp), True)
