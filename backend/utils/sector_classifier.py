"""
Sector Classifier for ASX Stocks
---------------------------------
Maps tickers to their economic sector and provides signal routing — which
market signals are relevant (and which should be excluded) for each stock.

Used by the Reasoning Synthesizer to:
  1. Select the appropriate sector system prompt
  2. Filter irrelevant signals before passing them to the LLM
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class SectorConfig:
    sector: str
    subsector: str
    cost_drivers: List[str]
    revenue_drivers: List[str]
    demand_indicators: List[str]
    sentiment_indicators: List[str]
    irrelevant_signal_keywords: List[str] = field(default_factory=list)
    """Lower-case keywords that, if found in a market-signal key, flag the signal as irrelevant."""


# ── ASX ticker → sector config ─────────────────────────────────────────────────

_SECTORS: Dict[str, SectorConfig] = {

    # ── Iron ore / diversified miners ───────────────────────────────────────
    "BHP.AX": SectorConfig(
        sector="Materials",
        subsector="Diversified Metals & Mining",
        cost_drivers=["diesel", "freight", "labour", "electricity", "explosives"],
        revenue_drivers=["iron_ore_price", "copper_price", "aud_usd", "production_volume"],
        demand_indicators=["china_pmi", "steel_production", "property_starts", "infrastructure_spend"],
        sentiment_indicators=["iron_ore_futures", "bdi", "china_port_inventory"],
        irrelevant_signal_keywords=["nim", "mortgage", "credit_growth", "rba_cash_rate",
                                    "housing_turnover", "consumer_confidence", "plasma"],
    ),
    "RIO.AX": SectorConfig(
        sector="Materials",
        subsector="Diversified Metals & Mining",
        cost_drivers=["diesel", "freight", "labour", "electricity", "bauxite"],
        revenue_drivers=["iron_ore_price", "aluminium_price", "copper_price", "aud_usd"],
        demand_indicators=["china_pmi", "steel_production", "ev_demand", "property_starts"],
        sentiment_indicators=["iron_ore_futures", "aluminium_futures", "china_port_inventory"],
        irrelevant_signal_keywords=["nim", "mortgage", "credit_growth", "rba_cash_rate", "plasma"],
    ),
    "FMG.AX": SectorConfig(
        sector="Materials",
        subsector="Iron Ore Mining",
        cost_drivers=["diesel", "freight", "labour", "rail_costs"],
        revenue_drivers=["iron_ore_price", "grade_premium", "aud_usd", "shipment_volume"],
        demand_indicators=["china_pmi", "steel_production", "blast_furnace_utilisation"],
        sentiment_indicators=["iron_ore_futures", "china_port_inventory", "spot_vs_contract"],
        irrelevant_signal_keywords=["nim", "mortgage", "credit_growth", "rba_cash_rate", "plasma"],
    ),
    "MIN.AX": SectorConfig(
        sector="Materials",
        subsector="Diversified Mining Services",
        cost_drivers=["diesel", "freight", "labour", "lithium_royalties"],
        revenue_drivers=["iron_ore_price", "lithium_price", "spodumene_price", "aud_usd"],
        demand_indicators=["china_pmi", "ev_demand", "battery_demand", "steel_production"],
        sentiment_indicators=["lithium_futures", "iron_ore_futures", "ev_sentiment"],
        irrelevant_signal_keywords=["nim", "mortgage", "credit_growth", "rba_cash_rate"],
    ),

    # ── Rare Earths & Critical Minerals ──────────────────────────────────────
    "LYC.AX": SectorConfig(
        sector="Rare Earths",
        subsector="Rare Earths & Critical Minerals",
        cost_drivers=["processing_energy", "labour_wa_malaysia", "logistics_concentrate",
                      "regulatory_compliance", "maintenance_kalgoorlie", "maintenance_kuantan"],
        revenue_drivers=["ndpr_oxide_price", "dysprosium_price", "terbium_price",
                         "aud_usd", "production_volume", "offtake_contracts"],
        demand_indicators=["ev_motor_production", "wind_turbine_orders", "defence_procurement",
                           "china_export_quotas", "magnet_manufacturing"],
        sentiment_indicators=["rare_earth_index", "china_supply_chain_news",
                              "us_critical_minerals_policy", "eu_critical_raw_materials_act"],
        irrelevant_signal_keywords=["iron_ore", "copper", "coal", "steel_production",
                                    "property_starts", "nim", "mortgage", "credit_growth",
                                    "rba_cash_rate", "china_pmi"],
    ),
    "ILU.AX": SectorConfig(
        sector="Rare Earths",
        subsector="Mineral Sands & Critical Minerals",
        cost_drivers=["mining_costs", "energy", "labour", "rehabilitation"],
        revenue_drivers=["zircon_price", "rutile_price", "synthetic_rutile_price",
                         "rare_earth_credits", "aud_usd"],
        demand_indicators=["ceramics_demand", "titanium_pigment_demand",
                           "aerospace_titanium", "construction_activity"],
        sentiment_indicators=["mineral_sands_index", "china_ceramics_production"],
        irrelevant_signal_keywords=["iron_ore", "copper", "coal", "steel_production",
                                    "nim", "mortgage", "credit_growth", "rba_cash_rate"],
    ),

    # ── Lithium ───────────────────────────────────────────────────────────────
    "PLS.AX": SectorConfig(
        sector="Lithium",
        subsector="Lithium Mining",
        cost_drivers=["mining_costs", "diesel", "labour", "shipping_to_china"],
        revenue_drivers=["spodumene_price", "lithium_hydroxide", "aud_usd", "offtake_volumes"],
        demand_indicators=["ev_sales_global", "battery_cell_production",
                           "china_lithium_inventory", "us_ira_battery_demand"],
        sentiment_indicators=["lithium_carbonate_futures", "ev_adoption_forecasts",
                              "battery_technology_news"],
        irrelevant_signal_keywords=["iron_ore", "copper", "coal", "steel_production",
                                    "nim", "mortgage", "credit_growth", "rba_cash_rate"],
    ),
    "IGO.AX": SectorConfig(
        sector="Lithium",
        subsector="Lithium & Nickel",
        cost_drivers=["energy", "labour", "processing_costs"],
        revenue_drivers=["lithium_hydroxide_price", "nickel_sulphate_price",
                         "cobalt_credits", "aud_usd"],
        demand_indicators=["ev_battery_chemistry", "battery_cell_production",
                           "energy_storage_demand"],
        sentiment_indicators=["battery_metals_index", "ev_adoption_rates"],
        irrelevant_signal_keywords=["iron_ore", "coal", "steel_production",
                                    "nim", "mortgage", "credit_growth", "rba_cash_rate"],
    ),
    "SYR.AX": SectorConfig(
        sector="Lithium",
        subsector="Graphite",
        cost_drivers=["mining_costs", "processing", "logistics", "energy"],
        revenue_drivers=["natural_graphite_price", "spherical_graphite_premium",
                         "battery_anode_contracts", "aud_usd"],
        demand_indicators=["ev_battery_production", "anode_material_demand",
                           "china_graphite_export_controls"],
        sentiment_indicators=["graphite_index", "battery_supply_chain_news"],
        irrelevant_signal_keywords=["iron_ore", "copper", "coal", "steel_production",
                                    "nim", "mortgage", "credit_growth", "rba_cash_rate"],
    ),

    # ── Energy ──────────────────────────────────────────────────────────────
    "WDS.AX": SectorConfig(
        sector="Energy",
        subsector="Oil & Gas",
        cost_drivers=["operating_cost", "lng_freight", "royalties", "maintenance"],
        revenue_drivers=["lng_price", "oil_price", "jkm_spot", "aud_usd"],
        demand_indicators=["asian_lng_demand", "china_gas_imports", "japan_lng", "korea_lng"],
        sentiment_indicators=["jkm_futures", "brent_futures", "carbon_price"],
        irrelevant_signal_keywords=["nim", "mortgage", "credit_growth", "plasma", "iron_ore_62fe"],
    ),
    "STO.AX": SectorConfig(
        sector="Energy",
        subsector="Oil & Gas",
        cost_drivers=["operating_cost", "lng_freight", "royalties", "capex"],
        revenue_drivers=["lng_price", "oil_price", "aud_usd", "production_volume"],
        demand_indicators=["asian_lng_demand", "china_gas_imports", "power_demand"],
        sentiment_indicators=["jkm_futures", "brent_futures", "carbon_price"],
        irrelevant_signal_keywords=["nim", "mortgage", "credit_growth", "plasma", "iron_ore_62fe"],
    ),

    # ── Major banks ─────────────────────────────────────────────────────────
    "CBA.AX": SectorConfig(
        sector="Financials",
        subsector="Major Banks",
        cost_drivers=["funding_costs", "compliance", "technology", "wages", "bad_debts"],
        revenue_drivers=["net_interest_margin", "loan_growth", "fee_income", "wealth_management"],
        demand_indicators=["mortgage_applications", "business_lending", "housing_turnover"],
        sentiment_indicators=["rba_rate_expectations", "yield_curve", "housing_sentiment"],
        irrelevant_signal_keywords=["iron_ore", "copper", "china_pmi", "freight",
                                    "diesel", "aluminium", "plasma", "lng"],
    ),
    "NAB.AX": SectorConfig(
        sector="Financials",
        subsector="Major Banks",
        cost_drivers=["funding_costs", "compliance", "technology", "wages", "bad_debts"],
        revenue_drivers=["net_interest_margin", "business_loan_growth", "fee_income", "markets_revenue"],
        demand_indicators=["business_credit", "sme_lending", "commercial_property"],
        sentiment_indicators=["rba_rate_expectations", "yield_curve", "business_confidence"],
        irrelevant_signal_keywords=["iron_ore", "copper", "china_pmi", "freight",
                                    "diesel", "aluminium", "plasma", "lng"],
    ),
    "WBC.AX": SectorConfig(
        sector="Financials",
        subsector="Major Banks",
        cost_drivers=["funding_costs", "compliance", "technology", "wages", "bad_debts"],
        revenue_drivers=["net_interest_margin", "mortgage_growth", "fee_income", "nz_operations"],
        demand_indicators=["mortgage_applications", "housing_turnover", "consumer_lending"],
        sentiment_indicators=["rba_rate_expectations", "yield_curve", "housing_sentiment"],
        irrelevant_signal_keywords=["iron_ore", "copper", "china_pmi", "freight",
                                    "diesel", "aluminium", "plasma"],
    ),
    "ANZ.AX": SectorConfig(
        sector="Financials",
        subsector="Major Banks",
        cost_drivers=["funding_costs", "compliance", "technology", "wages", "bad_debts"],
        revenue_drivers=["net_interest_margin", "institutional_revenue", "markets_trading"],
        demand_indicators=["institutional_lending", "trade_finance", "fx_volumes"],
        sentiment_indicators=["rba_rate_expectations", "yield_curve", "credit_spreads"],
        irrelevant_signal_keywords=["iron_ore", "copper", "china_pmi", "freight",
                                    "diesel", "aluminium", "plasma"],
    ),

    # ── Healthcare ───────────────────────────────────────────────────────────
    "CSL.AX": SectorConfig(
        sector="Healthcare",
        subsector="Biotechnology",
        cost_drivers=["plasma_collection", "r&d_spend", "manufacturing", "regulatory"],
        revenue_drivers=["immunoglobulin_demand", "vaccine_sales", "aud_usd"],
        demand_indicators=["plasma_demand", "flu_severity", "aging_population"],
        sentiment_indicators=["fda_approvals", "competitor_pipeline", "biotech_sentiment"],
        irrelevant_signal_keywords=["iron_ore", "interest_rates", "china_pmi", "mortgage",
                                    "freight", "diesel", "lng"],
    ),

    # ── Consumer staples ─────────────────────────────────────────────────────
    "WOW.AX": SectorConfig(
        sector="Consumer Staples",
        subsector="Food Retail",
        cost_drivers=["wages", "supply_chain", "rent", "energy", "shrinkage"],
        revenue_drivers=["same_store_sales", "basket_size", "foot_traffic"],
        demand_indicators=["consumer_confidence", "retail_sales", "food_inflation"],
        sentiment_indicators=["consumer_sentiment", "competitor_pricing"],
        irrelevant_signal_keywords=["iron_ore", "china_pmi", "nim", "mortgage", "freight"],
    ),
    "COL.AX": SectorConfig(
        sector="Consumer Staples",
        subsector="Food Retail",
        cost_drivers=["wages", "supply_chain", "rent", "energy"],
        revenue_drivers=["same_store_sales", "liquor_growth", "convenience_format"],
        demand_indicators=["consumer_confidence", "retail_sales", "food_inflation"],
        sentiment_indicators=["consumer_sentiment", "competitor_pricing"],
        irrelevant_signal_keywords=["iron_ore", "china_pmi", "nim", "mortgage", "freight"],
    ),

    # ── Technology ───────────────────────────────────────────────────────────
    "XRO.AX": SectorConfig(
        sector="Technology",
        subsector="Software / SaaS",
        cost_drivers=["engineering", "sales_marketing", "cloud_infrastructure"],
        revenue_drivers=["subscription_revenue", "arpu", "churn", "geographic_expansion"],
        demand_indicators=["smb_formation", "digital_adoption"],
        sentiment_indicators=["saas_multiples", "tech_sentiment", "aud_gbp"],
        irrelevant_signal_keywords=["iron_ore", "china_pmi", "mortgage", "nim",
                                    "diesel", "freight", "lng"],
    ),

    # ── Industrial REITs ─────────────────────────────────────────────────────
    "GMG.AX": SectorConfig(
        sector="Real Estate",
        subsector="Industrial REITs",
        cost_drivers=["construction_costs", "interest_expense", "property_taxes"],
        revenue_drivers=["rental_income", "occupancy", "development_profits"],
        demand_indicators=["warehouse_demand", "ecommerce_penetration"],
        sentiment_indicators=["cap_rate_expectations", "bond_yields", "industrial_vacancy"],
        irrelevant_signal_keywords=["iron_ore", "china_pmi", "nim", "plasma",
                                    "diesel", "freight"],
    ),
}


# ── Public API ─────────────────────────────────────────────────────────────────

def get_sector_config(ticker: str) -> Optional[SectorConfig]:
    return _SECTORS.get(ticker.upper())


def get_sector(ticker: str) -> str:
    cfg = get_sector_config(ticker)
    return cfg.sector if cfg else "General"


def filter_signals_for_sector(
    ticker: str, signals: Dict[str, object]
) -> Dict[str, object]:
    """
    Remove market signals that are irrelevant for the stock's sector.

    E.g., iron_ore_62fe is dropped for CBA.AX; nim is dropped for BHP.AX.
    Unknown tickers pass all signals through unchanged.
    """
    cfg = get_sector_config(ticker)
    if not cfg:
        return signals

    filtered: Dict[str, object] = {}
    for key, value in signals.items():
        key_lower = key.lower()
        if any(kw in key_lower for kw in cfg.irrelevant_signal_keywords):
            continue
        filtered[key] = value

    return filtered
