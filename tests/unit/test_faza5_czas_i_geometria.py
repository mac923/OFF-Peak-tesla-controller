#!/usr/bin/env python3
"""
Testy jednostkowe Fazy 5:
- nakładanie okien przez północ (segmentowo)
- peak hours następnego dnia dla slotów przez północ
"""

import os
import sys
import pytest
import pytz
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from cloud_tesla_monitor import CloudTeslaMonitor
from cloud_tesla_worker import WorkerHealthCheckHandler
from tesla_controller import ChargeSchedule

WARSAW = pytz.timezone('Europe/Warsaw')


def sched(start_min, end_min):
    return ChargeSchedule(enabled=True, start_time=start_min, end_time=end_min,
                          start_enabled=True, end_enabled=True)


class TestSchedulesOverlapMidnight:
    def _overlap(self, s1, s2):
        m = CloudTeslaMonitor.__new__(CloudTeslaMonitor)
        return m._schedules_overlap(s1, s2)

    def test_okno_przez_polnoc_nakladane_z_porannym(self):
        # 23:00-01:00 vs 00:30-02:00 — wspólny odcinek 00:30-01:00
        # (stara formuła po normalizacji end<start tego NIE wykrywała)
        assert self._overlap(sched(23 * 60, 1 * 60), sched(30, 2 * 60)) is True

    def test_okno_przez_polnoc_nakladane_z_wieczornym(self):
        # 23:00-01:00 vs 22:00-23:30 — wspólny odcinek 23:00-23:30
        assert self._overlap(sched(23 * 60, 1 * 60), sched(22 * 60, 23 * 60 + 30)) is True

    def test_dwa_okna_przez_polnoc(self):
        # 23:00-02:00 vs 01:00-03:00 (drugie normalne) — wspólny 01:00-02:00
        assert self._overlap(sched(23 * 60, 2 * 60), sched(1 * 60, 3 * 60)) is True

    def test_rozlaczne_okna(self):
        assert self._overlap(sched(23 * 60, 1 * 60), sched(2 * 60, 5 * 60)) is False

    def test_zwykle_nakladanie_dziala_jak_wczesniej(self):
        assert self._overlap(sched(60, 300), sched(200, 400)) is True
        assert self._overlap(sched(60, 200), sched(200, 400)) is False

    def test_stary_format_end_powyzej_1440(self):
        # Konwerter potrafił dawać end_time > 1440 (przejście przez północ)
        assert self._overlap(sched(23 * 60, 25 * 60), sched(30, 2 * 60)) is True


class TestPeakHoursNextDay:
    def _handler(self):
        return WorkerHealthCheckHandler.__new__(WorkerHealthCheckHandler)

    def test_slot_nocny_zahacza_o_poranny_szczyt_jutro(self):
        # 23:00 → 07:00: godzina 06:00-07:00 wypada w szczycie 6-10 NASTĘPNEGO dnia
        h = self._handler()
        start = WARSAW.localize(datetime(2026, 7, 18, 23, 0))
        end = WARSAW.localize(datetime(2026, 7, 19, 7, 0))
        assert h._slot_avoids_peak_hours(start, end) is False
        assert h._calculate_peak_collision(start, end) == pytest.approx(1.0)

    def test_slot_nocny_konczacy_przed_szczytem_ok(self):
        h = self._handler()
        start = WARSAW.localize(datetime(2026, 7, 18, 23, 0))
        end = WARSAW.localize(datetime(2026, 7, 19, 5, 30))
        assert h._slot_avoids_peak_hours(start, end) is True
        assert h._calculate_peak_collision(start, end) == pytest.approx(0.0)

    def test_slot_dzienny_w_szczycie_wykrywany(self):
        h = self._handler()
        start = WARSAW.localize(datetime(2026, 7, 18, 8, 0))
        end = WARSAW.localize(datetime(2026, 7, 18, 11, 0))
        assert h._slot_avoids_peak_hours(start, end) is False
        assert h._calculate_peak_collision(start, end) == pytest.approx(2.0)


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-v']))
