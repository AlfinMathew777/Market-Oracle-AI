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
        """Test ASX prices endpoint"""
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
                        "change_pct_1d" in sample_ticker
                    )
                    
                    overall_success = count_correct and tickers_correct and structure_valid
                    
                    self.log_test(
                        "ASX Prices Endpoint",
                        overall_success,
                        f"Tickers: {ticker_count}, Sample price: ${sample_ticker.get('price', 'N/A')}",
                        f"Expected 5 tickers {expected_tickers}, got {found_tickers}"
                    )
                    
                else:
                    self.log_test("ASX Prices Endpoint", False, "Invalid response structure")
            else:
                self.log_test("ASX Prices Endpoint", False, f"HTTP {response.status_code}")

        except Exception as e:
            self.log_test("ASX Prices Endpoint", False, f"Error: {str(e)}")

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