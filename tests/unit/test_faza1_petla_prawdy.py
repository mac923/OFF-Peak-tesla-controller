#!/usr/bin/env python3
"""
Testy jednostkowe Fazy 1 — "pętla zwrotna prawdy":
- odczyt pola result z odpowiedzi komend Tesla (HTTP 200 != sukces)
- rozróżnienie błędu odczytu harmonogramów (None) od pustej listy ([])
- hash harmonogramu zatwierdzany dopiero po sukcesie
- retry-budget (3 próby + cooldown) dla aplikacji harmonogramu
- rekoncyliacja po treści (idempotencja retry)
"""

import os
import sys
import time
import types
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from tesla_fleet_api_client import TeslaFleetAPIClient
from cloud_tesla_monitor import CloudTeslaMonitor
from tesla_controller import ChargeSchedule


# ========== Helpery ==========

def make_client() -> TeslaFleetAPIClient:
    """Klient bez konstruktora (bez tokenów/sieci) — testujemy czyste metody."""
    client = TeslaFleetAPIClient.__new__(TeslaFleetAPIClient)
    client.proxy_url = "https://localhost:4443"
    return client


def make_monitor() -> CloudTeslaMonitor:
    """Monitor bez konstruktora (bez GCP) — tylko pola używane w testach."""
    m = CloudTeslaMonitor.__new__(CloudTeslaMonitor)
    m.last_off_peak_schedules = {}
    m.schedule_apply_attempts = {}
    m.firestore_client = None
    return m


VIN = "TESTVIN1234567890"


# ========== 1. _command_result ==========

class TestCommandResult:
    def test_result_true_to_sukces(self):
        client = make_client()
        ok, reason = client._command_result({'response': {'result': True, 'reason': ''}}, 'cmd')
        assert ok is True

    def test_result_false_to_porazka_z_reason(self):
        client = make_client()
        ok, reason = client._command_result(
            {'response': {'result': False, 'reason': 'could_not_wake_buses'}}, 'cmd')
        assert ok is False
        assert reason == 'could_not_wake_buses'

    def test_brak_pola_result_nie_blokuje(self):
        # Nieznany kształt odpowiedzi (np. wake_up) nie może być traktowany jak porażka
        client = make_client()
        ok, _ = client._command_result({'response': {'id': 123, 'state': 'online'}}, 'cmd')
        assert ok is True

    def test_odpowiedz_nie_dict_nie_blokuje(self):
        client = make_client()
        ok, _ = client._command_result("weird", 'cmd')
        assert ok is True


class TestCommandWrappers:
    def _patch_request(self, client, response):
        client._make_signed_request = lambda *a, **kw: response

    def test_set_charge_limit_result_false_zwraca_false(self):
        client = make_client()
        self._patch_request(client, {'response': {'result': False, 'reason': 'not_charging'}})
        assert client.set_charge_limit('VIN', 80, use_proxy=True) is False

    def test_add_charge_schedule_result_false_zwraca_false(self):
        client = make_client()
        self._patch_request(client, {'response': {'result': False, 'reason': 'invalid_schedule'}})
        assert client.add_charge_schedule('VIN', 'All', True, 52.0, 20.0,
                                          start_time=120, end_time=300) is False

    def test_remove_charge_schedule_not_found_to_sukces(self):
        # Harmonogram już nie istnieje (np. wykonany one_time) = cel osiągnięty
        client = make_client()
        self._patch_request(client, {'response': {'result': False, 'reason': 'schedule not found'}})
        assert client.remove_charge_schedule('VIN', 42, use_proxy=True) is True

    def test_remove_charge_schedule_inna_porazka_zwraca_false(self):
        client = make_client()
        self._patch_request(client, {'response': {'result': False, 'reason': 'vehicle_unavailable'}})
        assert client.remove_charge_schedule('VIN', 42, use_proxy=True) is False


# ========== 2. Błąd odczytu != pusta lista ==========

