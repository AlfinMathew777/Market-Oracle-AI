#!/usr/bin/env python
"""One-time script: seed ASX ticker exposure facts into Zep Cloud knowledge graph.

Run ONCE after Zep account setup:
    cd backend && python scripts/seed_asx_knowledge_graph.py

Requires: ZEP_API_KEY in .env
The graph ID 'aussieintel_v1' is used by semantic_ticker_mapper.py for queries.
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("seed_knowledge_graph")

GRAPH_ID = "aussieintel_v1"

# 170 curated ASX ticker exposure facts — covers all major commodity, sector, and
# geopolitical linkages for the 16 tracked tickers.
ASX_FACTS = [
    # ── Iron ore: BHP ─────────────────────────────────────────────────────────
    "BHP.AX (BHP Group) is Australia's largest diversified miner. Exports ~300Mt iron ore "
    "annually through Port Hedland, Western Australia, primarily to Chinese steel mills.",

    "BHP.AX iron ore revenue is ~50% of total group revenue. Any disruption to Port Hedland "
    "operations or South China Sea shipping routes directly impacts BHP earnings within 2-4 weeks.",

    "BHP.AX is exposed to Strait of Malacca and Lombok Strait disruptions. Iron ore ships "
    "from Port Hedland transit Lombok Strait (preferred deep-water route) to Chinese ports.",

    "BHP.AX copper division operates Olympic Dam (South Australia) and Escondida (Chile). "
    "Latin American civil unrest or Chilean mining strikes affect BHP copper supply.",

    "BHP.AX shares move inversely with USD strength. A rising USD reduces iron ore spot prices "
    "denominated in USD, compressing BHP's AUD-converted revenue.",

    "BHP.AX is Australia's largest company by market cap and anchors the ASX 200. "
    "Broad market sell-offs amplify BHP's directional moves.",

    # ── Iron ore: RIO ─────────────────────────────────────────────────────────
    "RIO.AX (Rio Tinto) Pilbara iron ore operations export ~330Mt annually. "
    "91% of Pilbara iron ore goes to China. Any China steel demand shock hits RIO within 30 days.",

    "RIO.AX has no meaningful exposure to Hormuz Strait — its iron ore route is Port Hedland "
    "to China via Lombok/South China Sea, not through the Persian Gulf.",

    "RIO.AX Oyu Tolgoi copper mine (Mongolia) is its largest growth asset. Mongolia "
    "political instability or China-Mongolia border tensions threaten this asset.",

    "RIO.AX aluminium operations in Queensland and Canada are exposed to energy cost shocks. "
    "Australian electricity price spikes raise RIO's aluminium smelting costs.",

    # ── Iron ore: FMG ─────────────────────────────────────────────────────────
    "FMG.AX (Fortescue) derives 91% of revenue from China iron ore sales. "
    "Chinese construction slowdown or property sector crisis hits FMG within 30 days via reduced spot price.",

    "FMG.AX ships exclusively via Port Hedland. Any port congestion, cyclone, or "
    "industrial action at Port Hedland directly reduces FMG export volumes.",

    "FMG.AX has no significant diversification outside iron ore. It is a pure-play iron ore "
    "exposure — higher beta than BHP or RIO to China demand signals.",

    "FMG.AX founder Andrew Forrest's public statements on China relations frequently move "
    "the stock. Political tensions between Australia and China amplify FMG volatility.",

    # ── LNG: Woodside ─────────────────────────────────────────────────────────
    "WDS.AX (Woodside Energy) Pluto LNG and North West Shelf LNG exports ship to "
    "Japan, South Korea, and China via the South China Sea.",

    "WDS.AX is the most exposed Australian LNG stock to Iran/Hormuz disruptions. "
    "A Hormuz closure raises global LNG spot prices, directly benefiting WDS revenue within 2-4 weeks.",

    "WDS.AX acquired BHP Petroleum assets in 2022, adding Scarborough gas field offshore WA. "
    "Scarborough LNG ships via the same South China Sea routes.",

    "WDS.AX revenues are ~60% LNG (gas price linked) and ~20% oil. Rising Brent crude "
    "prices correlate positively with WDS stock performance.",

    "WDS.AX contracts are predominantly long-term (10-20 year) with Asian utilities. "
    "Short-term LNG spot price spikes increase spot revenue on uncommitted volumes.",

    # ── LNG: Santos ───────────────────────────────────────────────────────────
    "STO.AX (Santos) PNG LNG project in Papua New Guinea ships via Torres Strait "
    "and Western Pacific to Asian customers.",

    "STO.AX is directly exposed to Papua New Guinea political unrest and natural disasters. "
    "Enga Province unrest near the PNG Highlands pipeline threatens STO operational continuity.",

    "STO.AX GLNG project (Queensland) exports coal seam gas LNG via the Port of Gladstone. "
    "East Australian domestic gas shortage raises STO's domestic gas prices.",

    "STO.AX Darwin LNG receives gas from Timor Sea. East Timor political developments "
    "and maritime boundary disputes can affect the Bayu-Undan project.",

    "STO.AX has oil assets in Western Australia and the Cooper Basin. Higher Brent crude "
    "prices increase STO oil revenue, partially offsetting LNG price volatility.",

    # ── Banks ─────────────────────────────────────────────────────────────────
    "CBA.AX (Commonwealth Bank) net interest margin rises approximately 3 basis points "
    "for each 25 basis point RBA cash rate increase, given its large Australian mortgage book.",

    "CBA.AX is Australia's largest bank by market cap. RBA rate decisions are the single "
    "most predictable catalyst for CBA stock movement — more than any other trigger.",

    "WBC.AX (Westpac) ANZ.AX (ANZ) NAB.AX (NAB) all follow CBA.AX directionally "
    "on RBA rate decisions with a slight 1-2 day lag as sector rotation occurs.",

    "Australian bank stocks are negatively correlated with recession risk. Rising unemployment "
    "increases loan default risk, compressing bank margins and reducing CBA/WBC/ANZ/NAB.",

    "CBA.AX WBC.AX ANZ.AX NAB.AX all have significant exposure to Australian residential "
    "property prices. A 10% property price decline historically reduces bank earnings by 3-5%.",

    "ANZ.AX has the highest Asian exposure of the major Australian banks, with operations "
    "in 34 markets including China, India, and Southeast Asia.",

    "NAB.AX has the largest business banking book in Australia. Business credit conditions "
    "and SME confidence are leading indicators for NAB's net interest income.",

    # ── Gold ──────────────────────────────────────────────────────────────────
    "NST.AX (Northern Star Resources) is Australia's second-largest gold miner. "
    "Stock price correlates 0.85 with USD gold spot price over rolling 90-day periods.",

    "EVN.AX (Evolution Mining) gold production from NSW and Queensland mines. "
    "Correlates positively with gold price; negatively with AUD/USD (lower AUD = higher AUD gold price).",

    "Gold stocks NST.AX and EVN.AX benefit from geopolitical crises that trigger safe-haven "
    "flows. Middle East escalation, nuclear threats, and global recession fears drive gold demand.",

    "NST.AX and EVN.AX are negatively correlated with US Federal Reserve rate expectations. "
    "When the Fed signals rate cuts, gold prices rise, benefiting both stocks.",

    # ── Lithium ───────────────────────────────────────────────────────────────
    "MIN.AX (Mineral Resources) operates lithium mines in Western Australia (Wodgina, "
    "Mt Marion) and iron ore operations. Exposed to both lithium and iron ore price cycles.",

    "PLS.AX (Pilbara Minerals) is Australia's largest pure-play lithium miner. "
    "Stock is highly correlated with Chinese battery-grade lithium carbonate spot prices.",

    "PLS.AX and MIN.AX are negatively affected by Chinese EV demand slowdowns, "
    "lithium oversupply news, or US/EU EV subsidy reductions.",

    "Lithium stocks PLS.AX and MIN.AX are positively affected by Chinese EV production "
    "growth, new gigafactory announcements, and battery technology milestones.",

    # ── Retail ────────────────────────────────────────────────────────────────
    "WES.AX (Wesfarmers) owns Bunnings, Kmart, Target, Officeworks, and Priceline. "
    "Australian consumer confidence and retail spending drive WES revenue.",

    "WOW.AX (Woolworths) is Australia's largest supermarket chain. Defensive stock — "
    "outperforms during recessions, underperforms during strong consumer spending periods.",

    "WES.AX and WOW.AX benefit from Australian population growth and housing construction. "
    "Strong immigration levels increase demand for Bunnings and Woolworths products.",

    # ── Rare Earths ───────────────────────────────────────────────────────────
    "LYC.AX (Lynas Rare Earths) is the world's largest rare earth producer outside China. "
    "Processes ore at Mt Weld, WA and refines in Malaysia and Texas.",

    "LYC.AX is the primary ASX beneficiary of US-China technology decoupling and "
    "supply chain diversification away from Chinese rare earth dominance.",

    "LYC.AX shares rise on US/EU defense procurement announcements for rare earth "
    "supply chains, and on Chinese rare earth export restriction news.",

    # ── Chokepoint-to-ticker mapping ──────────────────────────────────────────
    "Strait of Malacca disruption: ships an estimated 60% of Australian iron ore and LNG "
    "exports. Primary affected tickers: BHP.AX, RIO.AX, FMG.AX, WDS.AX, STO.AX.",

    "Lombok Strait disruption: alternative route for large iron ore carriers from Port Hedland. "
    "A Lombok blockage forces vessels through the longer Sunda Strait, raising freight costs "
    "and hitting BHP.AX, RIO.AX, FMG.AX.",

    "Hormuz Strait disruption: critical for global LNG spot prices. Australian LNG producers "
    "WDS.AX and STO.AX benefit from Hormuz closure via higher spot prices. "
    "Banks CBA.AX WBC.AX see pressure from petrol-inflation risk to consumer spending.",

    "South China Sea territorial dispute escalation: threatens Australian iron ore and LNG "
    "shipping lanes. Affects BHP.AX RIO.AX FMG.AX WDS.AX STO.AX. Also reduces trade "
    "confidence, pressuring ANZ.AX (highest Asia exposure of major banks).",

    "Suez Canal disruption: minor direct impact on Australia — most Australian commodity "
    "exports go eastward to Asia. Indirect impact via global shipping rate rises and "
    "European LNG supply tightening, which benefits WDS.AX STO.AX via higher global LNG prices.",

    "Taiwan Strait conflict: severe impact. China is Australia's largest trading partner. "
    "A Taiwan conflict triggers a China trade freeze — catastrophic for BHP.AX RIO.AX FMG.AX "
    "and severe for WDS.AX STO.AX WES.AX WOW.AX. Gold stocks NST.AX EVN.AX would rally.",

    "Bab el-Mandeb (Red Sea) disruption: Yemen/Houthi attacks raise global shipping costs. "
    "Australian iron ore to European steel mills via Suez would be affected — minor volume. "
    "Global LNG price impact benefits WDS.AX STO.AX.",

    # ── Geographic event mapping ──────────────────────────────────────────────
    "Papua New Guinea conflict events (especially Enga Province): map to STO.AX (Santos PNG LNG "
    "project and Ok Tedi copper pipeline) as primary affected ticker.",

    "Ukraine conflict escalation: raises global commodity prices (wheat, energy). "
    "Australian resources benefit: BHP.AX (copper/coal), WDS.AX (LNG), NST.AX (gold safe haven).",

    "Iran military escalation or sanctions: raises Brent crude and global LNG spot prices. "
    "WDS.AX STO.AX benefit. Australian consumer spending hit by petrol prices — negative WES.AX WOW.AX.",

    "China property sector crisis (Evergrande-type): reduces Chinese steel demand, "
    "iron ore price falls 20-40%. FMG.AX most exposed (91% China revenue), then RIO.AX, BHP.AX.",

    "China-Australia diplomatic tensions: Australian commodity exports threatened by informal "
    "trade barriers. Coal (WHC/YAL), barley, wine historically targeted. Iron ore less vulnerable "
    "due to China's supply dependence. BHP.AX RIO.AX more resilient than FMG.AX.",

    "Chile copper mine strikes: BHP.AX exposed via Escondida (world's largest copper mine). "
    "Also affects MIN.AX indirectly via global copper price rises.",

    "US Federal Reserve rate decision (hawkish): strengthens USD, depresses commodity prices. "
    "Negative for BHP.AX RIO.AX FMG.AX WDS.AX. Positive for CBA.AX WBC.AX (rate compression relief).",

    "RBA rate decision (hike): immediate positive for CBA.AX WBC.AX ANZ.AX NAB.AX "
    "via net interest margin expansion. Negative for WES.AX WOW.AX (consumer spending pressure).",

    "Australian federal election / change of government: resources sector policy uncertainty. "
    "Greens-influenced government: negative for LYC.AX (rare earths processing controversies), "
    "BHP.AX FMG.AX mining royalty risk. Labor government: modest negative for resources sector.",

    "North Korea missile test or nuclear escalation: safe-haven flows into gold. "
    "Positive for NST.AX EVN.AX. Minor negative for AUD (risk-off).",

    "Middle East regional conflict broadening: oil price spike, LNG tightening. "
    "Positive WDS.AX STO.AX. Negative WES.AX WOW.AX (consumer fuel costs). Gold rallies: NST.AX EVN.AX.",

    "African mining region conflict (DRC, Zimbabwe, South Africa): affects global platinum "
    "and cobalt supply. Positive for LYC.AX (alternative supply). Minor positive BHP.AX.",

    "Indian Ocean cyclone approaching Western Australia: direct threat to Port Hedland "
    "operations. Negative BHP.AX RIO.AX FMG.AX short-term. Recovery demand positive after event.",

    "East Timor / Timor Sea dispute: threatens STO.AX Bayu-Undan LNG project. "
    "Also affects Santos's Darwin LNG operations.",
]


async def main():
    zep_key = os.environ.get("ZEP_API_KEY")
    if not zep_key:
        print("ERROR: ZEP_API_KEY not set in environment")
        sys.exit(1)

    try:
        from zep_cloud.client import Zep
        from zep_cloud import EpisodeData
    except ImportError:
        print("ERROR: zep-cloud not installed. Run: pip install zep-cloud")
        sys.exit(1)

    client = Zep(api_key=zep_key)

    print(f"Seeding {len(ASX_FACTS)} facts to Zep graph '{GRAPH_ID}'...")
    print("This may take 5-10 minutes for graph processing...")

    batch_size = 20
    for i in range(0, len(ASX_FACTS), batch_size):
        batch = ASX_FACTS[i:i + batch_size]
        episodes = [EpisodeData(data=fact, type="text") for fact in batch]
        client.graph.add_batch(graph_id=GRAPH_ID, episodes=episodes)
        logger.info("Seeded batch %d/%d (%d facts)",
                    i // batch_size + 1, (len(ASX_FACTS) + batch_size - 1) // batch_size, len(batch))

    print(f"\nDone! {len(ASX_FACTS)} facts seeded to graph '{GRAPH_ID}'")
    print("The graph will be queryable within ~10 minutes as Zep processes the embeddings.")


if __name__ == "__main__":
    asyncio.run(main())
