import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.agents.narrative import create_storyteller
from google.adk.runners import InMemoryRunner
from google.genai import types

# Mock Auth
os.environ["GOOGLE_API_KEY"] = "fake_key_for_test" # The framework might need a key, but we'll mock the client if needed. 
# Actually, we need a real key for the model to run. 
# The user's env has the key. I will assume it is set or get it from auth.
from src.utils.auth import get_api_key
try:
    os.environ["GOOGLE_API_KEY"] = get_api_key()
except:
    print("Warning: Could not get API key. Test might fail if it hits the real model.")

# Mock Tools
class MockBibleTools:
    def __init__(self, story_id):
        self.story_id = story_id
    
    def read_bible(self):
        return """
        World Bible (Mock):
        Context: The hero, Kael, stands before the Gate of Shadows.
        History: Kael defeated the Goblin King in Ch1.
        """

    def get_bible(self):
        return self.read_bible()

class MockMetaTools:
    def __init__(self, story_id):
        self.story_id = story_id

    def trigger_research(self, topic: str):
        return f"[MOCK TOOL] Research on '{topic}' completed. Findings: It is a dark and scary place."

async def run_test():
    story_id = "test_story_123"
    
    # Patch the tools in narrative.py scope if possible, or just mock the class calls
    # easier to pass mocks if the creator accepted them, but it creates them internally.
    # We will use unittest.patch to intercept the creation of tools inside create_storyteller
    
    with patch('src.agents.narrative.BibleTools', side_effect=MockBibleTools) as MockBible, \
         patch('src.agents.narrative.MetaTools', side_effect=MockMetaTools) as MockMeta, \
         patch('src.agents.narrative.get_api_key', return_value=os.environ.get("GOOGLE_API_KEY", "test")):
         
        print("--- Initializing Agent ---")
        agent = create_storyteller(story_id)
        
        runner = InMemoryRunner(agent=agent, app_name="agents")
        
        # Create session
        try:
             await runner.session_service.create_session(app_name="agents", user_id="tester", session_id="test_sess")
        except:
             pass
        
        # Simulate User Input (The 'Turn')
        user_input = "I want to open the gate and face whatever is inside."
        print(f"--- Sending Input: {user_input} ---")
        
        response_text = ""
        # Wrap format
        input_msg = types.Content(parts=[types.Part(text=user_input)], role="user")
        
        async with runner:
            async for event in runner.run_async(user_id="tester", session_id="test_sess", new_message=input_msg):
                 if hasattr(event, "type") and event.type == "message":
                     # This is a simplification, depends on how InMemoryRunner yields
                     pass
        
        # InMemoryRunner logic is complex to capture output easily without a sink.
        # Let's just look at the last history or use a simpler run method if available.
        # Actually, InMemoryRunner yields events. We can collect them.
        
            session = await runner.session_service.get_session(app_name="agents", user_id="tester", session_id="test_sess")
        history = session.history
        last_message = history[-1].parts[0].text if history else "No response"
        
        print("\n--- Agent Response ---")
        print(last_message)
        print("----------------------")
        
        # Analysis
        if "Chapter" in last_message and last_message.count("Chapter") > 1:
            print("[FAIL] Multiple chapters detected or strict repetition.")
        else:
            print("[PASS] Usage seems singular (manual check required).")
            
        if "summary" in last_message and "choices" in last_message:
            print("[PASS] JSON block likely present.")
        else:
            print("[FAIL] JSON block missing.")

if __name__ == "__main__":
    asyncio.run(run_test())
