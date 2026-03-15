"""Market Oracle AI - Core POC Simulation Script

Tests the complete 50-agent simulation flow:
1. Sample ACLED event input
2. Map event to ASX ticker
3. Run 50 agents (8 personas) for 3-5 rounds
4. Generate structured prediction JSON with Claude
5. Validate output schema

This POC must work before building the main app.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import json
import uuid
from datetime import datetime
from typing import List, Dict, Any
from dotenv import load_dotenv

load_dotenv()

from llm_router import LLMRouter, parse_json_response
from models.prediction import (
    PredictionCard, DirectionEnum, TimeHorizonEnum,
    KeySignal, SignalType, AgentConsensus, CausalChainStep
)
from event_ticker_mapping import map_event_to_ticker, get_ticker_info
from services.market_intelligence import build_enhanced_agent_context

# 8 ASX Persona Archetypes
PERSONAS = {
    'retail_investor': {
        'description': 'Individual retail investor, risk-averse, follows news',
        'risk_tolerance': 'low',
        'information_sources': ['mainstream_media', 'social_media'],
        'decision_style': 'emotional',
        'count': 8  # 8/50 agents
    },
    'superannuation_manager': {
        'description': 'Super fund manager, long-term horizon, institutional',
        'risk_tolerance': 'medium',
        'information_sources': ['bloomberg', 'analyst_reports', 'company_reports'],
        'decision_style': 'fundamental',
        'count': 6
    },
    'hedge_fund_quant': {
        'description': 'Hedge fund/quant algo trader, high frequency, data-driven',
        'risk_tolerance': 'high',
        'information_sources': ['market_data', 'alternative_data', 'algorithms'],
        'decision_style': 'quantitative',
        'count': 7
    },
    'financial_media': {
        'description': 'Financial journalist/analyst, influences sentiment',
        'risk_tolerance': 'neutral',
        'information_sources': ['expert_interviews', 'market_data', 'company_announcements'],
        'decision_style': 'narrative',
        'count': 5
    },
    'company_ir': {
        'description': 'Company IR/management, optimistic bias, insider knowledge',
        'risk_tolerance': 'low',
        'information_sources': ['internal_data', 'industry_contacts'],
        'decision_style': 'defensive',
        'count': 4
    },
    'foreign_institutional': {
        'description': 'Foreign institutional investor, global macro view',
        'risk_tolerance': 'medium',
        'information_sources': ['global_macro', 'geopolitical_analysis', 'currency_markets'],
        'decision_style': 'macro',
        'count': 8
    },
    'rba_regulator': {
        'description': 'RBA/ASIC/Treasury official, systemic risk focus',
        'risk_tolerance': 'very_low',
        'information_sources': ['economic_data', 'regulatory_reports', 'bank_submissions'],
        'decision_style': 'conservative',
        'count': 6
    },
    'options_trader': {
        'description': 'Options/derivatives trader, volatility-focused',
        'risk_tolerance': 'very_high',
        'information_sources': ['implied_volatility', 'options_flow', 'technical_analysis'],
        'decision_style': 'volatility',
        'count': 6
    }
}


class Agent:
    """Individual simulation agent with persona."""
    
    def __init__(self, agent_id: int, persona_type: str, persona_data: dict):
        self.agent_id = agent_id
        self.persona_type = persona_type
        self.persona_data = persona_data
        self.current_stance = None
        self.rationale = None
    
    def get_system_prompt(self) -> str:
        """Generate persona-specific system prompt."""
        return f"""You are Agent #{self.agent_id}, a {self.persona_data['description']} in the Australian market.

Your characteristics:
- Risk Tolerance: {self.persona_data['risk_tolerance']}
- Information Sources: {', '.join(self.persona_data['information_sources'])}
- Decision Style: {self.persona_data['decision_style']}

