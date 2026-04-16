Generate a comprehensive daily accuracy and system health report.

## Usage
```
/daily-report
/daily-report --days 7
```

## Report Sections

### 1. System Health
- Kill switch status (ON/OFF)
- Paper mode status
- Data feed freshness (yfinance, FRED, news)
- Active alert count and severity

### 2. Prediction Summary (Last N Days)
- Total signals generated
- Validated vs pending
- Hit rate (excluding neutral)
- Signal volume trend

### 3. Accuracy Breakdown
- Overall hit rate
- By confidence band (55-65%, 65-75%, 75-85%, 85%+)
- By direction (BULLISH vs BEARISH)
- By ticker (top 5 most predicted)

### 4. Alerts & Issues
- All active (unacknowledged) alerts
- Alert type and severity
- Recommended actions

## API Calls Used
```bash
curl http://localhost:8000/api/admin/status
curl http://localhost:8000/api/health/data-feeds
curl "http://localhost:8000/api/metrics/validation-summary?days=$DAYS"
curl "http://localhost:8000/api/alerts?status=active"
```

## Output
Report is printed to console and saved to `reports/daily-{YYYY-MM-DD}.md`
