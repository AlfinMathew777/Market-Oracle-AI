"""Australian Export Impact Engine.

Translates chokepoint disruptions into specific Australian sector,
regional, and ASX stock predictions using official government data.

Sources:
- Australian Department of Industry Resources & Energy Quarterly Dec 2025
- EIA World Oil Transit Chokepoints 2025 H1
- Port Hedland Authority: $288M AUD of iron ore exported per day
"""

import logging

logger = logging.getLogger(__name__)

# Real Australian export data ? December 2025 Resources & Energy Quarterly
AUSTRALIAN_EXPORT_PROFILE = {
    "iron_ore": {
        "annual_value_aud_bn": 105,
        "pct_total_exports": 27,
        "primary_destination": "China (80%)",
        "primary_route": "Port Hedland ? Lombok/Malacca ? China",
        "chokepoints": ["malacca", "lombok"],
        "asx_stocks": ["BHP.AX", "RIO.AX", "FMG.AX"],
        "daily_value_aud_m": 288,  # $288M AUD per day ? Port Hedland alone
        "disruption_impact": "Each day of Malacca closure = ~$288M AUD export delay",
    },
    "lng": {
        "annual_value_aud_bn": 53,
        "pct_total_exports": 14,
        "primary_destination": "Japan (35%), China (30%), Korea (20%)",
        "primary_route": "Karratha/Darwin ? Malacca ? NE Asia, OR ? Europe via Suez",
        "chokepoints": ["malacca", "hormuz", "suez", "bab_el_mandeb"],
        "asx_stocks": ["WDS.AX", "STO.AX"],
        "daily_value_aud_m": 145,
        "disruption_impact": "Hormuz closure spikes LNG spot price 20-50% in 24-48hrs ? WDS BULLISH",
    },
    "coal": {
        "annual_value_aud_bn": 36,
        "pct_total_exports": 9,
        "primary_destination": "India (35%), Japan (25%), Korea (20%)",
        "primary_route": "Queensland ports ? Coral Sea ? Indian Ocean",
        "chokepoints": ["malacca", "lombok"],
        "asx_stocks": ["WHC.AX", "NHC.AX"],
        "daily_value_aud_m": 99,
        "disruption_impact": "Malacca closure forces Cape reroute ? adds 15 days, $1-2M per voyage",
    },
    "gold": {
        "annual_value_aud_bn": 60,
        "pct_total_exports": 16,
        "primary_destination": "Global (air freight primary)",
        "primary_route": "Air freight ? NOT chokepoint dependent",
        "chokepoints": [],
        "asx_stocks": ["NCM.AX", "NST.AX", "EVN.AX"],
        "daily_value_aud_m": 164,
        "disruption_impact": "Global risk-off ? gold safe haven demand ? BULLISH regardless of route",
    },
    "critical_minerals": {
        "annual_value_aud_bn": 5,
        "pct_total_exports": 1,
        "primary_destination": "China (lithium), USA (rare earths)",
        "primary_route": "Fremantle ? Malacca ? China, OR Fremantle ? Cape ? USA/Europe",
        "chokepoints": ["malacca", "cape_good_hope"],
        "asx_stocks": ["LYC.AX", "PLS.AX", "MIN.AX"],
        "daily_value_aud_m": 14,
        "disruption_impact": "Supply disruption anywhere ? LYC premium as alternative supplier",
    },
}

