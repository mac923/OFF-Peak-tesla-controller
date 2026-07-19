#!/usr/bin/env python3
"""
Testy jednostkowe Fazy 2:
- detekcja nakładania okien z obecną chwilą (w tym okna przez północ)
- konwerter: tryb one_time (sloty jutrzejsze), odrzucanie minionych slotów,
  okno-strażnik 23:58-23:59 przy pustym planie
- fallback OFF PEAK API: format ISO + okno nocne
- klient: charge_start / charge_stop z idempotentnymi reasons
"""

import os
import sys
import types
import pytest
import pytz
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from tesla_fleet_api_client import TeslaFleetAPIClient
from cloud_tesla_monitor import CloudTeslaMonitor
from tesla_controller import ChargeSchedule

WARSAW = pytz.timezone('Europe/Warsaw')
VIN = "TESTVIN1234567890"


def make_monitor(now: datetime = None) -> CloudTeslaMonitor:
    m = CloudTeslaMonitor.__new__(CloudTeslaMonitor)
    m.last_off_peak_schedules = {}
    m.schedule_apply_attempts = {}
    m.firestore_client = None
    m.project_id = None
    m.tesla_controller = types.SimpleNamespace(
        current_vehicle=None,
        minutes_to_time=lambda mins: f"{mins // 60:02d}:{mins % 60:02d}",
    )
    if now is not None:
        m._get_warsaw_time = lambda: now
    return m


def make_client() -> TeslaFleetAPIClient:
    client = TeslaFleetAPIClient.__new__(TeslaFleetAPIClient)
    client.proxy_url = "https://localhost:4443"
    return client


def slot(start: datetime, end: datetime) -> dict:
    return {'start_time': start.isoformat(), 'end_time': end.isoformat(), 'charge_amount': 10}


def api_response(slots: list) -> dict:
    return {'success': True, 'data': {
        'summary': {'scheduledSlots': len(slots), 'totalEnergy': 10 * len(slots)},
        'chargingSchedule': slots,
    }}


# ========== 1. Nakładanie z "teraz" ==========

class TestCurrentTimeOverlap:
    NOW = WARSAW.localize(datetime(2026, 7, 18, 13, 30))

    def _sched(self, start_min, end_min, enabled=True):
        return ChargeSchedule(enabled=enabled, start_time=start_min, end_time=end_min,
                              start_enabled=True, end_enabled=True)

    def test_okno_pokrywa_teraz(self):
        m = make_monitor(self.NOW)
        assert m._current_time_overlaps_schedules([self._sched(13 * 60, 15 * 60)]) is True

    def test_okno_nie_pokrywa(self):
        m = make_monitor(self.NOW)
        assert m._current_time_overlaps_schedules([self._sched(23 * 60, 6 * 60)]) is False

    def test_okno_przez_polnoc_pokrywa_noca(self):
        m = make_monitor(WARSAW.localize(datetime(2026, 7, 19, 1, 30)))
        assert m._current_time_overlaps_schedules([self._sched(23 * 60, 6 * 60)]) is True

    def test_okno_wylaczone_ignorowane(self):
        m = make_monitor(self.NOW)
        assert m._current_time_overlaps_schedules([self._sched(13 * 60, 15 * 60, enabled=False)]) is False


# ========== 2. Konwerter: one_time / minione / strażnik ==========