class TestGetChargeSchedulesNone:
    def test_blad_odczytu_vehicle_data_zwraca_none(self):
        client = make_client()
        client.get_vehicle_data = lambda *a, **kw: {}
        assert client.get_charge_schedules('VIN') is None

    def test_pusta_odpowiedz_bez_harmonogramow_zwraca_pusta_liste(self):
        client = make_client()
        client.get_vehicle_data = lambda *a, **kw: {'charge_state': {}, 'vehicle_state': {}}
        assert client.get_charge_schedules('VIN') == []

    def test_preconditioning_nie_jest_zwracany_jako_charge_schedules(self):
        client = make_client()
        client.get_vehicle_data = lambda *a, **kw: {
            'preconditioning_schedule_data': {
                'preconditioning_schedules': [{'id': 7, 'start_time': 420}]
            }
        }
        assert client.get_charge_schedules('VIN') == []

    def test_remove_all_przy_bledzie_odczytu_zwraca_false(self):
        client = make_client()
        client.get_charge_schedules = lambda vid: None
        assert client.remove_all_charge_schedules('VIN', use_proxy=True) is False

    def test_remove_all_przy_pustej_liscie_zwraca_true(self):
        client = make_client()
        client.get_charge_schedules = lambda vid: []
        assert client.remove_all_charge_schedules('VIN', use_proxy=True) is True


# ========== 3. Hash po sukcesie ==========

class TestHashCommit:
    PLAN_A = {'success': True, 'data': {'summary': {'scheduledSlots': 2}}}

    def test_is_schedule_different_nie_zapisuje_hasha(self):
        m = make_monitor()
        assert m._is_schedule_different(VIN, self.PLAN_A) is True
        # Bez commita ten sam plan nadal wykrywany jako RÓŻNY (retry możliwy)
        assert m._is_schedule_different(VIN, self.PLAN_A) is True
        assert VIN not in m.last_off_peak_schedules

    def test_commit_hash_powoduje_identyczny(self):
        m = make_monitor()
        assert m._is_schedule_different(VIN, self.PLAN_A) is True
        m._commit_schedule_hash(VIN, self.PLAN_A)
        assert m._is_schedule_different(VIN, self.PLAN_A) is False


# ========== 4. Retry-budget ==========

class TestRetryBudget:
    HASH = "abcd1234"

    def test_blokada_po_trzech_porazkach(self):
        m = make_monitor()
        for _ in range(3):
            assert m._schedule_apply_blocked(VIN, self.HASH) is False
            m._record_schedule_apply_failure(VIN, self.HASH)
        assert m._schedule_apply_blocked(VIN, self.HASH) is True

    def test_inny_hash_resetuje_licznik(self):
        m = make_monitor()
        for _ in range(3):
            m._record_schedule_apply_failure(VIN, self.HASH)
        # Nowy plan (inny hash) nie jest blokowany
        assert m._schedule_apply_blocked(VIN, "inny0000") is False

    def test_sukces_czysci_licznik(self):
        m = make_monitor()
        for _ in range(3):
            m._record_schedule_apply_failure(VIN, self.HASH)
        m._clear_schedule_apply_failures(VIN)
        assert m._schedule_apply_blocked(VIN, self.HASH) is False

    def test_cooldown_odblokowuje(self):
        m = make_monitor()
        for _ in range(3):
            m._record_schedule_apply_failure(VIN, self.HASH)
        # Przesuń ostatnią próbę poza cooldown
        m.schedule_apply_attempts[VIN]['last_attempt_ts'] = (
            time.time() - m.SCHEDULE_APPLY_COOLDOWN_SECONDS - 1
        )
        assert m._schedule_apply_blocked(VIN, self.HASH) is False


# ========== 5. Rekoncyliacja po treści ==========

class TestReconciliation:
    def _desired(self, start, end, enabled=True):
        return ChargeSchedule(days_of_week='All', enabled=enabled,
                              start_time=start, end_time=end,
                              start_enabled=True, end_enabled=True)

    def test_identyczne_okno_jest_dopasowane(self):
        m = make_monitor()
        vehicle_schedule = {'id': 1, 'start_time': 120, 'end_time': 300, 'enabled': True}
        assert m._schedule_content_matches(vehicle_schedule, self._desired(120, 300)) is True

    def test_rozne_czasy_nie_pasuja(self):
        m = make_monitor()
        vehicle_schedule = {'id': 1, 'start_time': 120, 'end_time': 300, 'enabled': True}
        assert m._schedule_content_matches(vehicle_schedule, self._desired(130, 300)) is False

    def test_enabled_musi_sie_zgadzac(self):
        m = make_monitor()
        vehicle_schedule = {'id': 1, 'start_time': 120, 'end_time': 300, 'enabled': False}
        assert m._schedule_content_matches(vehicle_schedule, self._desired(120, 300, enabled=True)) is False


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-v']))