# Chokepoint ? Australian sector impact matrix
CHOKEPOINT_AUSTRALIA_MATRIX = {
    "hormuz": {
        "risk_level": "CRITICAL",
        "australian_impact": {
            "LNG": {
                "direction": "BULLISH",
                "magnitude": "HIGH",
                "reason": "Hormuz carries Qatar LNG ? disruption removes 20% of global LNG supply. Australian LNG becomes premium alternative. WDS and STO revenue surge.",
                "asx_signal": {"WDS.AX": "UP", "STO.AX": "UP"},
                "price_impact": "LNG spot price +20-50% within 48 hours",
                "time_to_asx_impact": "24-48 hours",
            },
            "OIL_PRICE": {
                "direction": "BULLISH_COSTS",
                "magnitude": "HIGH",
                "reason": "Oil price spike ? input cost increase for all Australian manufacturers and transport. Inflationary pressure ? RBA rate hike risk.",
                "asx_signal": {"CBA.AX": "UNCERTAIN"},
                "price_impact": "Brent +$15-30/bbl within 72 hours",
                "time_to_asx_impact": "48-72 hours",
            },
            "IRON_ORE": {
                "direction": "NEUTRAL_NEGATIVE",
                "magnitude": "LOW",
                "reason": "Iron ore ships through Malacca not Hormuz. Indirect impact via China steel demand slowdown if Chinese energy costs rise.",
                "asx_signal": {"BHP.AX": "SLIGHT_DOWN", "FMG.AX": "SLIGHT_DOWN"},
                "time_to_asx_impact": "1-2 weeks (lagged)",
            },
        },
        "australian_regions_affected": {
            "Karratha WA": "HIGH ? LNG export hub, WDS Pluto/North West Shelf",
            "Darwin NT": "HIGH ? Santos LNG export terminal",
            "Gladstone QLD": "MEDIUM ? APLNG export terminal",
            "Perth WA": "MEDIUM ? corporate HQ of WDS, STO, BHP",
        },
        "gdp_impact_estimate": "Hormuz disruption lasting 30 days = estimated $8-15B AUD impact on resource export earnings",
    },
    "malacca": {
        "risk_level": "CRITICAL",
        "australian_impact": {
            "IRON_ORE": {
                "direction": "BEARISH",
                "magnitude": "VERY_HIGH",
                "reason": "Malacca is the PRIMARY route for Australian iron ore to China. Closure forces Lombok/Sunda reroute adding 3-5 days, or Cape reroute adding 15+ days. FMG most exposed as pure Pilbara-China play.",
                "asx_signal": {"BHP.AX": "DOWN", "RIO.AX": "DOWN", "FMG.AX": "DOWN_STRONG"},
                "price_impact": "Freight rates +40-60%. Port Hedland exports $288M AUD/day.",
                "time_to_asx_impact": "12-24 hours",
            },
            "LNG": {
                "direction": "BEARISH",
                "magnitude": "HIGH",
                "reason": "Malacca is also the route for Australian LNG to Japan and Korea. Disruption delays deliveries.",
                "asx_signal": {"WDS.AX": "DOWN", "STO.AX": "DOWN"},
                "time_to_asx_impact": "24-48 hours",
            },
            "COAL": {
                "direction": "BEARISH",
                "magnitude": "MEDIUM",
                "reason": "Queensland coal to India and Korea routes through Malacca. Rerouting cost surge.",
                "asx_signal": {"WHC.AX": "DOWN", "NHC.AX": "DOWN"},
                "time_to_asx_impact": "48-72 hours",
            },
        },
        "australian_regions_affected": {
            "Pilbara WA": "CRITICAL ? BHP/RIO/FMG export halt",
            "Port Hedland WA": "CRITICAL ? world's largest bulk export port, $288M AUD/day",
            "Karratha WA": "HIGH ? LNG + iron ore dual exposure",
            "Gladstone QLD": "HIGH ? coal and LNG exports",
        },
        "gdp_impact_estimate": "Malacca closure lasting 14 days = estimated $4-8B AUD impact. Port Hedland exports $288M AUD of iron ore every single day.",
    },
    "bab_el_mandeb": {
        "risk_level": "HIGH",
        "australian_impact": {
            "LNG_EUROPE": {
                "direction": "BEARISH_COST",
                "magnitude": "MEDIUM",
                "reason": "Bab el-Mandeb + Suez = Australia-to-Europe LNG route. Houthi attacks already forcing Cape reroute. Adds 15 days and $1-2M per voyage.",
                "asx_signal": {"WDS.AX": "SLIGHT_DOWN", "STO.AX": "SLIGHT_DOWN"},
                "current_status": "ALREADY DISRUPTED ? Houthi attacks ongoing since late 2023",
                "time_to_asx_impact": "Already priced in ? watch for escalation triggers",
            },
            "IMPORT_COSTS": {
                "direction": "BEARISH_CONSUMER",
                "magnitude": "MEDIUM",
                "reason": "Australia imports manufactured goods from Europe and Middle East via this route. Disruption raises import costs, contributing to CPI inflation.",
                "asx_signal": {"WOW.AX": "SLIGHT_DOWN", "WES.AX": "SLIGHT_DOWN"},
                "time_to_asx_impact": "4-8 weeks (supply chain lag)",
            },
        },
        "australian_regions_affected": {
            "All Australian ports": "MEDIUM ? import cost increases",
            "Fremantle WA": "MEDIUM ? primary Europe-Australia import port",
        },
        "gdp_impact_estimate": "Ongoing Houthi disruption estimated at $500M-1B AUD annually in additional freight costs",
    },
    "suez": {
        "risk_level": "HIGH",
        "australian_impact": {
            "LNG_EUROPE": {
                "direction": "BEARISH_COST",
                "magnitude": "MEDIUM",
                "reason": "Suez is the fastest route for Australian LNG to European spot market. Closure adds 10-15 days and $800K-1.5M per voyage via Cape.",
                "asx_signal": {"WDS.AX": "SLIGHT_DOWN", "STO.AX": "SLIGHT_DOWN"},
                "time_to_asx_impact": "48-72 hours",
            },
        },
        "australian_regions_affected": {
            "Karratha WA": "MEDIUM ? North West Shelf LNG to Europe affected",
            "Darwin NT": "LOW ? primarily Asia-facing exports",
        },
        "gdp_impact_estimate": "Suez closure lasting 7 days = ~$200M AUD additional freight costs",
    },
    "cape_good_hope": {
        "risk_level": "MEDIUM",
        "australian_impact": {
            "FREIGHT_COSTS": {
                "direction": "BEARISH_COST",
                "magnitude": "HIGH",
                "reason": "Cape is the fallback when Bab/Suez disrupted. If Cape ALSO disrupted, all Australian export routes are simultaneously constrained ? worst case scenario.",
                "asx_signal": {"BHP.AX": "DOWN", "RIO.AX": "DOWN", "WDS.AX": "DOWN", "FMG.AX": "DOWN"},
                "time_to_asx_impact": "24-48 hours",
            },
        },
        "australian_regions_affected": {
            "All WA ports": "HIGH if combined with Bab/Suez disruption",
        },
        "gdp_impact_estimate": "Cape disruption combined with Red Sea disruption = full Australian export route crisis",
    },
    "lombok": {
        "risk_level": "LOW",
        "australian_impact": {
            "IRON_ORE_REROUTE": {
                "direction": "BEARISH",
                "magnitude": "MEDIUM",
                "reason": "Lombok is the PRIMARY ALTERNATIVE when Malacca is disrupted. If BOTH Malacca AND Lombok are blocked simultaneously, Australian iron ore exports face a full crisis ? Cape Horn reroute adds 30 days.",
                "asx_signal": {"FMG.AX": "DOWN_SEVERE", "BHP.AX": "DOWN", "RIO.AX": "DOWN"},
                "scenario": "Malacca + Lombok simultaneous disruption = worst case for Australian resources",
                "time_to_asx_impact": "12 hours if both close simultaneously",
            },
        },
        "australian_regions_affected": {
            "Pilbara WA": "HIGH if combined Malacca+Lombok disruption",
            "Port Hedland WA": "HIGH ? iron ore export backup route blocked",
        },
        "gdp_impact_estimate": "Lombok disruption alone = moderate. Combined with Malacca = catastrophic for Australian iron ore exports.",
    },
}