class TestConverterOneTime:
    NOW = WARSAW.localize(datetime(2026, 7, 18, 21, 0))  # wieczór — wpięcie po pracy

    def _convert(self, slots, one_time_mode: bool):
        os.environ['USE_ONE_TIME_SCHEDULES'] = 'true' if one_time_mode else 'false'
        try:
            m = make_monitor(self.NOW)
            return m._convert_off_peak_to_tesla_schedules(api_response(slots), VIN)
        finally:
            os.environ.pop('USE_ONE_TIME_SCHEDULES', None)

    def test_one_time_slot_jutrzejszy_trafia_do_planu(self):
        # Kluczowy scenariusz audytu: wpięcie o 21:00, tanie sloty jutro 00:00-06:00
        tomorrow = self.NOW + timedelta(days=1)
        slots = [slot(tomorrow.replace(hour=0, minute=0), tomorrow.replace(hour=6, minute=0))]
        result = self._convert(slots, one_time_mode=True)
        assert len(result) == 1
        assert result[0].one_time is True
        assert result[0].start_time == 0
        assert result[0].end_time == 6 * 60

    def test_legacy_slot_jutrzejszy_odfiltrowany_strażnik_w_zamian(self):
        tomorrow = self.NOW + timedelta(days=1)
        slots = [slot(tomorrow.replace(hour=0, minute=0), tomorrow.replace(hour=6, minute=0))]
        result = self._convert(slots, one_time_mode=False)
        # Legacy: slot odfiltrowany, zostaje okno-strażnik
        assert len(result) == 1
        assert result[0].start_time == 23 * 60 + 58
        assert result[0].end_time == 23 * 60 + 59

    def test_miniony_slot_odrzucany_w_obu_trybach(self):
        past = [slot(self.NOW.replace(hour=1, minute=0), self.NOW.replace(hour=5, minute=0))]
        for mode in (True, False):
            result = self._convert(past, one_time_mode=mode)
            assert all(s.start_time == 23 * 60 + 58 for s in result), \
                f"Miniony slot nie może trafić do planu (tryb one_time={mode})"

    def test_pusty_plan_daje_straznika_w_zakresie_0_1439(self):
        result = self._convert([], one_time_mode=True)
        assert len(result) == 1
        guard = result[0]
        assert 0 <= guard.start_time <= 1439
        assert 0 <= guard.end_time <= 1439
        assert guard.one_time is False

    def test_trwajacy_slot_zachowany(self):
        # Slot 20:00-23:00, teraz 21:00 — okno trwa, musi zostać w planie
        slots = [slot(self.NOW.replace(hour=20, minute=0), self.NOW.replace(hour=23, minute=0))]
        result = self._convert(slots, one_time_mode=True)
        assert len(result) == 1
        assert result[0].start_time == 20 * 60


# ========== 3. Fallback OFF PEAK API ==========

class TestFallbackResponse:
    def _get_fallback(self, now):
        m = make_monitor(now)
        # project_id=None wymusza fallback na starcie _call_off_peak_charge_api
        return m._call_off_peak_charge_api(50, VIN)

    def test_fallback_iso_parsowalny_przez_konwerter(self):
        now = WARSAW.localize(datetime(2026, 7, 18, 14, 0))
        resp = self._get_fallback(now)
        assert resp['success'] is True
        s = resp['data']['chargingSchedule'][0]
        # Musi się parsować dokładnie tak, jak robi to konwerter
        start = datetime.fromisoformat(s['start_time'].replace('Z', '+00:00'))
        end = datetime.fromisoformat(s['end_time'].replace('Z', '+00:00'))
        assert start < end

    def test_fallback_w_dzien_planuje_noc(self):
        now = WARSAW.localize(datetime(2026, 7, 18, 14, 0))
        resp = self._get_fallback(now)
        s = resp['data']['chargingSchedule'][0]
        start = datetime.fromisoformat(s['start_time'])
        end = datetime.fromisoformat(s['end_time'])
        assert start.hour == 23
        assert end.hour == 6
        assert end.date() == (now + timedelta(days=1)).date()

    def test_fallback_w_nocy_laduje_od_teraz(self):
        now = WARSAW.localize(datetime(2026, 7, 19, 1, 30))
        resp = self._get_fallback(now)
        s = resp['data']['chargingSchedule'][0]
        start = datetime.fromisoformat(s['start_time'])
        end = datetime.fromisoformat(s['end_time'])
        assert start.hour == 1 and start.minute == 30
        assert end.hour == 6 and end.date() == now.date()


# ========== 4. charge_start / charge_stop ==========

