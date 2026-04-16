# Documentation Rules (Market Oracle AI)

## Code Comments

Write comments explaining WHY, not WHAT. Add them for non-obvious logic only.

```python
# GOOD — explains the design decision
# bhp_price_at_prediction stores ANY ticker's price despite the name.
# This is a legacy column — don't rename without updating all query sites.
entry_price = prediction["bhp_price_at_prediction"]

# BAD — restates what the code already says
# Get the entry price
entry_price = prediction["bhp_price_at_prediction"]
```

## Docstrings (Public Functions Only)

```python
async def fetch_price_at_time(ticker: str, target_time: datetime) -> Optional[float]:
    """
    Fetch the ASX closing price on the first trading day at or after target_time.

    Args:
        ticker:      ASX ticker with .AX suffix (e.g. "BHP.AX")
        target_time: UTC datetime — snapped to next market open if outside hours

    Returns:
        Close price as float, or None if unavailable (warning logged).
    """
```

Internal/private functions don't need docstrings — a clear name is enough.

## CLAUDE.md Updates

Update `CLAUDE.md` when:
- Adding a new API endpoint (add to Key Files table or Endpoints section)
- Changing a core constant (confidence thresholds, MC settings, agent count)
- Adding a new environment variable
- Changing deployment process or branch strategy

## Memory Auto-Updates

After a change is verified working, update the appropriate memory file in
`~/.claude/projects/c--Users-HP-Market-Oracle-AI/memory/`:

| Change Type | Memory File | Format |
|-------------|-------------|--------|
| Core system change | `project_architecture_decisions.md` | `### [YYYY-MM-DD] Title` + What/Why/Impact |
| Bug requiring investigation | `project_bugs_fixed.md` | `### [YYYY-MM-DD] Title` + Symptom/Cause/Fix |
| New focus area | `project_current_focus.md` | Replace current entry |

Keep entries to 3-4 lines. Skip formatting changes, typos, or comment updates.

## Gotchas Files

Each skill has a `gotchas.md`. Add an entry when:
- A bug was caused by a misunderstood API, data format, or geographic fact
- A non-obvious rule was discovered (e.g. iron ore doesn't go through Malacca)
- A pattern repeatedly causes confusion

Format:
```markdown
### YYYY-MM-DD: Short Description
- **Bug/Discovery**: What happened
- **Why**: Root cause or non-obvious fact
- **Fix/Rule**: What to do instead
- **File**: Where the fix lives (if applicable)
```
