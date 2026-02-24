#!/usr/bin/env python3
"""Debug the error message from WebSocket."""

import asyncio
import json
import subprocess
import sys
from pathlib import Path

try:
    import websockets
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "websockets"])
    import websockets

DATASET_PATH = Path("/Users/itish/Downloads/Fable/src/dataset.md")

async def test_debug():
    story_id = "57ec021f-8427-4dbe-86a3-e51909d599da"
    uri = f"ws://localhost:8000/ws/{story_id}"

    with open(DATASET_PATH, "r") as f:
        dataset = f.read()

    prompt = f"""You are the Storyteller. Generate opening chapter for Kudou Kageaki.

CHARACTER FRAMEWORK:
{dataset}

Generate the chapter now:"""

    print("Connecting...")
    async with websockets.connect(uri) as ws:
        print("✓ Connected\n")

        payload = {"action": "choice", "payload": {"choice": prompt}}
        await ws.send(json.dumps(payload))
        print("✓ Sent prompt\n")

        # Get first message
        msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
        data = json.loads(msg)

        print("First message received:")
        print(json.dumps(data, indent=2))

asyncio.run(test_debug())