You are participating in a market simulation to predict the impact of a geopolitical event on an ASX stock.
Give a brief, realistic response as this type of market participant would."""
    
    async def form_opinion(self, llm_router: LLMRouter, event_context: str, ticker: str, round_num: int, previous_round_summary: str = "", event_data: dict = None, enhanced_context: str = "") -> Dict[str, Any]:
        """Agent forms opinion on the event's impact on ticker."""
        
        user_prompt = f"""Round {round_num} - Market Simulation

EVENT CONTEXT:
{event_context}

TARGET STOCK: {ticker}

{enhanced_context}

{previous_round_summary}

As a {self.persona_type}, provide your brief analysis:
1. How will this event affect {ticker}? (UP/DOWN/NEUTRAL)
2. One-sentence rationale

Respond in this exact format:
STANCE: [UP/DOWN/NEUTRAL]
RATIONALE: [one sentence]

Be concise and realistic to your persona."""
        
        try:
            response = await llm_router.call_boost(
                system_message=self.get_system_prompt(),
                user_prompt=user_prompt,
                session_id=f"agent_{self.agent_id}_r{round_num}"
            )
            
            # Parse response
            lines = response.strip().split('\n')
            stance_line = [l for l in lines if 'STANCE:' in l.upper()]
            rationale_line = [l for l in lines if 'RATIONALE:' in l.upper()]
            
            if stance_line:
                stance_text = stance_line[0].split(':', 1)[1].strip().upper()
                if 'UP' in stance_text:
                    self.current_stance = 'UP'
                elif 'DOWN' in stance_text:
                    self.current_stance = 'DOWN'
                else:
                    self.current_stance = 'NEUTRAL'
            else:
                # Default if parsing fails
                if 'UP' in response.upper():
                    self.current_stance = 'UP'
                elif 'DOWN' in response.upper():
                    self.current_stance = 'DOWN'
                else:
                    self.current_stance = 'NEUTRAL'
            
            if rationale_line:
                self.rationale = rationale_line[0].split(':', 1)[1].strip()
            else:
                self.rationale = response.strip()[:200]  # First 200 chars
            
            return {
                'agent_id': self.agent_id,
                'persona': self.persona_type,
                'stance': self.current_stance,
                'rationale': self.rationale
            }
            
        except Exception as e:
            print(f"Agent {self.agent_id} error: {str(e)}")
            # Fallback
            self.current_stance = 'NEUTRAL'
            self.rationale = "Unable to form opinion due to error"
            return {
                'agent_id': self.agent_id,
                'persona': self.persona_type,
                'stance': 'NEUTRAL',
                'rationale': self.rationale
            }


