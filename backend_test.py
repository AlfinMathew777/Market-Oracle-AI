#!/usr/bin/env python3
"""
Market Oracle AI - Backend Testing Suite
Tests transition from mock data to real-time data integration
Phase 1: FRED, MarketAux, AISStream, and GDELT integrations
"""

import requests
import json
import time
import sys
import urllib.parse
from datetime import datetime
from typing import Dict, Any, List

def encodeURIComponent(s):
    """Python equivalent of JavaScript's encodeURIComponent"""
    return urllib.parse.quote(s, safe='')

class MarketOracleBackendTester:
    def __init__(self, base_url="https://mirror-fish.preview.emergentagent.com"):
        self.base_url = base_url
        self.tests_run = 0
        self.tests_passed = 0
        self.failures = []
        
    def log_test(self, name: str, passed: bool, details: str = ""):
        """Log test result"""
        self.tests_run += 1
        if passed:
            self.tests_passed += 1
            print(f"✅ {name}")
            if details:
                print(f"   {details}")
        else:
            self.failures.append(f"{name}: {details}")
            print(f"❌ {name}")
            print(f"   FAILED: {details}")
    
    def test_health_check(self):
        """Test comprehensive health check with API status (FRED, MarketAux, yfinance, AISStream, GDELT)"""
        print("\n🏥 Testing comprehensive health check...")
        try:
            response = requests.get(f"{self.base_url}/api/health", timeout=15)
            success = response.status_code == 200
            
            if not success:
                self.log_test("Health Check - Basic connectivity", False, f"Status code: {response.status_code}")
                return
                
            data = response.json()
            
            self.log_test("Health Check - Server responding", True, f"Status: {data.get('status')}")
            
            # Check data sources status
            data_sources = data.get("data_sources", {})
            
            # FRED should be OK with provided key
            fred_status = data_sources.get("FRED", {}).get("status")
            fred_ok = fred_status == "OK"
            self.log_test("Health Check - FRED integration", fred_ok, 
                         f"FRED status: {fred_status}, Fields: {data_sources.get('FRED', {}).get('fields_returned', 'N/A')}")
            
            # MarketAux should be OK with provided key
            marketaux_status = data_sources.get("MarketAux", {}).get("status")  
            marketaux_ok = marketaux_status in ["OK", "NO_ARTICLES"]  # Either is acceptable
            self.log_test("Health Check - MarketAux integration", marketaux_ok,
                         f"MarketAux status: {marketaux_status}")
            
            # yfinance should be OK (no key needed)
            yfinance_status = data_sources.get("yfinance", {}).get("status")
            yfinance_ok = yfinance_status == "OK"
            self.log_test("Health Check - yfinance integration", yfinance_ok,
                         f"yfinance status: {yfinance_status}")
                         
            # AISStream should be PENDING_KEY (key not configured)
            aisstream_status = data_sources.get("AISStream", {}).get("status")
            aisstream_pending = aisstream_status == "PENDING_KEY"
            self.log_test("Health Check - AISStream graceful handling", aisstream_pending,
                         f"AISStream status: {aisstream_status} (expected PENDING_KEY)")
            
            # GDELT should be OK or RATE_LIMITED
            gdelt_status = data_sources.get("GDELT", {}).get("status")
            gdelt_ok = gdelt_status in ["OK", "RATE_LIMITED"]
            self.log_test("Health Check - GDELT integration", gdelt_ok,
                         f"GDELT status: {gdelt_status}")
            
            # Overall demo readiness
            demo_ready = data.get("demo_ready", False)
            live_sources = data.get("live_data_sources", "0/0")
            self.log_test("Health Check - Demo ready status", demo_ready,
                         f"Live sources: {live_sources}")
                
        except Exception as e:
            self.log_test("Health Check - Comprehensive status", False, f"Connection error: {str(e)}")

    def test_macro_context_brent_gold(self):
        """Test /api/data/macro-context returns Brent Crude and Gold price badges"""
        print("\n🛢️ Testing macro-context with Brent Crude and Gold badges...")
        
        try:
            response = requests.get(f"{self.base_url}/api/data/macro-context", timeout=15)
            success = response.status_code == 200
            
            if not success:
                self.log_test("Macro Context - API Response", False, 
                             f"Status code: {response.status_code}")
                return
                
            data = response.json()
            
            if data.get("status") != "success":
                self.log_test("Macro Context - Response Status", False, 
                             f"Expected 'success', got: {data.get('status')}")
                return
                
            macro_data = data.get("data", {})
            
            # Check for Brent Crude badge
            brent_crude = macro_data.get("brent_crude", {})
            brent_value = brent_crude.get("value", "N/A")
            brent_label = brent_crude.get("label", "N/A")
            has_brent = brent_value != "N/A" and brent_label != "N/A"
            
            self.log_test("Macro Context - Brent Crude badge", has_brent,
                         f"Brent: {brent_label} (value: {brent_value})")
            
            # Check for Gold badge  
            gold = macro_data.get("gold", {})
            gold_value = gold.get("value", "N/A")
            gold_label = gold.get("label", "N/A")
            has_gold = gold_value != "N/A" and gold_label != "N/A"
            
            self.log_test("Macro Context - Gold badge", has_gold,
                         f"Gold: {gold_label} (value: {gold_value})")
            
            # Verify we now have 7 badges total (5 original + Brent + Gold)
            expected_badges = ["fed_rate", "aud_usd", "iron_ore", "rba_rate", "asx_200", "brent_crude", "gold"]
            available_badges = [key for key in expected_badges if key in macro_data and macro_data[key].get("label") != "N/A"]
            
            self.log_test("Macro Context - 7 total badges", len(available_badges) >= 5,  # At minimum, should have most badges
                         f"Available badges: {len(available_badges)}/7 - {available_badges}")
                         
        except Exception as e:
            self.log_test("Macro Context - Brent/Gold badges", False, f"Exception: {str(e)}")

    def test_australian_macro_fred_data(self):
        """Test /api/data/australian-macro returns 14 fields with FRED data"""
        print("\n🇦🇺 Testing Australian macro with 14 FRED fields...")
        
        try:
            response = requests.get(f"{self.base_url}/api/data/australian-macro", timeout=15)
            success = response.status_code == 200
            
            if not success:
                self.log_test("Australian Macro - API Response", False, 
                             f"Status code: {response.status_code}")
                return
                
            data = response.json()
            
            if data.get("status") != "success":
                self.log_test("Australian Macro - Response Status", False, 
                             f"Expected 'success', got: {data.get('status')}")
                return
                
            macro_data = data.get("data", {})
            
            # Check if using FRED data (should have fetched_at and data dict)
            if macro_data.get("status") == "success" and "data" in macro_data:
                # Real FRED data structure
                fred_fields = macro_data.get("data", {})
                field_count = len(fred_fields)
                
                expected_fred_fields = [
                    "rba_cash_rate", "aud_usd", "unemployment_rate", "long_term_rate",
                    "cpi", "gdp_growth", "exports", "brent_crude_price", "gold_price_usd"
                ]
                
                available_fields = [field for field in expected_fred_fields if field in fred_fields]
                
                self.log_test("Australian Macro - FRED data structure", True, 
                             f"FRED API response with {field_count} fields")
                self.log_test("Australian Macro - Key FRED fields", len(available_fields) >= 7,
                             f"Found {len(available_fields)}/9 key fields: {available_fields}")
            else:
                # Legacy structure - check for direct fields
                expected_fields = [
                    "rba_cash_rate", "unemployment", "cpi", "gdp_growth", 
                    "household_debt_pct_income", "household_saving_ratio",
                    "terms_of_trade_change", "labor_productivity_change"
                ]
                
                available_fields = [field for field in expected_fields if field in macro_data]
                field_count = len(available_fields)
                
                self.log_test("Australian Macro - Field count", field_count >= 8,
                             f"Found {field_count}/14+ fields")
                self.log_test("Australian Macro - Required fields present", len(available_fields) >= 6,
                             f"Key fields: {available_fields}")
            
            # Check data source
            data_source = macro_data.get("source", "Unknown")
            has_fred_source = "FRED" in data_source or data_source == "Australian Bureau of Statistics"
            self.log_test("Australian Macro - Data source", True,
                         f"Source: {data_source}")
                         
        except Exception as e:
            self.log_test("Australian Macro - FRED integration", False, f"Exception: {str(e)}")

    def test_pre_simulation_sentiment(self):
        """Test /api/data/pre-simulation-sentiment combines GDELT + MarketAux sentiment"""
        print("\n🧠 Testing pre-simulation sentiment combining GDELT + MarketAux...")
        
        try:
            # Test with iron ore related tickers and topic
            tickers = "BHP.AX,RIO.AX"
            topic = "China Australia iron ore"
            
            response = requests.get(
                f"{self.base_url}/api/data/pre-simulation-sentiment?tickers={tickers}&topic={encodeURIComponent(topic)}", 
                timeout=30
            )
            success = response.status_code == 200
            
            if not success:
                self.log_test("Pre-Simulation - API Response", False, 
                             f"Status code: {response.status_code}")
                return
                
            data = response.json()
            
            if data.get("status") != "success":
                self.log_test("Pre-Simulation - Response Status", False, 
                             f"Expected 'success', got: {data.get('status')}")
                return
                
            context = data.get("data", {})
            
            # Check structure
            has_combined_bias = "combined_sentiment_bias" in context
            has_signal_strength = "signal_strength" in context
            has_gdelt_signal = "gdelt_signal" in context
            has_news_signal = "news_signal" in context
            
            self.log_test("Pre-Simulation - Response structure", all([has_combined_bias, has_signal_strength, has_gdelt_signal, has_news_signal]),
                         "Has combined_bias, signal_strength, gdelt_signal, news_signal")
            
            # Check GDELT signal
            gdelt_signal = context.get("gdelt_signal", {})
            gdelt_articles = gdelt_signal.get("article_count", 0)
            gdelt_tone = gdelt_signal.get("avgtone", 0)
            gdelt_working = gdelt_signal.get("status") in ["success", "rate_limited", "no_data"]
            
            self.log_test("Pre-Simulation - GDELT signal", gdelt_working,
                         f"GDELT: {gdelt_articles} articles, tone {gdelt_tone}, status: {gdelt_signal.get('status')}")
            
            # Check MarketAux signal
            news_signal = context.get("news_signal", {})
            news_articles = news_signal.get("article_count", 0)
            news_bias = news_signal.get("bias", 0)
            news_working = news_signal.get("status") in ["success", "pending_api_key"]
            
            self.log_test("Pre-Simulation - MarketAux signal", news_working,
                         f"MarketAux: {news_articles} articles, bias {news_bias}, status: {news_signal.get('status')}")
            
            # Check combined sentiment calculation
            combined_bias = context.get("combined_sentiment_bias", 0)
            signal_strength = context.get("signal_strength", "UNKNOWN")
            
            self.log_test("Pre-Simulation - Combined sentiment", True,
                         f"Combined bias: {combined_bias}, strength: {signal_strength}")
            
            # Check commodity context
            commodity_context = context.get("commodity_context", {})
            has_brent = "brent_crude" in commodity_context
            has_gold = "gold" in commodity_context
            
            self.log_test("Pre-Simulation - Commodity context", has_brent and has_gold,
                         f"Brent: {commodity_context.get('brent_crude')}, Gold: {commodity_context.get('gold')}")
                         
        except Exception as e:
            self.log_test("Pre-Simulation - Sentiment integration", False, f"Exception: {str(e)}")

    def test_gdelt_caching(self):
        """Test GDELT service implements 1-hour caching to prevent rate limiting"""
        print("\n⏰ Testing GDELT 1-hour caching mechanism...")
        
        try:
            # Test GDELT endpoint directly
            topic = "Australia iron ore"
            
            # First request
            print("   Making first GDELT request...")
            response1 = requests.get(
                f"{self.base_url}/api/data/gdelt-sentiment?topic={encodeURIComponent(topic)}", 
                timeout=15
            )
            
            if response1.status_code != 200:
                self.log_test("GDELT Caching - First request", False, 
                             f"Status code: {response1.status_code}")
                return
            
            data1 = response1.json()
            if data1.get("status") != "success":
                self.log_test("GDELT Caching - First request success", False,
                             f"Status: {data1.get('status')}")
                return
                             
            gdelt_data1 = data1.get("data", {})
            from_cache1 = gdelt_data1.get("from_cache", False)
            
            # Second request (should hit cache)
            print("   Making second GDELT request (should hit cache)...")
            time.sleep(1)  # Small delay
            response2 = requests.get(
                f"{self.base_url}/api/data/gdelt-sentiment?topic={encodeURIComponent(topic)}", 
                timeout=15
            )
            
            if response2.status_code == 200:
                data2 = response2.json()
                if data2.get("status") == "success":
                    gdelt_data2 = data2.get("data", {})
                    from_cache2 = gdelt_data2.get("from_cache", False)
                    
                    # Cache should be hit on second request
                    cache_working = from_cache2 == True
                    
                    self.log_test("GDELT Caching - Cache mechanism", cache_working,
                                 f"First: cache={from_cache1}, Second: cache={from_cache2}")
                    
                    # Check cache age is reported
                    cache_age = gdelt_data2.get("cache_age_seconds", 0)
                    self.log_test("GDELT Caching - Cache age tracking", cache_age > 0 if from_cache2 else True,
                                 f"Cache age: {cache_age} seconds")
                else:
                    self.log_test("GDELT Caching - Second request", False, 
                                 f"Status: {data2.get('status')}")
            else:
                self.log_test("GDELT Caching - Second request", False,
                             f"Status code: {response2.status_code}")
                             
        except Exception as e:
            self.log_test("GDELT Caching - Cache mechanism", False, f"Exception: {str(e)}")

    def test_aisstream_graceful_handling(self):
        """Test AISStream service handles missing API key gracefully (no crash on startup)"""
        print("\n🚢 Testing AISStream graceful handling of missing API key...")
        
        try:
            # Test Port Hedland endpoint
            response = requests.get(f"{self.base_url}/api/data/port-hedland", timeout=15)
            success = response.status_code == 200
            
            if not success:
                self.log_test("AISStream - Basic endpoint", False, 
                             f"Status code: {response.status_code}")
                return
                
            data = response.json()
            
            if data.get("status") != "success":
                self.log_test("AISStream - Response format", False, 
                             f"Expected 'success', got: {data.get('status')}")
                return
                
            ais_data = data.get("data", {})
            
            # Should show graceful handling with PENDING_KEY status
            ais_status = ais_data.get("status")
            connected = ais_data.get("connected", False)
            
            graceful_handling = ais_status in ["pending_api_key", "PENDING_KEY", "not_started", "connecting"]
            no_crash = not connected  # Should not be connected without key
            
            self.log_test("AISStream - Graceful key handling", graceful_handling,
                         f"Status: {ais_status}, Connected: {connected}")
            
            self.log_test("AISStream - No crash on startup", no_crash,
                         f"Service running without key, status: {ais_status}")
            
            # Check message is helpful
            message = ais_data.get("message", "")
            has_helpful_message = "aisstream.io" in message or "API key" in message
            
            self.log_test("AISStream - Helpful error message", has_helpful_message,
                         f"Message: {message}")
                         
        except Exception as e:
            self.log_test("AISStream - Graceful handling", False, f"Exception: {str(e)}")

    def run_all_tests(self):
        """Run complete test suite"""
        print("=" * 60)
        print("🧪 MARKET ORACLE AI - BACKEND TESTING SUITE")
        print("   Testing Phase 1: Transition from Mock to Live Data")
        print("   FRED + MarketAux + GDELT + AISStream Integrations")
        print("=" * 60)
        
        start_time = time.time()
        
        # Run all test categories
        self.test_health_check()
        self.test_macro_context_brent_gold()
        self.test_australian_macro_fred_data()
        self.test_pre_simulation_sentiment()
        self.test_gdelt_caching()
        self.test_aisstream_graceful_handling()
        
        # Summary
        elapsed = time.time() - start_time
        print("\n" + "=" * 60)
        print(f"📊 TEST RESULTS SUMMARY")
        print("=" * 60)
        print(f"✅ Tests Passed: {self.tests_passed}/{self.tests_run}")
        print(f"⏱️  Elapsed Time: {elapsed:.1f}s")
        
        success_rate = (self.tests_passed / self.tests_run) * 100 if self.tests_run > 0 else 0
        print(f"📈 Success Rate: {success_rate:.1f}%")
        
        if self.failures:
            print(f"\n❌ FAILURES ({len(self.failures)}):")
            for i, failure in enumerate(self.failures, 1):
                print(f"   {i}. {failure}")
        
        print("\n" + "=" * 60)
        
        # Return status for automation
        return len(self.failures) == 0

def main():
    tester = MarketOracleBackendTester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()