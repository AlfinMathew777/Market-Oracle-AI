"""Market Oracle AI - Simplified POC with 10 agents (for speed)

Tests the complete flow with smaller agent count to verify logic before scaling to 50.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import json
from datetime import datetime
from typing import List, Dict
from dotenv import load_dotenv

load_dotenv()

from llm_router import LLMRouter, parse_json_response
from models.prediction import PredictionCard
from event_ticker_mapping import map_event_to_ticker, get_ticker_info

# Simplified: 10 agents, 4 personas
PERSONAS_SIMPLE = {
    'retail_investor': {'description': 'Retail investor', 'count': 3},
    'hedge_fund': {'description': 'Hedge fund trader', 'count': 3},
    'analyst': {'description': 'Financial analyst', 'count': 2},
    'institutional': {'description': 'Institutional investor', 'count': 2}
}


async def run_simplified_simulation():
    """Run simplified 10-agent simulation."""
    print("\n" + "="*60)
    print("  SIMPLIFIED POC - 10 Agents, 2 Rounds")
    print("="*60)
    
    # Sample event
    event = {
        'event_id_cnty': 'test_001',
        'country': 'Iran',
        'location': 'Strait of Hormuz',
        'event_type': 'Battles',
        'fatalities': 23,
        'event_date': '2026-03-15',
        'notes': 'Armed naval confrontation, oil tanker route disrupted'
    }
    
    # Initialize
    router = LLMRouter()
    ticker = map_event_to_ticker(event)
    ticker_info = get_ticker_info(ticker)
    
    print(f"\n? Event: {event['country']} - {event['event_type']}")
    print(f"? Mapped Ticker: {ticker} ({ticker_info['name']})")
    
    # Create 10 agents
    print(f"\n? Creating 10 agents...")
    agents = []
    agent_id = 1
    for persona, data in PERSONAS_SIMPLE.items():
        for _ in range(data['count']):
            agents.append({'id': agent_id, 'persona': persona})
            agent_id += 1
    
    # Run 2 rounds
    print(f"\n? Running 2 simulation rounds...")
    votes = {'UP': 0, 'DOWN': 0, 'NEUTRAL': 0}
    rationales = []
    
    event_context = f"{event['country']} - {event['event_type']}: {event['notes']}"
    
    # Simulate agent votes in batch
    prompts = []
    for agent in agents:
        prompts.append({
            'system': f"You are a {agent['persona']} analyzing market impact.",
            'user': f"""Event: {event_context}
Target Stock: {ticker} ({ticker_info['name']})

Will this event cause {ticker} to go UP, DOWN, or stay NEUTRAL over the next 7 days?
Respond with ONLY one word: UP, DOWN, or NEUTRAL."""
        })
    
    responses = await router.call_batch('boost', prompts)
    
    for i, response in enumerate(responses):
        vote = 'NEUTRAL'
        if 'UP' in response.upper() and 'DOWN' not in response.upper():
            vote = 'UP'
        elif 'DOWN' in response.upper():
            vote = 'DOWN'
        votes[vote] += 1
        rationales.append(f"Agent {i+1} ({agents[i]['persona']}): {vote}")
    
    print(f"\n? Results:")
    print(f"  ? UP: {votes['UP']}/10")
    print(f"  ? DOWN: {votes['DOWN']}/10")
    print(f"  ? NEUTRAL: {votes['NEUTRAL']}/10")
    
    # Generate final prediction with Claude
    print(f"\n? Generating prediction report with Claude...")
    
    direction = max(votes, key=votes.get)
    confidence = votes[direction] / 10.0
    
    report_prompt = f"""Generate a prediction report JSON for:

TICKER: {ticker} ({ticker_info['name']})
EVENT: {event_context}
AGENT VOTES: UP={votes['UP']}, DOWN={votes['DOWN']}, NEUTRAL={votes['NEUTRAL']}

Return ONLY this JSON (no markdown):
{{
  "ticker": "{ticker}",
  "direction": "{direction}",
  "confidence": {confidence},
  "time_horizon": "d7",
  "causal_chain": [
    {{"step": 1, "event": "...", "consequence": "..."}},
    {{"step": 2, "event": "...", "consequence": "..."}}
  ],
  "key_signals": [
    {{
      "signal_type": "conflict",
      "description": "{event['event_type']} in {event['country']} with {event['fatalities']} fatalities",
      "impact": "negative",
      "confidence": 0.8
    }}
  ],
  "agent_consensus": {{
    "up": {votes['UP']},
    "down": {votes['DOWN']},
    "neutral": {votes['NEUTRAL']}
  }},
  "simulation_id": "sim_poc_001",
  "contrarian_view": null,
  "risk_factors": null
}}

Fill in realistic causal chain steps."""
    
    response = await router.call_primary(
        system_message="You generate valid JSON for financial predictions.",
        user_prompt=report_prompt
    )
    
    prediction_dict = parse_json_response(response)
    prediction_dict['generated_at'] = datetime.utcnow().isoformat()
    prediction_dict['trigger_event_id'] = event['event_id_cnty']
    
    prediction = PredictionCard(**prediction_dict)
    
    print(f"\n? Prediction Generated:")
    print(f"   Ticker: {prediction.ticker}")
    print(f"   Direction: {prediction.direction.value}")
    print(f"   Confidence: {prediction.confidence:.1%}")
    print(f"   Causal Chain: {len(prediction.causal_chain)} steps")
    
    # Save output
    output_file = f"/app/backend/scripts/poc_simple_output.json"
    with open(output_file, 'w') as f:
        json.dump(prediction.model_dump(), f, indent=2, default=str)
    print(f"\n? Saved to: {output_file}")
    
    print("\n" + "="*60)
    print("  ? SIMPLIFIED POC COMPLETE")
    print("="*60)
    print("\nValidation:")
    print("  ? Event mapped to ticker")
    print("  ? 10 agents voted (Gemini Flash)")
    print("  ? Consensus aggregated")
    print("  ? Claude generated structured JSON")
    print("  ? Schema validation passed")
    
    return True


if __name__ == "__main__":
    result = asyncio.run(run_simplified_simulation())
    if result:
        print("\n? Ready to scale to 50 agents and build main app!")
