"""Quick LLM router test to verify Emergent Universal Key setup."""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from llm_router import LLMRouter, parse_json_response

async def test_llm_setup():
    """Test that LLM routing works with all three models."""
    print("\n🧪 Testing LLM Router Setup...")
    print("="*50)
    
    router = LLMRouter()
    
    # Test 1: Claude Sonnet 4.6 (Primary)
    print("\n1️⃣ Testing Claude Sonnet 4.6 (Primary)...")
    try:
        response = await router.call_primary(
            system_message="You are a helpful assistant.",
            user_prompt="Say 'Hello from Claude Sonnet 4.6!' and nothing else."
        )
        print(f"✅ Claude Response: {response}")
    except Exception as e:
        print(f"❌ Claude Error: {str(e)}")
        return False
    
    # Test 2: Gemini 2.5 Flash (Boost)
    print("\n2️⃣ Testing Gemini 2.5 Flash (Boost)...")
    try:
        response = await router.call_boost(
            system_message="You are a helpful assistant.",
            user_prompt="Say 'Hello from Gemini 2.5 Flash!' and nothing else."
        )
        print(f"✅ Gemini Response: {response}")
    except Exception as e:
        print(f"❌ Gemini Error: {str(e)}")
        return False
    
    # Test 3: JSON parsing with Claude
    print("\n3️⃣ Testing JSON generation with Claude...")
    try:
        response = await router.call_primary(
            system_message="You respond only with valid JSON.",
            user_prompt='Return this exact JSON: {"status": "success", "model": "claude-sonnet-4-6", "test": true}'
        )
        parsed = parse_json_response(response)
        print(f"✅ JSON Response: {parsed}")
    except Exception as e:
        print(f"❌ JSON Error: {str(e)}")
        return False
    
    print("\n" + "="*50)
    print("✅ All LLM tests passed!")
    print("="*50)
    return True

if __name__ == "__main__":
    result = asyncio.run(test_llm_setup())
    if result:
        print("\n🎉 LLM Router is ready for simulation!")
    else:
        print("\n❌ LLM Router has issues. Check API key and configuration.")