def predict_australian_impact(disrupted_chokepoints: list, duration_days: int = 7) -> dict:
    """Generate Australian sector and regional impact prediction."""
    all_asx_signals = {}
    affected_regions = {}
    affected_sectors = []
    total_export_value_at_risk = 0

    for cp_id in disrupted_chokepoints:
        impact = CHOKEPOINT_AUSTRALIA_MATRIX.get(cp_id, {})
        if not impact:
            continue

        for sector, data in impact.get("australian_impact", {}).items():
            for ticker, direction in data.get("asx_signal", {}).items():
                all_asx_signals.setdefault(ticker, []).append({
                    "direction": direction,
                    "reason": data["reason"],
                    "magnitude": data["magnitude"],
                    "time_to_impact": data.get("time_to_asx_impact", "unknown"),
                })
            affected_sectors.append(sector)

        for region, severity in impact.get("australian_regions_affected", {}).items():
            affected_regions[region] = severity

    for cp_id in disrupted_chokepoints:
        for commodity, profile in AUSTRALIAN_EXPORT_PROFILE.items():
            if cp_id in profile["chokepoints"]:
                daily_value = profile["annual_value_aud_bn"] * 1e9 / 365
                total_export_value_at_risk += daily_value * duration_days

    state_impacts = _calculate_state_impacts(disrupted_chokepoints)

    return {
        "disrupted_chokepoints": disrupted_chokepoints,
        "duration_days": duration_days,
        "asx_predictions": _consolidate_asx_signals(all_asx_signals),
        "affected_sectors": list(set(affected_sectors)),
        "australian_regions": affected_regions,
        "state_heatmap": state_impacts,
        "export_value_at_risk_aud_bn": round(total_export_value_at_risk / 1e9, 1),
        "simulation_seed": _generate_simulation_seed(disrupted_chokepoints, duration_days),
        "key_insight": _generate_key_insight(disrupted_chokepoints),
    }


