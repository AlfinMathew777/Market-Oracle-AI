"""Market Oracle AI - FastAPI Backend Server."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv
import logging
from pathlib import Path

# Import routes
from routes.data import router as data_router
from routes.simulate import router as simulate_router

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Market Oracle AI API",
    description="ASX prediction platform with 50-agent swarm intelligence",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(data_router)
app.include_router(simulate_router)

@app.get("/")
def root():
    return {
        "name": "Market Oracle AI API",
        "version": "1.0.0",
        "status": "operational",
        "endpoints": {
            "data": [
                "/api/data/acled",
                "/api/data/asx-prices",
                "/api/data/port-hedland"
            ],
            "simulation": [
                "/api/simulate"
            ]
        }
    }

@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "market-oracle-ai"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