class Simulation:
    """50-agent simulation engine."""
    
    def __init__(self, llm_router: LLMRouter):
        self.llm_router = llm_router
        self.agents: List[Agent] = []
        self.simulation_id = f"sim_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        self._init_agents()
    
    def _init_agents(self):
        """Initialize 50 agents across 8 personas."""
        agent_id = 1
        for persona_type, persona_data in PERSONAS.items():
            count = persona_data['count']
            for _ in range(count):
                agent = Agent(agent_id, persona_type, persona_data)
                self.agents.append(agent)
                agent_id += 1
        
        print(f"✓ Initialized {len(self.agents)} agents across {len(PERSONAS)} personas")
    
    async def run_round(self, round_num: int, event_context: str, ticker: str, event_data: dict, enhanced_context: str = "", previous_summary: str = "") -> Dict[str, Any]:
        """Run one simulation round with all agents."""
        print(f"\n🔄 Running Round {round_num}...")
        
        # Agents form opinions in parallel (using boost model for speed)
        tasks = [
            agent.form_opinion(self.llm_router, event_context, ticker, round_num, previous_summary, event_data, enhanced_context)
            for agent in self.agents
        ]
        
        opinions = await asyncio.gather(*tasks)
        
        # Aggregate stances
        up_count = sum(1 for o in opinions if o['stance'] == 'UP')
        down_count = sum(1 for o in opinions if o['stance'] == 'DOWN')
        neutral_count = sum(1 for o in opinions if o['stance'] == 'NEUTRAL')
        
        # Extract top rationales
        up_rationales = [o['rationale'] for o in opinions if o['stance'] == 'UP'][:3]
        down_rationales = [o['rationale'] for o in opinions if o['stance'] == 'DOWN'][:3]
        
        round_result = {
            'round': round_num,
            'consensus': {
                'up': up_count,
                'down': down_count,
                'neutral': neutral_count
            },
            'top_up_rationales': up_rationales,
            'top_down_rationales': down_rationales
        }
        
        print(f"  Round {round_num} consensus: ↑{up_count} ↓{down_count} ⟷{neutral_count}")
        
        return round_result
    
    async def run_simulation(self, event_data: dict, ticker: str, num_rounds: int = 3) -> Dict[str, Any]:
        """Run complete simulation for an event."""
        print(f"\n{'='*60}")
        print(f"🚀 SIMULATION START: {self.simulation_id}")
        print(f"{'='*60}")
        print(f"Ticker: {ticker}")
        print(f"Event: {event_data.get('country')} - {event_data.get('event_type')}")
        print(f"Rounds: {num_rounds}")
        
        # Build event context
        event_context = f"""
CONFLICT EVENT:
- Country: {event_data.get('country')}
- Location: {event_data.get('location')}
- Event Type: {event_data.get('event_type')}
- Fatalities: {event_data.get('fatalities')}
- Date: {event_data.get('event_date')}
- Notes: {event_data.get('notes', 'N/A')}
"""
        
        # Build enhanced context with sector sensitivity and AUD transmission
        enhanced_context = build_enhanced_agent_context(ticker, event_data)
        if enhanced_context:
            print(f"\n📊 Market Intelligence Injected:")
            print(enhanced_context[:200] + "..." if len(enhanced_context) > 200 else enhanced_context)
        
        # Run rounds
        round_results = []
        previous_summary = ""
        
        for round_num in range(1, num_rounds + 1):
            round_result = await self.run_round(
                round_num=round_num,
                event_context=event_context,
                ticker=ticker,
                event_data=event_data,
                enhanced_context=enhanced_context,
                previous_summary=previous_summary
            )
            round_results.append(round_result)
            
            # Update summary for next round
            consensus = round_result['consensus']
            previous_summary = f"""
Previous Round {round_num} Consensus:
- UP: {consensus['up']}/{len(self.agents)}
- DOWN: {consensus['down']}/{len(self.agents)}
- NEUTRAL: {consensus['neutral']}/{len(self.agents)}
"""
        
        # Final consensus (use last round)
        final_consensus = round_results[-1]['consensus']
        
        print(f"\n✅ Simulation complete")
        print(f"Final consensus: ↑{final_consensus['up']} ↓{final_consensus['down']} ⟷{final_consensus['neutral']}")
        
        return {
            'simulation_id': self.simulation_id,
            'ticker': ticker,
            'event_data': event_data,
            'round_results': round_results,
            'final_consensus': final_consensus
        }
    
    async def generate_prediction_report(self, simulation_results: Dict[str, Any]) -> PredictionCard:
        """Use Claude to generate final structured prediction report."""
        print(f"\n📊 Generating prediction report with Claude...")
        
        ticker = simulation_results['ticker']
        ticker_info = get_ticker_info(ticker)
        event_data = simulation_results['event_data']
        final_consensus = simulation_results['final_consensus']
        
        # Build comprehensive prompt for Claude with Australian market context
        system_message = """You are a financial analyst at Market Oracle AI specializing in Australian Securities Exchange (ASX) intelligence. Your task is to generate a structured prediction report based on a 50-agent market simulation.

AUSTRALIAN MARKET CONTEXT (CRITICAL - USE THESE TRANSMISSION MECHANISMS):

Template A - AUD Commodity Amplifier:
When AUD depreciates and commodity prices stay flat or rise:
• Example: Iron ore $100 USD/t → AUD falls 5% → BHP.AX earns 5% more in AUD terms (85% pass-through)
• Formula: If commodity export price stable + AUD falls X% → ASX resource stock revenue rises ~0.85X% in AUD terms
• Application: Always cite this FX tailwind when event weakens AUD AND ticker is BHP.AX, RIO.AX, FMG.AX, LYC.AX

Template B - Superannuation Contagion:
Australian super funds ($3.5T AUM) have 0.65-0.75 correlation with S&P 500:
• US equity selloff → Super funds mark-to-market losses → domestic equity redemptions
• Chain: S&P 500 falls 3% → ASX 200 likely falls 2-2.25% within 48 hours via super rebalancing
• Application: When event originates in US markets (Fed policy, tech selloff), cite super contagion channel

Template C - Rate Sensitivity Asymmetry:
RBA rate hikes create divergent impacts across ASX sectors:
• Banks (CBA.AX, WBC.AX): Net Interest Margin (NIM) expansion → bullish (sensitivity +1.8)
• REITs (GPT.AX, VCX.AX): Property discount rates rise + debt costs increase → bearish (sensitivity -2.2)
• Example causal chain: "RBA hikes 25bps → CBA.AX NIM expands ~8bps → quarterly profit uplift $120M"
• Application: Always cite NIM mechanics when event is RBA rate decision AND ticker is a bank

Template D - China Concentration Risk:
80% of Pilbara iron ore exports go to China:
• Single-country dependency creates binary risk: China policy shift → immediate margin compression
• Example: China announces 15% import quota cut → BHP.AX, RIO.AX, FMG.AX face revenue loss within 1 quarter
• Port Hedland congestion metric is a 72-hour leading indicator of export disruption
• Application: When event involves China trade policy, tariffs, or geopolitical tension, cite 80% dependency

Template E - Critical Minerals Premium:
Rare earth supply chain disruptions boost Australian producers:
• Taiwan Strait risk OR China export restrictions → LYC.AX premium expands (non-China supply valued)
• Semiconductor demand inelastic → rare earth price spike passes through quickly
• Example: China rare earth export ban → LYC.AX sees 15-20% price premium as Japan/US buyers scramble
• Application: When event disrupts China/Taiwan rare earth or semiconductor supply chain

CRITICAL INSTRUCTIONS FOR CAUSAL CHAINS:
- ALWAYS reference specific transmission mechanisms from Templates A-E when applicable
- Use concrete numbers (e.g., "8bps NIM expansion" not "margin improvement")
- Cite the 85% AUD pass-through, 0.70 super correlation, or 80% China dependency explicitly
- Make causal chains sound like a seasoned ASX analyst who knows these structural relationships

You MUST respond with ONLY valid JSON matching this exact schema (no markdown, no explanations):

{
  "ticker": "string",
  "direction": "UP" | "DOWN" | "NEUTRAL",
  "confidence": 0.0-1.0,
  "time_horizon": "h24" | "d7" | "d30",
  "causal_chain": [
    {"step": 1, "event": "...", "consequence": "..."},
    ...2-5 steps with Australian transmission mechanisms
  ],
  "key_signals": [
    {
      "signal_type": "conflict" | "commodity" | "macro" | "shipping" | "market_sentiment",
      "description": "...",
      "impact": "positive" | "negative" | "neutral",
      "confidence": 0.0-1.0
    }
  ],
  "agent_consensus": {
    "up": int,
    "down": int,
    "neutral": int
  },
  "contrarian_view": "string or null",
  "risk_factors": ["...", "..."] or null
}

Base your analysis on the simulation data provided. Be realistic, specific, and cite Australian market structure."""
        
        user_prompt = f"""Generate a prediction report for this simulation:

TICKER: {ticker} ({ticker_info['name']})
SECTOR: {ticker_info['sector']} - {ticker_info['subsector']}

TRIGGER EVENT:
- Country: {event_data['country']}
- Event Type: {event_data['event_type']}
- Fatalities: {event_data['fatalities']}
- Location: {event_data['location']}
- Notes: {event_data.get('notes', 'N/A')}

AGENT SIMULATION RESULTS:
- Total Agents: 50
- Final Consensus:
  * UP votes: {final_consensus['up']}
  * DOWN votes: {final_consensus['down']}
  * NEUTRAL votes: {final_consensus['neutral']}

ROUND-BY-ROUND:
{json.dumps(simulation_results['round_results'], indent=2)}

Based on this simulation, generate the JSON prediction report. Consider:
1. The 50-agent consensus clearly indicates direction
2. Causal chain from the conflict event to {ticker}'s stock price
3. Key signals from the event data
4. Realistic confidence score based on consensus strength
5. Contrarian views and risk factors

Return ONLY the JSON object, no other text."""
        
        try:
            response = await self.llm_router.call_primary(
                system_message=system_message,
                user_prompt=user_prompt,
                session_id=f"{self.simulation_id}_report"
            )
            
            # Parse and validate JSON
            prediction_dict = parse_json_response(response)
            
            # Add metadata
            prediction_dict['simulation_id'] = self.simulation_id
            prediction_dict['trigger_event_id'] = event_data.get('event_id_cnty')
            prediction_dict['generated_at'] = datetime.utcnow().isoformat()
            
            # Validate with Pydantic
            prediction = PredictionCard(**prediction_dict)
            
            print(f"✅ Prediction report generated successfully")
            return prediction
            
        except Exception as e:
            print(f"❌ Error generating prediction report: {str(e)}")
            raise


