"""
FastAPI response pattern examples for Market Oracle AI.

These are reference snippets — not meant to be imported.
"""

# ── Standard success/error responses ──────────────────────────────────────────

def success_response(data, message: str = ""):
    return {"status": "success", "data": data, **({"message": message} if message else {})}

def error_response(message: str, code: int = 400):
    from fastapi import HTTPException
    raise HTTPException(status_code=code, detail=message)

# ── Async DB helper ────────────────────────────────────────────────────────────

async def safe_db_query(query, params=()):
    """Template for safe async DB queries with row_factory."""
    from database import get_db, init_db
    await init_db()
    try:
        async with get_db() as db:
            db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
            async with db.execute(query, params) as cur:
                return await cur.fetchall()
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("DB query failed: %s", e)
        return []

# ── Admin endpoint template ────────────────────────────────────────────────────

"""
@router.post("/api/admin/new-action")
async def new_admin_action(request: Request, body: NewActionRequest):
    from server import require_api_key
    require_api_key(request)

    result = await service_function(body.param)
    return {
        "status": "success",
        "result": result,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
"""