class TestChargeStartStop:
    def _patch(self, client, response):
        client._make_signed_request = lambda *a, **kw: response

    def test_charge_start_sukces(self):
        c = make_client()
        self._patch(c, {'response': {'result': True, 'reason': ''}})
        assert c.charge_start('VIN', use_proxy=True) is True

    def test_charge_start_juz_laduje_to_sukces(self):
        c = make_client()
        self._patch(c, {'response': {'result': False, 'reason': 'is_charging'}})
        assert c.charge_start('VIN', use_proxy=True) is True

    def test_charge_stop_nie_laduje_to_sukces(self):
        c = make_client()
        self._patch(c, {'response': {'result': False, 'reason': 'not_charging'}})
        assert c.charge_stop('VIN', use_proxy=True) is True

    def test_charge_stop_inna_porazka(self):
        c = make_client()
        self._patch(c, {'response': {'result': False, 'reason': 'vehicle_unavailable'}})
        assert c.charge_stop('VIN', use_proxy=True) is False


# ========== 5. Wyrównanie ładowania (shadow mode) ==========

class TestAlignCharging:
    NOW = WARSAW.localize(datetime(2026, 7, 18, 13, 30))

    def _monitor_with_fleet(self, calls):
        m = make_monitor(self.NOW)
        fleet = types.SimpleNamespace(
            proxy_url='https://localhost:4443',
            charge_start=lambda vin, use_proxy=None: calls.append('start') or True,
            charge_stop=lambda vin, use_proxy=None: calls.append('stop') or True,
        )
        m.tesla_controller = types.SimpleNamespace(fleet_api=fleet,
                                                   minutes_to_time=lambda x: str(x))
        m._log_event = lambda **kw: None
        m._has_active_special_session = lambda vin: False
        return m

    def _window_outside_now(self):
        return [ChargeSchedule(enabled=True, start_time=23 * 60, end_time=6 * 60,
                               start_enabled=True, end_enabled=True)]

    def _window_covering_now(self):
        return [ChargeSchedule(enabled=True, start_time=13 * 60, end_time=15 * 60,
                               start_enabled=True, end_enabled=True)]

    def test_shadow_mode_nie_wysyla_stop(self):
        os.environ.pop('CHARGE_STOP_ENFORCE', None)
        calls = []
        m = self._monitor_with_fleet(calls)
        m._align_charging_with_plan(self._window_outside_now(), VIN,
                                    {'charging_state': 'Charging', 'battery_level': 60})
        assert calls == []  # shadow: tylko log

    def test_enforce_wysyla_stop(self):
        os.environ['CHARGE_STOP_ENFORCE'] = 'true'
        try:
            calls = []
            m = self._monitor_with_fleet(calls)
            m._align_charging_with_plan(self._window_outside_now(), VIN,
                                        {'charging_state': 'Charging', 'battery_level': 60})
            assert calls == ['stop']
        finally:
            os.environ.pop('CHARGE_STOP_ENFORCE', None)

    def test_niska_bateria_blokuje_stop(self):
        os.environ['CHARGE_STOP_ENFORCE'] = 'true'
        try:
            calls = []
            m = self._monitor_with_fleet(calls)
            m._align_charging_with_plan(self._window_outside_now(), VIN,
                                        {'charging_state': 'Charging', 'battery_level': 20})
            assert calls == []
        finally:
            os.environ.pop('CHARGE_STOP_ENFORCE', None)

    def test_sesja_special_blokuje_stop(self):
        os.environ['CHARGE_STOP_ENFORCE'] = 'true'
        try:
            calls = []
            m = self._monitor_with_fleet(calls)
            m._has_active_special_session = lambda vin: True
            m._align_charging_with_plan(self._window_outside_now(), VIN,
                                        {'charging_state': 'Charging', 'battery_level': 60})
            assert calls == []
        finally:
            os.environ.pop('CHARGE_STOP_ENFORCE', None)

    def test_okno_pokrywa_teraz_wysyla_start(self):
        calls = []
        m = self._monitor_with_fleet(calls)
        m._align_charging_with_plan(self._window_covering_now(), VIN,
                                    {'charging_state': 'Stopped', 'battery_level': 60})
        assert calls == ['start']

    def test_complete_nie_startuje(self):
        calls = []
        m = self._monitor_with_fleet(calls)
        m._align_charging_with_plan(self._window_covering_now(), VIN,
                                    {'charging_state': 'Complete', 'battery_level': 80})
        assert calls == []


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-v']))
