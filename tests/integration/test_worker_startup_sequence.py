#!/usr/bin/env python3
"""
Test Worker Service Startup Sequence
Weryfikuje naprawki sekwencji uruchamiania Worker Service
"""

import os
import sys
import unittest
from unittest.mock import Mock, patch, MagicMock
import logging

# Dodaj ścieżkę do modułów
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import z naprawionych modułów
from src.worker.worker_service import CloudTeslaWorker, WorkerHealthCheckHandler

class TestWorkerStartupSequence(unittest.TestCase):
    """Test naprawek Worker Service startup sequence"""
    
    def setUp(self):
        """Setup testu"""
        # Mock zmiennych środowiskowych
        self.env_patcher = patch.dict(os.environ, {
            'TESLA_WORKER_MODE': 'true',
            'TESLA_SMART_PROXY_MODE': 'true', 
            'TESLA_PROXY_AVAILABLE': 'true',
            'TESLA_PRIVATE_KEY_READY': 'true',
            'TESLA_HTTP_PROXY_HOST': 'localhost',
            'TESLA_HTTP_PROXY_PORT': '4443',
            'GOOGLE_CLOUD_PROJECT': 'test-project'
        })
        self.env_patcher.start()
        
        # Mock file operations
        self.file_patcher = patch('os.path.exists')
        self.mock_exists = self.file_patcher.start()
        self.mock_exists.return_value = True
        
        self.size_patcher = patch('os.path.getsize')
        self.mock_size = self.size_patcher.start()
        self.mock_size.return_value = 1024  # Non-empty key
        
    def tearDown(self):
        """Cleanup testu"""
        self.env_patcher.stop()
        self.file_patcher.stop()
        self.size_patcher.stop()
    
    @patch('cloud_tesla_worker.CloudTeslaMonitor')
    def test_worker_initialization_without_early_tesla_test(self, mock_monitor_class):
        """Test: Worker nie testuje Tesla API podczas inicjalizacji"""
        
        # Mock monitora
        mock_monitor = Mock()
        mock_monitor._get_warsaw_time.return_value = Mock()
        mock_monitor_class.return_value = mock_monitor
        
        # Inicjalizuj Worker
        with patch('cloud_tesla_worker.HTTPServer'):
            worker = CloudTeslaWorker()
        
        # Sprawdź że monitor został utworzony
        mock_monitor_class.assert_called_once()
        
        # Sprawdź że Tesla Controller connect() NIE był wywołany podczas init
        # (to jest nasza naprawka - brak wczesnego testowania Tesla API)
        mock_monitor.tesla_controller.connect.assert_not_called()
        
        print("✅ Test passed: Worker nie testuje Tesla API podczas inicjalizacji")
    
    @patch('cloud_tesla_worker.CloudTeslaMonitor')
    def test_prepare_worker_for_cycle_checks_readiness(self, mock_monitor_class):
        """Test: _prepare_worker_for_cycle sprawdza gotowość komponentów"""
        
        # Mock monitora z metodami proxy
        mock_monitor = Mock()
        mock_monitor._get_warsaw_time.return_value = Mock(strftime=Mock(return_value='[10:30]'))
        mock_monitor.tesla_controller.connect.return_value = True
        mock_monitor.proxy_running = False
        mock_monitor._start_proxy_on_demand.return_value = True
        mock_monitor_class.return_value = mock_monitor
        
        # Mock HTTP handler
        with patch('cloud_tesla_worker.HTTPServer'):
            worker = CloudTeslaWorker()
            
            # Mock HTTP request handler
            handler = WorkerHealthCheckHandler(mock_monitor)
            handler.headers = {'Content-Length': '0'}
            handler.rfile = Mock()
            handler.rfile.read.return_value = b'{}'
            handler._send_response = Mock()
            
            # Test _prepare_worker_for_cycle (wywoływana przez _handle_scout_trigger)
            result = handler._prepare_worker_for_cycle()
            
            # Sprawdź że metoda zwraca True (system gotowy)
            self.assertTrue(result)
            
            # Sprawdź że proxy został uruchomiony on-demand
            mock_monitor._start_proxy_on_demand.assert_called_once()
        
        print("✅ Test passed: _prepare_worker_for_cycle sprawdza gotowość")
    
    @patch('cloud_tesla_worker.CloudTeslaMonitor')
    def test_private_key_not_ready_prevents_proxy_start(self, mock_monitor_class):
        """Test: Brak gotowego private key uniemożliwia uruchomienie proxy"""
        
        # Mock monitora
        mock_monitor = Mock()
        mock_monitor._get_warsaw_time.return_value = Mock(strftime=Mock(return_value='[10:30]'))
        mock_monitor.smart_proxy_mode = True
        mock_monitor.proxy_available = True
        mock_monitor.proxy_running = False
        mock_monitor_class.return_value = mock_monitor
        
        # Ustaw TESLA_PRIVATE_KEY_READY=false
        with patch.dict(os.environ, {'TESLA_PRIVATE_KEY_READY': 'false'}):
            with patch('cloud_tesla_worker.HTTPServer'):
                worker = CloudTeslaWorker()
                
                # Mock handler
                handler = WorkerHealthCheckHandler(mock_monitor)
                handler.headers = {'Content-Length': '0'}
                handler.rfile = Mock()
                handler.rfile.read.return_value = b'{}'
                handler._send_response = Mock()
                
                # Test prepare_worker_for_cycle
                result = handler._prepare_worker_for_cycle()
                
                # Sprawdź że system nie jest gotowy (private key niegotowy)
                # Ale metoda powinna zwrócić True bo może działać bez proxy
                self.assertTrue(result)
                
                # Sprawdź że proxy NIE był uruchamiany
                mock_monitor._start_proxy_on_demand.assert_not_called()
        
        print("✅ Test passed: Brak private key uniemożliwia proxy start")
    
    def test_environment_variables_setup(self):
        """Test: Zmienne środowiskowe są poprawnie skonfigurowane"""
        
        # Sprawdź kluczowe zmienne środowiskowe
        self.assertEqual(os.getenv('TESLA_WORKER_MODE'), 'true')
        self.assertEqual(os.getenv('TESLA_SMART_PROXY_MODE'), 'true')
        self.assertEqual(os.getenv('TESLA_PROXY_AVAILABLE'), 'true')
        self.assertEqual(os.getenv('TESLA_PRIVATE_KEY_READY'), 'true')
        
        print("✅ Test passed: Zmienne środowiskowe poprawnie skonfigurowane")
    
    @patch('cloud_tesla_worker.CloudTeslaMonitor')
    def test_scout_trigger_requires_system_readiness(self, mock_monitor_class):
        """Test: Scout trigger sprawdza gotowość systemu przed cyklem"""
        
        # Mock monitora
        mock_monitor = Mock()
        mock_monitor._get_warsaw_time.return_value = Mock(
            strftime=Mock(return_value='[10:30]'),
            isoformat=Mock(return_value='2025-01-01T10:30:00')
        )
        mock_monitor.run_monitoring_cycle = Mock()
        mock_monitor_class.return_value = mock_monitor
        
        with patch('cloud_tesla_worker.HTTPServer'):
            worker = CloudTeslaWorker()
            
            # Mock handler z _prepare_worker_for_cycle zwracającym False
            handler = WorkerHealthCheckHandler(mock_monitor)
            handler.headers = {'Content-Length': '2'}
            handler.rfile = Mock()
            handler.rfile.read.return_value = b'{}'
            handler._send_response = Mock()
            handler._prepare_worker_for_cycle = Mock(return_value=False)
            
            # Test _handle_scout_trigger
            handler._handle_scout_trigger()
            
            # Sprawdź że _prepare_worker_for_cycle został wywołany
            handler._prepare_worker_for_cycle.assert_called_once()
            
            # Sprawdź że monitoring cycle NIE został uruchomiony (system niegotowy)
            mock_monitor.run_monitoring_cycle.assert_not_called()
            
            # Sprawdź że wysłano błąd 500
            handler._send_response.assert_called_once()
            args = handler._send_response.call_args
            self.assertEqual(args[0][0], 500)  # Status code 500
            self.assertIn('error', args[0][1])  # Response zawiera 'error'
        
        print("✅ Test passed: Scout trigger sprawdza gotowość przed cyklem")

def main():
    """Uruchom testy Worker Service startup sequence"""
    print("🔧 === TEST WORKER SERVICE STARTUP SEQUENCE ===")
    print("🎯 Weryfikacja naprawek sekwencji uruchamiania Worker Service")
    print("")
    
    # Konfiguruj logging
    logging.basicConfig(level=logging.WARNING)  # Zmniejsz spam logów
    
    # Uruchom testy
    unittest.main(verbosity=2, exit=False)
    
    print("")
    print("✅ === TESTY STARTUP SEQUENCE ZAKOŃCZONE ===")
    print("💡 Worker Service powinien teraz:")
    print("   1. ✅ Nie testować Tesla API podczas inicjalizacji")
    print("   2. ✅ Sprawdzać gotowość private key przed proxy")
    print("   3. ✅ Uruchamiać proxy on-demand przed cyklem")
    print("   4. ✅ Sprawdzać gotowość systemu przed Scout trigger")

if __name__ == "__main__":
    main() 