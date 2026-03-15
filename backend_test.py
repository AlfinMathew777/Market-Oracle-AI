#!/usr/bin/env python3
"""Market Oracle AI Backend API Testing Suite
Tests all 4 backend endpoints for Market Oracle AI platform.
"""

import requests
import sys
import json
from datetime import datetime

class MarketOracleAPITester:
    def __init__(self, base_url="https://mirror-fish.preview.emergentagent.com"):
        self.base_url = base_url
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []

    def log_test(self, test_name, success, details="", expected_vs_actual=""):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            status = "✅ PASS"
        else:
            status = "❌ FAIL"
        
        result = {
            "test": test_name,
            "status": status,
            "details": details,
            "expected_vs_actual": expected_vs_actual
        }
        self.test_results.append(result)
        print(f"{status} - {test_name}")
        if details:
            print(f"    Details: {details}")
        if expected_vs_actual:
            print(f"    Expected vs Actual: {expected_vs_actual}")

    def test_health_check(self):
        """Test basic health check endpoints"""
        try:
            # Root endpoint
            response = requests.get(f"{self.base_url}/", timeout=10)
            if response.status_code == 200:
                data = response.json()
                success = data.get("name") == "Market Oracle AI API" and data.get("status") == "operational"
                self.log_test(
                    "Root Health Check", 
                    success, 
                    f"Status: {response.status_code}, Response: {data.get('name', 'N/A')}"
                )
            else:
                self.log_test("Root Health Check", False, f"HTTP {response.status_code}")

            # API health endpoint
            response = requests.get(f"{self.base_url}/api/health", timeout=10)
            if response.status_code == 200:
                data = response.json()
                success = data.get("status") == "ok"
                self.log_test("API Health Check", success, f"Status: {data.get('status')}")
            else:
                self.log_test("API Health Check", False, f"HTTP {response.status_code}")

        except Exception as e:
            self.log_test("Health Checks", False, f"Error: {str(e)}")

    def test_acled_endpoint(self):
        """Test ACLED conflict events endpoint"""
        try:
            response = requests.get(f"{self.base_url}/api/data/acled", timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                
                # Check response structure
                success = (
                    data.get("status") == "success" and
                    "data" in data and
                    "count" in data and
                    data.get("data", {}).get("type") == "FeatureCollection"
                )
                
                if success:
                    features = data["data"].get("features", [])
                    event_count = len(features)
                    
                    # Verify we have 8 ACLED events as expected
                    expected_count = 8
                    count_correct = event_count == expected_count
                    
                    # Check first event structure
                    sample_event = features[0] if features else {}
                    event_structure_valid = (
                        sample_event.get("type") == "Feature" and
                        "geometry" in sample_event and
                        "properties" in sample_event and
                        "coordinates" in sample_event.get("geometry", {})
                    )
                    
                    overall_success = count_correct and event_structure_valid
                    
                    self.log_test(
                        "ACLED Events Endpoint",
                        overall_success,
                        f"Events: {event_count}, Data source: {data.get('data_source', 'unknown')}",
                        f"Expected {expected_count} events, got {event_count}"
                    )
                    
                    # Additional check for specific events
                    iran_event = None
                    for feature in features:
                        if "Iran" in feature.get("properties", {}).get("country", ""):
                            iran_event = feature
                            break
                    
                    self.log_test(
                        "Iran/Strait of Hormuz Event Present",
                        iran_event is not None,
                        f"Found Iran event: {iran_event.get('properties', {}).get('description', 'N/A') if iran_event else 'Not found'}"
                    )
                    
                else:
                    self.log_test("ACLED Events Endpoint", False, "Invalid response structure")
            else:
                self.log_test("ACLED Events Endpoint", False, f"HTTP {response.status_code}")

        except Exception as e:
            self.log_test("ACLED Events Endpoint", False, f"Error: {str(e)}")

    def test_asx_prices_endpoint(self):
        """Test ASX prices endpoint with P0 heatmap requirements"""
        expected_tickers = ['BHP.AX', 'RIO.AX', 'FMG.AX', 'CBA.AX', 'LYC.AX']
        
        try:
            response = requests.get(f"{self.base_url}/api/data/asx-prices", timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                
                success = data.get("status") == "success" and "data" in data
                
                if success:
                    tickers = data["data"]
                    ticker_count = len(tickers)
                    
                    # Check we have 5 tickers
                    count_correct = ticker_count == 5
                    
                    # Check ticker symbols are correct
                    found_tickers = [t.get("ticker") for t in tickers]
                    tickers_correct = all(ticker in found_tickers for ticker in expected_tickers)
                    
                    # Check price data structure
                    sample_ticker = tickers[0] if tickers else {}
                    structure_valid = (
                        "ticker" in sample_ticker and
                        "price" in sample_ticker and
                        "currency" in sample_ticker and
                        "change_pct_1d" in sample_ticker and
                        "change_abs_1d" in sample_ticker
                    )
                    
                    # P0 Feature Test: Check history_5d array with 5 data points
                    history_5d_valid = self.validate_history_5d_data(tickers)
                    
                    overall_success = count_correct and tickers_correct and structure_valid and history_5d_valid
                    
                    self.log_test(
                        "ASX Prices Endpoint (P0 Feature)",
                        overall_success,
                        f"Tickers: {ticker_count}, Sample price: ${sample_ticker.get('price', 'N/A')}, History 5d: {'✓' if history_5d_valid else '✗'}",
                        f"Expected 5 tickers {expected_tickers}, got {found_tickers}"
                    )
                    
                else:
                    self.log_test("ASX Prices Endpoint (P0 Feature)", False, "Invalid response structure")
            else:
                self.log_test("ASX Prices Endpoint (P0 Feature)", False, f"HTTP {response.status_code}")

        except Exception as e:
            self.log_test("ASX Prices Endpoint (P0 Feature)", False, f"Error: {str(e)}")

    def validate_history_5d_data(self, tickers):
        """Validate history_5d array structure for P0 heatmap feature"""
        for ticker_data in tickers:
            history_5d = ticker_data.get("history_5d", [])
            
            # Must have exactly 5 data points
            if len(history_5d) != 5:
                self.log_test(
                    f"History 5D Count - {ticker_data.get('ticker')}",
                    False,
                    f"Expected 5 data points, got {len(history_5d)}"
                )
                return False
            
            # Each data point must have date and close
            for i, data_point in enumerate(history_5d):
                if not isinstance(data_point, dict) or "date" not in data_point or "close" not in data_point:
                    self.log_test(
                        f"History 5D Structure - {ticker_data.get('ticker')} Day {i+1}",
                        False,
                        f"Invalid data point structure: {data_point}"
                    )
                    return False
                
                # Validate close price is numeric
                try:
                    float(data_point["close"])
                except (ValueError, TypeError):
                    self.log_test(
                        f"History 5D Price - {ticker_data.get('ticker')} Day {i+1}",
                        False,
                        f"Invalid close price: {data_point['close']}"
                    )
                    return False
        
        # Log success for history_5d validation
        sample_ticker = tickers[0].get('ticker', 'Unknown') if tickers else 'Unknown'
        sample_history = tickers[0].get('history_5d', []) if tickers else []
        self.log_test(
            "History 5D Data Validation",
            True,
            f"All 5 tickers have valid 5-day price history. Sample ({sample_ticker}): {len(sample_history)} days"
        )
        return True

    def test_port_hedland_endpoint(self):
        """Test Port Hedland vessel status endpoint"""
        try:
            response = requests.get(f"{self.base_url}/api/data/port-hedland", timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                
                success = data.get("status") == "success" and "data" in data
                
                if success:
                    port_data = data["data"]
                    
                    # Check required fields
                    required_fields = ["vessel_count", "congestion_level", "data_source"]
                    fields_present = all(field in port_data for field in required_fields)
                    
                    # Check congestion level is HIGH as expected
                    congestion_correct = port_data.get("congestion_level") == "HIGH"
                    
                    # Check vessel count (should be 14 from mock data)
                    vessel_count = port_data.get("vessel_count", 0)
                    vessel_count_correct = vessel_count > 0
                    
                    overall_success = fields_present and congestion_correct and vessel_count_correct
                    
                    self.log_test(
                        "Port Hedland Endpoint",
                        overall_success,
                        f"Vessels: {vessel_count}, Congestion: {port_data.get('congestion_level')}, Source: {port_data.get('data_source')}",
                        f"Expected HIGH congestion with >0 vessels"
                    )
                    
                else:
                    self.log_test("Port Hedland Endpoint", False, "Invalid response structure")
            else:
                self.log_test("Port Hedland Endpoint", False, f"HTTP {response.status_code}")

        except Exception as e:
            self.log_test("Port Hedland Endpoint", False, f"Error: {str(e)}")

    def test_macro_context_endpoint(self):
        """Test P3 Feature: Macro economic context endpoint"""
        expected_indicators = ['fed_rate', 'aud_usd', 'iron_ore', 'rba_rate', 'asx_200']
        
        try:
            response = requests.get(f"{self.base_url}/api/data/macro-context", timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                
                success = data.get("status") == "success" and "data" in data
                
                if success:
                    macro_data = data["data"]
                    
                    # Check all 5 indicators are present
                    indicators_present = all(indicator in macro_data for indicator in expected_indicators)
                    
                    # Check Fed Funds Rate structure
                    fed_rate = macro_data.get("fed_rate", {})
                    fed_valid = (
                        "value" in fed_rate and 
                        "label" in fed_rate and
                        "source" in fed_rate and
                        fed_rate.get("source") == "FRED"
                    )
                    
                    # Check AUD/USD structure
                    aud_usd = macro_data.get("aud_usd", {})
                    aud_valid = (
                        "value" in aud_usd and 
                        "label" in aud_usd and
                        "source" in aud_usd and
                        aud_usd.get("source") == "Yahoo Finance"
                    )
                    
                    # Check Iron Ore with fallback
                    iron_ore = macro_data.get("iron_ore", {})
                    iron_valid = (
                        "value" in iron_ore and 
                        "label" in iron_ore and
                        "status" in iron_ore and
                        iron_ore.get("value") == 97.50 and  # Expected fallback value
                        iron_ore.get("status") == "delayed"
                    )
                    
                    # Check RBA Cash Rate (hardcoded)
                    rba_rate = macro_data.get("rba_rate", {})
                    rba_valid = (
                        "value" in rba_rate and 
                        "label" in rba_rate and
                        rba_rate.get("value") == 4.10 and  # Expected hardcoded value
                        rba_rate.get("source") == "RBA"
                    )
                    
                    # Check ASX 200 with change percentage
                    asx_200 = macro_data.get("asx_200", {})
                    asx_valid = (
                        "value" in asx_200 and 
                        "label" in asx_200 and
                        "change_pct" in asx_200 and
                        "source" in asx_200 and
                        asx_200.get("source") == "Yahoo Finance"
                    )
                    
                    # Check fetched_at timestamp
                    has_timestamp = "fetched_at" in macro_data
                    
                    overall_success = (
                        indicators_present and fed_valid and aud_valid and 
                        iron_valid and rba_valid and asx_valid and has_timestamp
                    )
                    
                    self.log_test(
                        "P3 Macro Context Endpoint",
                        overall_success,
                        f"Indicators: {len([i for i in expected_indicators if i in macro_data])}/5, "
                        f"Fed: {fed_rate.get('label', 'N/A')}, "
                        f"AUD/USD: {aud_usd.get('label', 'N/A')}, "
                        f"Iron Ore: {iron_ore.get('label', 'N/A')} ({iron_ore.get('status', 'N/A')}), "
                        f"RBA: {rba_rate.get('label', 'N/A')}, "
                        f"ASX 200: {asx_200.get('label', 'N/A')} ({asx_200.get('change_pct', 0):.2f}%)",
                        f"Expected all 5 indicators with proper structure"
                    )
                    
                    # Test Iron Ore fallback mechanism specifically
                    self.log_test(
                        "Iron Ore Fallback ($97.50/t)",
                        iron_ore.get("value") == 97.50 and iron_ore.get("status") == "delayed",
                        f"Value: ${iron_ore.get('value', 'N/A')}/t, Status: {iron_ore.get('status', 'N/A')}",
                        "Expected $97.50/t with delayed status"
                    )
                    
                else:
                    self.log_test("P3 Macro Context Endpoint", False, "Invalid response structure")
            else:
                self.log_test("P3 Macro Context Endpoint", False, f"HTTP {response.status_code}")

        except Exception as e:
            self.log_test("P3 Macro Context Endpoint", False, f"Error: {str(e)}")

    def test_simulate_endpoint_exists(self):
        """Test that simulation endpoint exists (without running simulation)"""
        try:
            # Test with invalid/empty body to see if endpoint exists
            response = requests.post(
                f"{self.base_url}/api/simulate", 
                json={},
                timeout=10
            )
            
            # We expect either 422 (validation error) or 400 (bad request) or 500
            # What we don't want is 404 (not found) or 405 (method not allowed)
            endpoint_exists = response.status_code not in [404, 405]
            
            self.log_test(
                "Simulation Endpoint Exists",
                endpoint_exists,
                f"HTTP {response.status_code} (endpoint exists if not 404/405)",
                "Expected non-404/405 status code"
            )
            
        except Exception as e:
            self.log_test("Simulation Endpoint Exists", False, f"Error: {str(e)}")

    def run_all_tests(self):
        """Run complete test suite"""
        print("🚀 Starting Market Oracle AI Backend API Tests")
        print(f"Base URL: {self.base_url}")
        print("=" * 60)
        
        self.test_health_check()
        self.test_acled_endpoint()
        self.test_asx_prices_endpoint()
        self.test_port_hedland_endpoint()
        self.test_macro_context_endpoint()  # P3 Feature Test
        self.test_simulate_endpoint_exists()
        
        print("\n" + "=" * 60)
        print(f"📊 Test Results: {self.tests_passed}/{self.tests_run} passed")
        
        if self.tests_passed == self.tests_run:
            print("🎉 All tests passed!")
            return 0
        else:
            print("⚠️  Some tests failed - check details above")
            return 1

def main():
    tester = MarketOracleAPITester()
    return tester.run_all_tests()

if __name__ == "__main__":
    sys.exit(main())