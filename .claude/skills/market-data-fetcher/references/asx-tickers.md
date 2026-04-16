# Supported ASX Tickers

## Primary Focus — Top 20 by Market Cap

| Ticker | Company | Sector | Chokepoint Sensitivity |
|--------|---------|--------|------------------------|
| BHP.AX | BHP Group | Mining | Lombok (primary), Suez (secondary) |
| CBA.AX | Commonwealth Bank | Banking | None direct — import inflation via Malacca |
| CSL.AX | CSL Limited | Healthcare | Low |
| NAB.AX | National Australia Bank | Banking | Low |
| WBC.AX | Westpac | Banking | Low |
| ANZ.AX | ANZ Bank | Banking | Low |
| WES.AX | Wesfarmers | Retail/Mining | Low |
| MQG.AX | Macquarie Group | Finance | Low |
| RIO.AX | Rio Tinto | Mining | Lombok (primary), Suez (secondary) |
| FMG.AX | Fortescue Metals | Mining | Lombok (primary) |
| WOW.AX | Woolworths | Retail | Low |
| TLS.AX | Telstra | Telecom | Low |
| WDS.AX | Woodside Energy | Energy | Lombok+Suez (LNG), Malacca (bullish — competitor) |
| GMG.AX | Goodman Group | Real Estate | Low |
| ALL.AX | Aristocrat Leisure | Gaming | Low |
| REA.AX | REA Group | Tech/Property | Low |
| TCL.AX | Transurban | Infrastructure | Low |
| STO.AX | Santos | Energy | Lombok+Suez (LNG), Malacca (bullish — competitor) |
| COL.AX | Coles Group | Retail | Low |
| AMC.AX | Amcor | Materials | Low |

## Sector Causal Chain Mapping

### Mining (BHP, RIO, FMG)
- Iron ore price ↑ → Bullish
- China PMI ↑ → Bullish
- AUD/USD ↑ → Bearish (exports less competitive in USD terms)
- Lombok/Makassar disruption → Bearish (iron ore blocked)
- Malacca disruption → **NEUTRAL** (iron ore doesn't transit Malacca)
- Suez disruption → Bearish secondary (LNG competitors affected)

### Banking (CBA, NAB, WBC, ANZ, MQG)
- Interest rates ↑ → Mixed (margin ↑ vs defaults ↑)
- Housing prices ↑ → Bullish
- Unemployment ↓ → Bullish
- Import inflation (Malacca disruption) → Bearish (consumer spending ↓)

### Energy (WDS, STO)
- Oil price ↑ → Bullish
- LNG demand ↑ → Bullish
- Malacca disruption → **Bullish** (Qatar LNG competitor disrupted)
- Lombok/Suez disruption → Mixed (own exports affected)

## FRED Series for Key Macro Indicators

| Indicator | FRED Series | Notes |
|-----------|-------------|-------|
| Iron Ore Price | PIORECRUSDM | Monthly, delayed |
| AUD/USD | DEXUSAL | Daily |
| Australia Interest Rate | INTDSRTRM193N | Monthly |
| Brent Crude | DCOILBRENTEU | Daily |
| China PMI | — | Use caution: not on FRED |
