"""
pytest configuration for Market Oracle AI backend tests.
"""
import sys
import os

# Add backend root so `from services.xxx import ...` resolves correctly
# (same path the app uses at runtime)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
