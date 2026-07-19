#!/usr/bin/env python3
"""
Testy jednostkowe Fazy 3 (special charging):
- deterministyczny session_id dla need (datetime i string)
- ochrona harmonogramów special w rekoncyliacji monitora
"""

import os
import sys
import types
import pytest
import pytz
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from cloud_tesla_worker import WorkerHealthCheckHandler
from cloud_tesla_monitor import CloudTeslaMonitor
from tesla_controller import ChargeSchedule

WARSAW = pytz.timezone('Europe/Warsaw')


def make_handler() -> WorkerHealthCheckHandler:
    return WorkerHealthCheckHandler.__new__(WorkerHealthCheckHandler)


class TestSessionIdForNeed:
    def test_datetime_target(self):
        h = make_handler()
        need = {'row': 3, 'target_datetime': WARSAW.localize(datetime(2026, 7, 22, 7, 0))}
        assert h._session_id_for_need(need) == 'special_3_20260722_0700'

    def test_string_target_fallback(self):
        # _execute_scheduled_special_charging może przekazać string po nieudanym parsowaniu
        h = make_handler()
        need = {'row': 3, 'target_datetime': '2026-07-22T07:00:00'}
        assert h._session_id_for_need(need) == 'special_3_20260722_0700'

    def test_uszkodzony_target_zwraca_none(self):
        h = make_handler()
        assert h._session_id_for_need({'row': 3, 'target_datetime': 'zepsute'}) is None

    def test_ten_sam_need_ten_sam_id(self):
        # Deduplikacja w daily check opiera się na deterministyczności
        h = make_handler()
        need_dt = {'row': 5, 'target_datetime': WARSAW.localize(datetime(2026, 7, 22, 7, 0))}
        need_str = {'row': 5, 'target_datetime': '2026-07-22 07:00'}
        assert h._session_id_for_need(need_dt) == h._session_id_for_need(need_str)


class TestProtectedSchedulesInReconciliation:
    """Symulacja fragmentu rekoncyliacji: chronione ID nie trafiają do usunięcia."""

    def _reconcile_removals(self, current, desired, protected_ids):
        m = CloudTeslaMonitor.__new__(CloudTeslaMonitor)
        return [
            c for c in current
            if c.get('id') not in protected_ids
            and not any(m._schedule_content_matches(c, s) for s in desired)
        ]

    def test_special_schedule_nie_jest_usuwany(self):
        current = [
            {'id': 1, 'start_time': 60, 'end_time': 300, 'enabled': True},    # stare okno off-peak
            {'id': 99, 'start_time': 120, 'end_time': 400, 'enabled': True},  # okno sesji special
        ]
        desired = [ChargeSchedule(enabled=True, start_time=0, end_time=360,
                                  start_enabled=True, end_enabled=True)]
        to_remove = self._reconcile_removals(current, desired, protected_ids={99})
        assert [c['id'] for c in to_remove] == [1]

    def test_bez_ochrony_special_bylby_usuniety(self):
        current = [{'id': 99, 'start_time': 120, 'end_time': 400, 'enabled': True}]
        desired = []
        to_remove = self._reconcile_removals(current, desired, protected_ids=set())
        assert [c['id'] for c in to_remove] == [99]


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-v']))