def _calculate_state_impacts(disrupted_chokepoints: list) -> dict:
    """Map chokepoint disruptions to Australian state impact levels (0-100)."""
    state = {"WA": 0, "QLD": 0, "NSW": 0, "NT": 0, "SA": 0, "VIC": 0, "TAS": 0}
    if "malacca" in disrupted_chokepoints or "lombok" in disrupted_chokepoints:
        state["WA"] = max(state["WA"], 90)
        state["QLD"] = max(state["QLD"], 60)
        state["NT"] = max(state["NT"], 50)
    if "hormuz" in disrupted_chokepoints:
        state["WA"] = max(state["WA"], 85)
        state["NT"] = max(state["NT"], 80)
        state["QLD"] = max(state["QLD"], 55)
    if "bab_el_mandeb" in disrupted_chokepoints or "suez" in disrupted_chokepoints:
        state["WA"] = max(state["WA"], 40)
        state["VIC"] = max(state["VIC"], 30)
        state["NSW"] = max(state["NSW"], 30)
    if "cape_good_hope" in disrupted_chokepoints:
        state["WA"] = max(state["WA"], 50)
        state["QLD"] = max(state["QLD"], 35)
    return state


def _consolidate_asx_signals(signals: dict) -> list:
    result = []
    for ticker, signal_list in signals.items():
        ups = sum(1 for s in signal_list if "UP" in s["direction"])
        downs = sum(1 for s in signal_list if "DOWN" in s["direction"])
        direction = "UP" if ups > downs else "DOWN" if downs > ups else "NEUTRAL"
        confidence = max(ups, downs) / len(signal_list) if signal_list else 0
        result.append({
            "ticker": ticker,
            "direction": direction,
            "confidence": round(confidence, 2),
            "signal_count": len(signal_list),
            "primary_reason": signal_list[0]["reason"][:100] if signal_list else "",
        })
    return sorted(result, key=lambda x: x["confidence"], reverse=True)


def _generate_simulation_seed(chokepoints: list, duration_days: int) -> str:
    from services.chokepoint_service import CHOKEPOINTS
    cp_names = [CHOKEPOINTS.get(cp, {}).get("name", cp) for cp in chokepoints]
    verb = "is" if len(chokepoints) == 1 else "are"
    return (
        f"Global maritime chokepoint disruption: {', '.join(cp_names)} {verb} disrupted "
        f"for an estimated {duration_days} days. This affects Australian resource and energy "
        f"export routes. Analyse the impact on ASX-listed resource, energy, and financial stocks "
        f"considering Australia's $383 billion annual resource export dependency."
    )


def _generate_key_insight(chokepoints: list) -> str:
    if "malacca" in chokepoints and "hormuz" in chokepoints:
        return "DUAL CRISIS: Malacca + Hormuz simultaneous disruption threatens 54% of global seaborne oil and ALL major Australian export routes simultaneously"
    if "malacca" in chokepoints:
        return "Malacca disruption threatens $288M AUD/day in Australian iron ore exports ? FMG most exposed as pure Pilbara-China play"
    if "hormuz" in chokepoints:
        return "Hormuz disruption triggers LNG price spike 20-50% ? Australian LNG becomes premium alternative supplier ? WDS and STO BULLISH"
    if "bab_el_mandeb" in chokepoints:
        return "Bab el-Mandeb/Red Sea disruption forces Cape reroute ? adds $1-2M per voyage to Australian LNG deliveries to Europe"
    if "lombok" in chokepoints:
        return "Lombok Strait disruption blocks Australia-China iron ore backup route ? adds 3-5 days when Malacca is also congested"
    return "Chokepoint disruption detected ? monitoring Australian export impact"
