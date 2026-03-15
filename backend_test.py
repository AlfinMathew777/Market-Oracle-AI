#!/usr/bin/env python3
"""
Market Oracle AI - Backend Testing Suite
Tests all 5 priority upgrades for Australian Market Intelligence platform
"""

import requests
import json
import time
import sys
from datetime import datetime
from typing import Dict, Any, List

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
        """Test basic server health"""
        print("\n🏥 Testing basic server health...")
        try:
            response = requests.get(f"{self.base_url}/api/data/health", timeout=10)
            success = response.status_code == 200
            
            if success:
                data = response.json()
                expected_endpoints = [
                    "/api/data/acled",
                    "/api/data/asx-prices", 
                    "/api/data/port-hedland",
                    "/api/data/macro-context",
                    "/api/data/australian-macro"
                ]
                has_all_endpoints = all(ep in data.get("endpoints", []) for ep in expected_endpoints)
                
                self.log_test("Health Check - Server responding", True, f"Status: {data.get('status')}")
                self.log_test("Health Check - All endpoints listed", has_all_endpoints, 
                             f"Found: {len(data.get('endpoints', []))} endpoints")
            else:
                self.log_test("Health Check", False, f"Status code: {response.status_code}")
                
        except Exception as e:
            self.log_test("Health Check", False, f"Connection error: {str(e)}")

    def test_upgrade_1_australian_macro_endpoint(self):
        """UPGRADE 1: Test /api/data/australian-macro endpoint returns correct data"""
        print("\n🇦🇺 Testing Upgrade 1: Australian Macro Endpoint...")
        
        try:
            response = requests.get(f"{self.base_url}/api/data/australian-macro", timeout=15)
            success = response.status_code == 200
            
            if not success:
                self.log_test("Upgrade 1 - Australian Macro API", False, 
                             f"Status code: {response.status_code}")
                return
                
            data = response.json()
            
            # Check response structure
            if data.get("status") != "success":
                self.log_test("Upgrade 1 - Response status", False, 
                             f"Expected 'success', got: {data.get('status')}")
                return
                
            macro_data = data.get("data", {})
            
            # Check required fields for MacroContext component
            required_fields = [
                "cpi",              # 3.8% - for badge
                "gdp_growth",       # 1.4% - for badge  
                "rba_cash_rate",    # 3.85%
                "unemployment",     # 4.1%
                "household_debt_pct_income", # 176%
                "household_saving_ratio",    # 6.1%
                "terms_of_trade_change",     # -4.0%
                "labor_productivity_change", # -0.7%
                "fetched_at",
                "source"
            ]
            
            missing_fields = [field for field in required_fields if field not in macro_data]
            
            self.log_test("Upgrade 1 - Australian Macro API response", True, "200 OK")
            self.log_test("Upgrade 1 - All required fields present", len(missing_fields) == 0,
                         f"Missing: {missing_fields}" if missing_fields else "All 10+ fields present")
            
            # Validate specific values for CPI and GDP (should match mock data)
            cpi_correct = macro_data.get("cpi") == 3.8
            gdp_correct = macro_data.get("gdp_growth") == 1.4
            
            self.log_test("Upgrade 1 - CPI value 3.8%", cpi_correct, 
                         f"Got CPI: {macro_data.get('cpi')}%")
            self.log_test("Upgrade 1 - GDP value 1.4%", gdp_correct,
                         f"Got GDP: {macro_data.get('gdp_growth')}%")
            
            # Check data source indicates mocking
            is_mocked = "Mock Data" in macro_data.get("source", "")
            self.log_test("Upgrade 1 - Uses mock data (expected)", is_mocked,
                         f"Source: {macro_data.get('source')}")
            
        except Exception as e:
            self.log_test("Upgrade 1 - Australian Macro API", False, f"Exception: {str(e)}")

    def test_upgrade_2_sector_sensitivity_logic(self):
        """UPGRADE 2: Test market intelligence sector rate sensitivity"""
        print("\n📊 Testing Upgrade 2: Sector Rate Sensitivity Logic...")
        
        # Test by importing the market intelligence module
        try:
            import sys
            import os
            sys.path.append('/app/backend')
            
            from services.market_intelligence import (
                SECTOR_RATE_SENSITIVITY, 
                get_sector_context, 
                detect_rate_event,
                detect_aud_event,
                build_rate_sensitivity_context,
                build_aud_transmission_context
            )
            
            # Check if all 28 expected tickers are mapped
            expected_tickers = [
                # Banks (5)
                "CBA.AX", "WBC.AX", "NAB.AX", "ANZ.AX", "MQG.AX",
                # REITs (4) 
                "GPT.AX", "CQR.AX", "VCX.AX", "MGR.AX",
                # Infrastructure/Utilities (3)
                "APA.AX", "TLS.AX", "SYD.AX",
                # Resources (6)
                "BHP.AX", "RIO.AX", "FMG.AX", "MIN.AX", "LYC.AX", "PLS.AX",
                # Consumer Staples (2)
                "WOW.AX", "COL.AX",
                # Technology (2)
                "XRO.AX", "WTC.AX",
                # Healthcare (2)
                "CSL.AX", "RHC.AX"
            ]
            # Total = 24 tickers, need to find 4 more for 28
            
            mapped_tickers = list(SECTOR_RATE_SENSITIVITY.keys())
            
            self.log_test("Upgrade 2 - SECTOR_RATE_SENSITIVITY import", True, 
                         f"Found {len(mapped_tickers)} tickers")
            
            # Check coverage of major tickers
            major_tickers_present = all(ticker in mapped_tickers for ticker in expected_tickers)
            self.log_test("Upgrade 2 - Major ASX tickers mapped", major_tickers_present,
                         f"Expected 24+ tickers, found {len(mapped_tickers)}")
            
            # Test rate event detection  
            test_rate_event = {
                "event_type": "Monetary Policy",
                "description": "RBA raises cash rate to 3.85%",
                "notes": "Reserve Bank decision",
                "country": "australia"
            }
            
            is_rate_event = detect_rate_event(test_rate_event)
            self.log_test("Upgrade 2 - Rate event detection", is_rate_event,
                         "RBA rate event correctly detected")
            
            # Test AUD event detection
            test_aud_event = {
                "event_type": "Trade Restriction", 
                "description": "China iron ore import ban",
                "notes": "China Commerce Ministry quota reduction"
            }
            
            is_aud_event = detect_aud_event(test_aud_event)
            self.log_test("Upgrade 2 - AUD event detection", is_aud_event,
                         "China trade event correctly detected")
            
            # Test sector context for banks (should be bullish on rate hikes)
            cba_context = get_sector_context("CBA.AX")
            cba_bullish_on_hikes = cba_context.get("rate_bias") == "bullish_on_hikes"
            self.log_test("Upgrade 2 - Bank rate sensitivity", cba_bullish_on_hikes,
                         f"CBA.AX bias: {cba_context.get('rate_bias')}")
            
            # Test REIT sensitivity (should be bearish on rate hikes)
            gpt_context = get_sector_context("GPT.AX")
            gpt_bearish_on_hikes = gpt_context.get("rate_bias") == "bearish_on_hikes"
            self.log_test("Upgrade 2 - REIT rate sensitivity", gpt_bearish_on_hikes,
                         f"GPT.AX bias: {gpt_context.get('rate_bias')}")
            
        except ImportError as e:
            self.log_test("Upgrade 2 - Market intelligence import", False, 
                         f"Import error: {str(e)}")
        except Exception as e:
            self.log_test("Upgrade 2 - Sector sensitivity logic", False, 
                         f"Error: {str(e)}")

    def test_upgrade_3_new_acled_events(self):
        """UPGRADE 3: Test ACLED service returns 13 total events including 5 new ones"""
        print("\n🌍 Testing Upgrade 3: New ACLED Events...")
        
        try:
            response = requests.get(f"{self.base_url}/api/data/acled", timeout=15)
            success = response.status_code == 200
            
            if not success:
                self.log_test("Upgrade 3 - ACLED API", False, 
                             f"Status code: {response.status_code}")
                return
                
            data = response.json()
            
            if data.get("status") != "success":
                self.log_test("Upgrade 3 - ACLED response status", False,
                             f"Expected 'success', got: {data.get('status')}")
                return
                
            events = data.get("data", {}).get("features", [])
            event_count = len(events)
            
            # Should have 13 events (8 original + 5 new)
            has_13_events = event_count == 13
            self.log_test("Upgrade 3 - Total event count", has_13_events,
                         f"Expected 13, got {event_count}")
            
            # Check for specific new event IDs (acled_009 through acled_013)
            event_ids = [event.get("properties", {}).get("id") for event in events]
            
            new_event_ids = ["acled_009", "acled_010", "acled_011", "acled_012", "acled_013"]
            found_new_events = [eid for eid in new_event_ids if eid in event_ids]
            
            self.log_test("Upgrade 3 - New events present", len(found_new_events) == 5,
                         f"Found {len(found_new_events)}/5 new events: {found_new_events}")
            
            # Check specific new events for correct content
            us_tariff_event = None
            china_iron_event = None
            rba_hike_event = None
            
            for event in events:
                event_id = event.get("properties", {}).get("id")
                if event_id == "acled_009":  # US Liberation Day tariffs
                    us_tariff_event = event
                elif event_id == "acled_010":  # China iron ore ban
                    china_iron_event = event
                elif event_id == "acled_012":  # RBA hike to 3.85%
                    rba_hike_event = event
            
            # Validate US tariff event
            if us_tariff_event:
                us_desc = us_tariff_event.get("properties", {}).get("description", "")
                us_has_tariff = "tariff" in us_desc.lower()
                self.log_test("Upgrade 3 - US tariff event content", us_has_tariff,
                             f"US event description contains 'tariff'")
            
            # Validate China iron ore event
            if china_iron_event:
                china_desc = china_iron_event.get("properties", {}).get("description", "")
                china_has_iron = "iron ore" in china_desc.lower()
                self.log_test("Upgrade 3 - China iron ore event content", china_has_iron,
                             f"China event description contains 'iron ore'")
            
            # Validate RBA rate event
            if rba_hike_event:
                rba_desc = rba_hike_event.get("properties", {}).get("description", "")
                rba_has_rate = "3.85%" in rba_desc
                self.log_test("Upgrade 3 - RBA rate event content", rba_has_rate,
                             f"RBA event mentions 3.85% rate")
                
        except Exception as e:
            self.log_test("Upgrade 3 - ACLED Events API", False, f"Exception: {str(e)}")

    def test_upgrade_4_simulation_engine_enhancement(self):
        """UPGRADE 4: Test simulation engine uses enhanced context"""
        print("\n🤖 Testing Upgrade 4: Enhanced Simulation Context...")
        
        try:
            # Test simulation endpoint with a rate-sensitive event - provide ticker explicitly
            test_event = {
                "event_id": "acled_012",
                "event_description": "RBA raises cash rate to 3.85% - highest since 2011",
                "event_type": "Monetary Policy",
                "lat": -35.3,
                "lon": 149.1,
                "country": "Australia",
                "fatalities": 0,
                "date": "2026-02-03",
                "affected_tickers": ["CBA.AX"]  # Explicitly provide bank ticker for rate event
            }
            
            print(f"   Testing simulation with RBA rate event (CBA.AX)...")
            
            response = requests.post(
                f"{self.base_url}/api/simulate",
                headers={"Content-Type": "application/json"},
                json=test_event,
                timeout=90  # Increased timeout for simulation
            )
            
            success = response.status_code == 200
            
            if not success:
                # Try to get error detail
                try:
                    error_detail = response.json().get("detail", "Unknown error")
                except:
                    error_detail = f"HTTP {response.status_code}"
                
                self.log_test("Upgrade 4 - Simulation API", False,
                             f"Status code: {response.status_code}, Detail: {error_detail}")
                return
                
            data = response.json()
            
            if data.get("status") != "completed":
                self.log_test("Upgrade 4 - Simulation completion", False,
                             f"Expected 'completed', got: {data.get('status')}")
                return
                
            prediction = data.get("prediction", {})
            
            # Check if prediction contains enhanced causal chain
            causal_chain = prediction.get("causal_chain", [])
            has_causal_chain = len(causal_chain) > 0
            
            self.log_test("Upgrade 4 - Simulation completed", True, 
                         f"Status: {data.get('status')}")
            self.log_test("Upgrade 4 - Causal chain generated", has_causal_chain,
                         f"Chain length: {len(causal_chain)} steps")
            
            # Check for Australian transmission mechanisms in causal chain
            chain_text = " ".join([step.get("consequence", "") for step in causal_chain])
            
            has_nim_mention = "nim" in chain_text.lower() or "margin" in chain_text.lower()
            has_australian_context = any(term in chain_text.lower() for term in 
                                       ["australian", "asx", "aud", "rba", "bank"])
            
            self.log_test("Upgrade 4 - Enhanced causal chain quality", has_nim_mention,
                         "Causal chain mentions NIM/margin mechanics")
            self.log_test("Upgrade 4 - Australian context in chain", has_australian_context,
                         "Causal chain includes Australian market context")
                
        except Exception as e:
            self.log_test("Upgrade 4 - Simulation Engine", False, f"Exception: {str(e)}")

    def test_upgrade_5_transmission_templates(self):
        """UPGRADE 5: Test ReportAgent has Australian market transmission templates"""
        print("\n📋 Testing Upgrade 5: Market Transmission Templates...")
        
        try:
            # Read the test_core.py file to check for transmission templates
            with open('/app/backend/scripts/test_core.py', 'r') as f:
                test_core_content = f.read()
            
            # Check for the 5 Australian market transmission templates
            template_names = [
                "AUD Commodity Amplifier",     # Template A
                "Superannuation Contagion",    # Template B
                "Rate Sensitivity Asymmetry",  # Template C
                "China Concentration Risk",    # Template D
                "Critical Minerals Premium"    # Template E
            ]
            
            templates_found = []
            for template in template_names:
                if template in test_core_content:
                    templates_found.append(template)
            
            all_templates_present = len(templates_found) == 5
            self.log_test("Upgrade 5 - All 5 transmission templates", all_templates_present,
                         f"Found {len(templates_found)}/5: {templates_found}")
            
            # Check for specific Australian market mechanics
            has_aud_passthrough = "85% pass-through" in test_core_content
            has_super_correlation = "0.65-0.75 correlation with S&P 500" in test_core_content
            has_china_dependency = "80% of exports to China" in test_core_content or "80% dependency" in test_core_content
            
            self.log_test("Upgrade 5 - AUD transmission mechanism", has_aud_passthrough,
                         "85% FX pass-through mentioned")
            self.log_test("Upgrade 5 - Super fund correlation", has_super_correlation,
                         "Super fund S&P 500 correlation cited")
            self.log_test("Upgrade 5 - China dependency metric", has_china_dependency,
                         "China 80% export dependency mentioned")
            
            # Check for NIM expansion mechanics for banks
            has_nim_mechanics = "NIM expansion" in test_core_content
            self.log_test("Upgrade 5 - Bank NIM mechanics", has_nim_mechanics,
                         "NIM expansion mechanics included")
                
        except Exception as e:
            self.log_test("Upgrade 5 - Transmission Templates", False, f"Exception: {str(e)}")

    def test_comprehensive_integration(self):
        """Test full integration flow: MacroContext + AustralianEconomicContext data"""
        print("\n🔄 Testing Full Integration Flow...")
        
        try:
            # Test macro-context endpoint (original 5 indicators)
            macro_response = requests.get(f"{self.base_url}/api/data/macro-context", timeout=15)
            macro_success = macro_response.status_code == 200
            
            # Test australian-macro endpoint (new 8+ indicators)
            aus_response = requests.get(f"{self.base_url}/api/data/australian-macro", timeout=15)
            aus_success = aus_response.status_code == 200
            
            both_apis_work = macro_success and aus_success
            self.log_test("Integration - Both macro APIs working", both_apis_work,
                         f"macro-context: {macro_response.status_code}, australian-macro: {aus_response.status_code}")
            
            if both_apis_work:
                macro_data = macro_response.json().get("data", {})
                aus_data = aus_response.json().get("data", {})
                
                # Check MacroContext will have 7 total indicators (5 original + 2 new)
                original_indicators = ["fed_rate", "aud_usd", "iron_ore", "rba_rate", "asx_200"]
                new_indicators = ["cpi", "gdp_growth"]  # From australian-macro
                
                original_present = all(indicator in macro_data for indicator in original_indicators)
                new_present = all(indicator in aus_data for indicator in new_indicators)
                
                self.log_test("Integration - Original 5 indicators", original_present,
                             f"Fed rate, AUD/USD, Iron ore, RBA rate, ASX 200")
                self.log_test("Integration - New CPI & GDP indicators", new_present,
                             f"CPI: {aus_data.get('cpi')}%, GDP: {aus_data.get('gdp_growth')}%")
                
        except Exception as e:
            self.log_test("Integration - Full flow", False, f"Exception: {str(e)}")

    def run_all_tests(self):
        """Run complete test suite"""
        print("=" * 60)
        print("🧪 MARKET ORACLE AI - BACKEND TESTING SUITE")
        print("   Testing 5 Priority Upgrades for Australian Market Intelligence")
        print("=" * 60)
        
        start_time = time.time()
        
        # Run all test categories
        self.test_health_check()
        self.test_upgrade_1_australian_macro_endpoint()
        self.test_upgrade_2_sector_sensitivity_logic() 
        self.test_upgrade_3_new_acled_events()
        self.test_upgrade_4_simulation_engine_enhancement()
        self.test_upgrade_5_transmission_templates()
        self.test_comprehensive_integration()
        
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