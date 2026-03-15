"""LLM Router with multi-model fallback for Market Oracle AI.

Primary: Claude Sonnet 4.6 - ReportAgent, knowledge graph, prediction reports
Secondary: Gemini 2.5 Flash - per-agent simulation reasoning
Fallback: GPT-4.1 - safety net
"""

import os
import json
import asyncio
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv
from emergentintegrations.llm.chat import LlmChat, UserMessage
import logging

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LLMRouter:
    """Routes LLM requests to appropriate models with fallback."""
    
    def __init__(self):
        self.api_key = os.getenv('EMERGENT_LLM_KEY')
        if not self.api_key:
            raise ValueError("EMERGENT_LLM_KEY not found in environment variables")
        
        # Model configuration
        self.primary_model = os.getenv('LLM_MODEL_NAME', 'claude-sonnet-4-6')
        self.boost_model = os.getenv('BOOST_LLM_MODEL_NAME', 'gemini-2.5-flash')
        self.fallback_model = os.getenv('FALLBACK_LLM_MODEL_NAME', 'gpt-4.1')
        
        # Provider mapping
        self.model_to_provider = {
            'claude-sonnet-4-6': 'anthropic',
            'claude-opus-4-6': 'anthropic',
            'claude-4-sonnet-20250514': 'anthropic',
            'gemini-2.5-flash': 'gemini',
            'gemini-2.5-pro': 'gemini',
            'gemini-3-flash-preview': 'gemini',
            'gpt-4.1': 'openai',
            'gpt-5.2': 'openai',
            'gpt-5.1': 'openai'
        }
        
        logger.info(f"LLM Router initialized: Primary={self.primary_model}, Boost={self.boost_model}, Fallback={self.fallback_model}")
    
    def _get_provider(self, model: str) -> str:
        """Get provider for a given model."""
        return self.model_to_provider.get(model, 'openai')
    
    async def call_primary(self, system_message: str, user_prompt: str, session_id: str = "primary") -> str:
        """Call primary model (Claude Sonnet 4.6) for structured outputs."""
        return await self._call_with_fallback(
            model=self.primary_model,
            system_message=system_message,
            user_prompt=user_prompt,
            session_id=session_id,
            use_fallback=True
        )
    
    async def call_boost(self, system_message: str, user_prompt: str, session_id: str = "boost") -> str:
        """Call boost model (Gemini 2.5 Flash) for high-volume agent calls."""
        return await self._call_with_fallback(
            model=self.boost_model,
            system_message=system_message,
            user_prompt=user_prompt,
            session_id=session_id,
            use_fallback=True
        )
    
    async def _call_with_fallback(
        self,
        model: str,
        system_message: str,
        user_prompt: str,
        session_id: str,
        use_fallback: bool = True,
        max_retries: int = 2
    ) -> str:
        """Call LLM with automatic fallback on failure."""
        provider = self._get_provider(model)
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Calling {provider}/{model} (attempt {attempt + 1}/{max_retries})")
                
                chat = LlmChat(
                    api_key=self.api_key,
                    session_id=session_id,
                    system_message=system_message
                ).with_model(provider, model)
                
                user_message = UserMessage(text=user_prompt)
                response = await chat.send_message(user_message)
                
                logger.info(f"Successfully received response from {provider}/{model}")
                return response
                
            except Exception as e:
                logger.error(f"Error calling {provider}/{model}: {str(e)}")
                
                if attempt < max_retries - 1:
                    logger.info("Retrying with same model...")
                    await asyncio.sleep(1)
                    continue
                
                if use_fallback and model != self.fallback_model:
                    logger.info(f"Falling back to {self.fallback_model}")
                    return await self._call_with_fallback(
                        model=self.fallback_model,
                        system_message=system_message,
                        user_prompt=user_prompt,
                        session_id=session_id,
                        use_fallback=False,
                        max_retries=2
                    )
                else:
                    raise Exception(f"All LLM attempts failed: {str(e)}")
    
    async def call_batch(self, model_type: str, prompts: List[Dict[str, str]]) -> List[str]:
        """Call LLM for multiple prompts in parallel (for agent simulation)."""
        tasks = []
        for i, prompt in enumerate(prompts):
            if model_type == "boost":
                task = self.call_boost(
                    system_message=prompt['system'],
                    user_prompt=prompt['user'],
                    session_id=f"agent_{i}"
                )
            else:
                task = self.call_primary(
                    system_message=prompt['system'],
                    user_prompt=prompt['user'],
                    session_id=f"agent_{i}"
                )
            tasks.append(task)
        
        return await asyncio.gather(*tasks)


def parse_json_response(response: str) -> Dict[str, Any]:
    """Parse JSON from LLM response with error handling and repair."""
    # Try direct JSON parse
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass
    
    # Try to extract JSON from markdown code blocks
    if '```json' in response:
        start = response.find('```json') + 7
        end = response.find('```', start)
        if end != -1:
            json_str = response[start:end].strip()
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass
    
    # Try to find JSON object in response
    start_idx = response.find('{')
    end_idx = response.rfind('}') + 1
    if start_idx != -1 and end_idx > start_idx:
        try:
            return json.loads(response[start_idx:end_idx])
        except json.JSONDecodeError:
            pass
    
    # Last resort: try to repair common JSON issues
    try:
        # Remove trailing commas
        cleaned = response.replace(',}', '}').replace(',]', ']')
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse JSON from LLM response: {str(e)}")


if __name__ == "__main__":
    # Test the router
    async def test_router():
        router = LLMRouter()
        
        # Test primary (Claude)
        print("Testing primary model (Claude Sonnet 4.6)...")
        response = await router.call_primary(
            system_message="You are a helpful assistant.",
            user_prompt="Say 'Hello from Claude!' and nothing else."
        )
        print(f"Primary response: {response}")
        
        # Test boost (Gemini)
        print("\nTesting boost model (Gemini 2.5 Flash)...")
        response = await router.call_boost(
            system_message="You are a helpful assistant.",
            user_prompt="Say 'Hello from Gemini!' and nothing else."
        )
        print(f"Boost response: {response}")
        
        # Test JSON parsing
        print("\nTesting JSON parsing...")
        json_response = await router.call_primary(
            system_message="You always respond with valid JSON.",
            user_prompt='Return this JSON: {"status": "success", "message": "test"}'
        )
        parsed = parse_json_response(json_response)
        print(f"Parsed JSON: {parsed}")
    
    asyncio.run(test_router())