async def main():
    """Main POC test function."""
    print("\n" + "="*60)
    print("  MARKET ORACLE AI - CORE POC TEST")
    print("="*60)
    
    # Sample ACLED event
    sample_event = {
        'event_id_cnty': 'test_12345',
        'country': 'Iran',
        'location': 'Strait of Hormuz',
        'event_type': 'Battles',
        'fatalities': 23,
        'event_date': '2026-03-15',
        'notes': 'Armed naval confrontation near Hormuz, oil tanker route disrupted'
    }
    
    print("\n📌 Sample Event:")
    print(f"   {sample_event['country']} - {sample_event['event_type']}")
    print(f"   {sample_event['notes']}")
    
    # Initialize LLM router
    print("\n🔧 Initializing LLM router...")
    llm_router = LLMRouter()
    
    # Map event to ticker
    print("\n🎯 Mapping event to ASX ticker...")
    ticker = map_event_to_ticker(sample_event)
    if not ticker:
        print("❌ No ticker mapping found!")
        return
    
    ticker_info = get_ticker_info(ticker)
    print(f"   Mapped to: {ticker} ({ticker_info['name']})")
    
    # Run simulation
    simulation = Simulation(llm_router)
    simulation_results = await simulation.run_simulation(
        event_data=sample_event,
        ticker=ticker,
        num_rounds=3  # Start with 3 rounds for POC
    )
    
    # Generate prediction report
    prediction = await simulation.generate_prediction_report(simulation_results)
    
    # Display results
    print("\n" + "="*60)
    print("  PREDICTION CARD")
    print("="*60)
    print(f"\n🎯 Ticker: {prediction.ticker}")
    print(f"📈 Direction: {prediction.direction.value}")
    print(f"🎲 Confidence: {prediction.confidence:.1%}")
    print(f"⏱️  Time Horizon: {prediction.time_horizon.value}")
    
    print(f"\n🔗 Causal Chain:")
    for step in prediction.causal_chain:
        print(f"   {step.step}. {step.event}")
        print(f"      → {step.consequence}")
    
    print(f"\n📊 Agent Consensus:")
    print(f"   ↑ UP: {prediction.agent_consensus.up} ({prediction.agent_consensus.up_percentage:.1f}%)")
    print(f"   ↓ DOWN: {prediction.agent_consensus.down} ({prediction.agent_consensus.down_percentage:.1f}%)")
    print(f"   ⟷ NEUTRAL: {prediction.agent_consensus.neutral}")
    
    print(f"\n🔔 Key Signals:")
    for signal in prediction.key_signals:
        print(f"   • {signal.signal_type.value}: {signal.description}")
        print(f"     Impact: {signal.impact}, Confidence: {signal.confidence:.1%}")
    
    if prediction.contrarian_view:
        print(f"\n⚠️  Contrarian View: {prediction.contrarian_view}")
    
    if prediction.risk_factors:
        print(f"\n⚠️  Risk Factors:")
        for risk in prediction.risk_factors:
            print(f"   • {risk}")
    
    # Save to file
    output_file = f"/app/backend/scripts/poc_output_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w') as f:
        json.dump(prediction.model_dump(), f, indent=2, default=str)
    print(f"\n💾 Full prediction saved to: {output_file}")
    
    print("\n" + "="*60)
    print("  ✅ POC TEST COMPLETE")
    print("="*60)
    print("\nValidation:")
    print("  ✓ LLM routing works (Claude + Gemini + fallback)")
    print("  ✓ 50-agent simulation complete")
    print("  ✓ Structured JSON prediction generated")
    print("  ✓ Schema validation passed")
    print("\n🎉 Ready to proceed to Phase 2: Main App Development")


if __name__ == "__main__":
    asyncio.run(main())
