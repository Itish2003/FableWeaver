import asyncio
import json
import time
import websockets
from tenacity import retry, stop_after_attempt, wait_exponential

# Configuration
URL = "ws://localhost:8000/ws"

async def simulate_game():
    print(f"Connecting to {URL}...")
    try:
        async with websockets.connect(URL) as websocket:
            print("Connected!")

            # --- Step 1: Initialization ---
            init_payload = {
                "action": "init",
                "payload": {
                    "universes": ["High School DxD"],
                    "timeline_deviation": "Devil Civil War Era. The Great War is recent history.",
                    "user_input": "Start the story with the OC making a move during the Civil War confusion.",
                    # Research is forcibly enabled in the new backend structure provided constraints
                }
            }
            
            print("\n[Client] Sending INIT...")
            await websocket.send(json.dumps(init_payload))
            
            # Listen loop
            buffer = ""
            while True:
                msg = await websocket.recv()
                data = json.loads(msg)
                
                type = data.get("type")
                
                if type == "status":
                    print(f"[Server Status] {data.get('status')}")
                elif type == "content_delta":
                    text = data.get("text", "")
                    sender = data.get("sender", "unknown")
                    print(f"[{sender}] {text}", end="", flush=True) 
                    buffer += text
                elif type == "turn_complete":
                     print("\n\n[Client] TURN COMPLETE.")
                     break
                elif type == "error":
                    print(f"\n[Server Error] {data.get('message')}")
                    return

            # Log the full text
            print("\n--- Turn 1 Result ---")
            print(buffer[:500] + "...") # Preview

            # --- Step 2: Make a Choice ---
            # We assume the last part of the text contained the choices.
            # For simulation, we just pick "Choice 1".
            
            choice_payload = {
                "action": "choice",
                "payload": {
                    "choice": "Option 1: Investigate the ancient ruins mentioned in the tome."
                }
            }
            
            print("\n[Client] Sending CHOICE...")
            await websocket.send(json.dumps(choice_payload))
            
            buffer = ""
            while True:
                msg = await websocket.recv()
                data = json.loads(msg)
                
                type = data.get("type")
                
                if type == "status":
                    print(f"[Server Status] {data.get('status')}")
                elif type == "content_delta":
                    text = data.get("text", "")
                    buffer += text
                elif type == "turn_complete":
                     print("\n\n[Client] TURN 2 COMPLETE.")
                     break
                elif type == "error":
                    print(f"\n[Server Error] {data.get('message')}")
                    return

            print("\n--- Turn 2 Result ---")
            print(buffer[:500] + "...")

    except Exception as e:
        print(f"Simulation failed: {e}")

if __name__ == "__main__":
    asyncio.run(simulate_game())
