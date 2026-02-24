#!/bin/bash
# Real Performance Test - Uses Existing FableWeaver Pipeline
# Tests the Kudou Kageaki character through the actual WebSocket system

set -e

echo "========================================"
echo "FableWeaver Real Performance Test"
echo "Using Existing Pipeline"
echo "========================================"
echo ""

# Step 1: Create test story
echo "[1/3] Creating test story..."
STORY_RESPONSE=$(curl -s -X POST http://localhost:8000/stories \
  -H "Content-Type: application/json" \
  -d '{"title": "[REAL-PERF-TEST] Kudou Kageaki - Real Performance"}')

STORY_ID=$(echo $STORY_RESPONSE | jq -r '.id')
echo "✓ Story created: $STORY_ID"
echo ""

# Step 2: Load World Bible
echo "[2/3] Loading Kudou test dataset into World Bible..."
BIBLE_RESPONSE=$(curl -s -X PATCH http://localhost:8000/stories/$STORY_ID/bible \
  -H "Content-Type: application/json" \
  -d @tests/kudou_test_dataset.json)

echo "✓ World Bible loaded"
echo ""

# Step 3: Test via existing pipeline using WebSocket with Python
echo "[3/3] Testing through existing WebSocket pipeline..."
echo ""

.venv/bin/python - <<'PYEOF'
import asyncio
import json
import sys
import time

try:
    import websockets
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "websockets"])
    import websockets

async def test_pipeline():
    story_id = "$STORY_ID"

    print(f"🔗 Connecting to WebSocket: ws://localhost:8000/ws/{story_id}\n")

    try:
        async with websockets.connect(f"ws://localhost:8000/ws/{story_id}") as ws:
            print("✓ Connected\n")

            # Send a simple "choice" action (the main pipeline)
            print("📤 Sending story continuation prompt...")
            payload = {
                "action": "choice",
                "payload": {
                    "choice": "Write the first day of Kudou Kageaki at First High School. Show his reserved personality, avoid power display."
                }
            }

            await ws.send(json.dumps(payload))
            print("✓ Payload sent\n")

            # Collect responses with timing
            start_time = time.time()
            messages = []
            content = ""

            print("📥 Receiving stream (30s timeout)...\n")

            try:
                while True:
                    msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    data = json.loads(msg)
                    msg_type = data.get("type")
                    elapsed = time.time() - start_time

                    if msg_type == "content_delta":
                        text = data.get("text", "")
                        content += text
                        print(f"  [{elapsed:.1f}s] {msg_type}: {len(text)} chars")
                        if len(text) > 0:
                            print(f"       \"{text[:60]}...\"")
                    elif msg_type == "choices":
                        print(f"  [{elapsed:.1f}s] {msg_type}: Generation complete")
                        print(f"\n✓ Total content received: {len(content)} characters")
                        break
                    elif msg_type == "status":
                        status_val = data.get("status", "unknown")
                        print(f"  [{elapsed:.1f}s] {msg_type}: {status_val}")
                    else:
                        print(f"  [{elapsed:.1f}s] {msg_type}")

                    messages.append((elapsed, msg_type, data))

                    if elapsed > 30:
                        print(f"\n⏱️ Timeout reached (30s)")
                        break

            except asyncio.TimeoutError:
                print(f"\n⏱️ No more messages (timeout)")

            # Summary
            print("\n" + "="*50)
            print("PERFORMANCE METRICS")
            print("="*50)
            print(f"Total time: {time.time() - start_time:.2f}s")
            print(f"Total messages: {len(messages)}")
            print(f"Content received: {len(content)} characters")
            print(f"Message types: {set(m[1] for m in messages)}")

            if len(content) > 0:
                word_count = len(content.split())
                print(f"Word count: ~{word_count} words")
                print(f"\nFirst 200 characters:\n{content[:200]}...")
                print(f"\nStatus: ✅ GENERATION WORKING")
                return True
            else:
                print(f"\nStatus: ❌ NO CONTENT RECEIVED")
                return False

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

success = asyncio.run(test_pipeline())
sys.exit(0 if success else 1)
PYEOF

echo ""
echo "========================================"
echo "Test Complete"
echo "========================================"
echo ""
echo "To view the story: http://localhost:5173/stories"
echo "Story ID: $STORY_ID"
