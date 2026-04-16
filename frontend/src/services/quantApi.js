/**
 * Quant Engine API service — Market Oracle AI
 *
 * Follows the exact same fetch() pattern used in App.js:
 * - REACT_APP_BACKEND_URL env var for base URL
 * - fetch() directly (no axios)
 * - Returns { status, data } on success or { status: 'error', detail } on failure
 * - All calls wrapped in try/catch
 */

const BACKEND_URL = "http://localhost:8000";

/**
 * Full quantitative analysis for a ticker.
 * Includes vol model, factor exposures, MC paths, and risk metrics.
 * @param {string} ticker  e.g. "BHP.AX"
 * @returns {Promise<{status: string, data?: object, detail?: string}>}
 */
export async function fetchQuantAnalysis(ticker) {
  try {
    const res = await fetch(
      `${BACKEND_URL}/api/quant/analyse/${encodeURIComponent(ticker)}`,
    );
    if (!res.ok) {
      let detail = "Quant analysis failed";
      try {
        detail = (await res.json()).detail || detail;
      } catch (_) {}
      return { status: "error", detail };
    }
    return await res.json();
  } catch (err) {
    return { status: "error", detail: err.message || "Network error" };
  }
}

/**
 * Monte Carlo simulation data — the primary feed for MonteCarloEngine.jsx.
 * Returns percentile price paths + tail probabilities + risk metrics.
 * @param {string} ticker        e.g. "BHP.AX"
 * @param {number} horizonDays   5–90 (default 30)
 * @param {number} nSimulations  1000–10000 (default 5000)
 * @returns {Promise<{status: string, data?: object, detail?: string}>}
 */
export async function fetchMonteCarlo(
  ticker,
  horizonDays = 30,
  nSimulations = 5000,
) {
  try {
    const params = new URLSearchParams({
      horizon_days: horizonDays,
      n_simulations: nSimulations,
    });
    const res = await fetch(
      `${BACKEND_URL}/api/quant/monte-carlo/${encodeURIComponent(ticker)}?${params}`,
    );
    if (!res.ok) {
      let detail = "Monte Carlo fetch failed";
      try {
        detail = (await res.json()).detail || detail;
      } catch (_) {}
      return { status: "error", detail };
    }
    return await res.json();
  } catch (err) {
    return { status: "error", detail: err.message || "Network error" };
  }
}

/**
 * Lightweight quant prediction — direction + confidence only.
 * Faster than fetchQuantAnalysis (2 000 simulations instead of 5 000).
 * @param {string} ticker  e.g. "BHP.AX"
 * @returns {Promise<{status: string, data?: object, detail?: string}>}
 */
export async function fetchPrediction(ticker) {
  try {
    const res = await fetch(
      `${BACKEND_URL}/api/quant/prediction/${encodeURIComponent(ticker)}`,
    );
    if (!res.ok) {
      let detail = "Quant prediction failed";
      try {
        detail = (await res.json()).detail || detail;
      } catch (_) {}
      return { status: "error", detail };
    }
    return await res.json();
  } catch (err) {
    return { status: "error", detail: err.message || "Network error" };
  }
}
