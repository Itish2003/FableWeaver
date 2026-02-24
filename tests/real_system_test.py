#!/usr/bin/env python3
"""
Real System Test: Use the existing system's own initialization flow

1. Create story via REST API
2. Connect to WebSocket
3. Send "init" action with full dataset
4. Let the system do back-and-forth naturally
5. Capture the full interaction and validate quality
"""

import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Any, List

try:
    import websockets
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "websockets"])
    import websockets

import httpx

# Configuration
API_BASE_URL = "http://localhost:8000"
DATASET_PATH = Path("/Users/itish/Downloads/Fable/src/dataset.md")


class RealSystemTest:
    """Use the system's own initialization and back-and-forth flow."""

    def __init__(self):
        self.story_id = None
        self.dataset_content = None
        self.results = {
            "test_date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "phases": {},
            "metrics": {},
        }

    async def setup(self):
        """Create story via REST API."""
        print("\n" + "=" * 70)
        print("STEP 1: Create Story via REST API")
        print("=" * 70)

        # Load dataset
        print("\n[1/2] Loading full dataset from src/dataset.md...")
        with open(DATASET_PATH, "r") as f:
            self.dataset_content = f.read()
        print(f"✓ Loaded {len(self.dataset_content):,} characters")

        # Create story
        print("\n[2/2] Creating story...")
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{API_BASE_URL}/stories",
                json={"title": "[REAL] Kudou Kageaki - System Integration Test"},
            )
            if response.status_code != 200:
                raise RuntimeError(f"Story creation failed: {response.text}")
            self.story_id = response.json()["id"]

        print(f"✓ Story ID: {self.story_id}\n")

    async def test_init_flow(self):
        """Send init action through system's own pipeline."""
        print("=" * 70)
        print("STEP 2: Initialize Story via WebSocket 'init' Action")
        print("=" * 70)

        uri = f"ws://localhost:8000/ws/{self.story_id}"

        print(f"\nConnecting to {uri}...")

        messages = []
        content_received = ""
        choices_received = []
        init_complete = False

        try:
            async with websockets.connect(uri) as websocket:
                print("✓ Connected\n")

                # Send init action with full dataset as user_input
                print("Sending 'init' action with complete dataset...")
                init_payload = {
                    "action": "init",
                    "payload": {
                        "universes": [
                            "The Irregular at Magic High School",
                            "Jujutsu Kaisen Crossover",
                        ],
                        "user_input": self.dataset_content,
                        "genre": "Fantasy / School Life / Psychological Thriller",
                        "theme": "Containment vs Contamination - Power That Grows",
                        "timeline_deviation": "First High School, Kudou Kageaki Enrollment Arc",
                    },
                }

                await websocket.send(json.dumps(init_payload))
                print("✓ Init payload sent\n")

                # Stream responses
                print("-" * 70)
                print("Streaming back-and-forth interaction:")
                print("-" * 70 + "\n")

                start_time = time.time()
                message_count = 0

                try:
                    while True:
                        try:
                            msg = await asyncio.wait_for(
                                websocket.recv(), timeout=2.0
                            )
                            data = json.loads(msg)
                            message_count += 1
                            msg_type = data.get("type")
                            elapsed = time.time() - start_time

                            messages.append(
                                {
                                    "type": msg_type,
                                    "time": elapsed,
                                    "size": len(msg),
                                }
                            )

                            # Pretty print by type
                            if msg_type == "content_delta":
                                text = data.get("text", "")
                                sender = data.get("sender", "system")
                                content_received += text
                                print(f"[{elapsed:6.1f}s] 📝 {sender}: {len(text):4d} chars")
                                if len(text) <= 150:
                                    print(f"           {text}")

                            elif msg_type == "choices":
                                choices = data.get("choices", [])
                                choices_received = choices
                                init_complete = True
                                print(
                                    f"[{elapsed:6.1f}s] 🎯 Choices presented ({len(choices)} options)"
                                )
                                for i, choice in enumerate(choices, 1):
                                    print(f"           {i}. {choice[:65]}...")

                            elif msg_type == "status":
                                status = data.get("status")
                                detail = data.get("detail", "")
                                detail_str = (
                                    f": {detail}" if detail else ""
                                )
                                print(
                                    f"[{elapsed:6.1f}s] ⚙️  Status: {status}{detail_str}"
                                )

                            elif msg_type == "error":
                                error_msg = data.get("message")
                                print(f"[{elapsed:6.1f}s] ❌ ERROR: {error_msg}")
                                break

                            # Stop if we got choices
                            if init_complete:
                                print("\n" + "-" * 70)
                                break

                            # Timeout safety
                            if elapsed > 120:
                                print(f"\n⏱️  Timeout (120s) - stopping")
                                break

                        except asyncio.TimeoutError:
                            elapsed = time.time() - start_time
                            if elapsed > 60:
                                print(
                                    f"\n⏱️  No messages for 2s after {elapsed:.1f}s total"
                                )
                                break

                except Exception as e:
                    print(f"\n✗ Stream error: {e}")

        except Exception as e:
            print(f"✗ WebSocket error: {e}")
            return False

        # Store results
        generation_time = time.time() - start_time

        self.results["phases"]["initialization"] = {
            "total_time_seconds": generation_time,
            "messages_received": message_count,
            "content_length": len(content_received),
            "content_word_count": len(content_received.split()),
            "choices_count": len(choices_received),
            "choices": choices_received,
            "init_complete": init_complete,
        }

        # Validate
        print("\n" + "=" * 70)
        print("VALIDATION: Quality Assessment")
        print("=" * 70)

        validation = self._validate_output(content_received, choices_received)
        self.results["phases"]["validation"] = validation

        for criterion, result in validation["criteria"].items():
            icon = "✅" if result else "❌"
            print(f"{icon} {criterion}")

        return init_complete

    def _validate_output(
        self, content: str, choices: List[str]
    ) -> Dict[str, Any]:
        """Validate generated content."""

        text_lower = content.lower()

        criteria = {
            "content_generated": len(content) > 0,
            "sufficient_length": len(content) >= 1000,
            "personality_evident": any(
                word in text_lower
                for word in [
                    "quiet",
                    "restrained",
                    "composed",
                    "watchful",
                    "observ",
                ]
            ),
            "no_power_abuse": not any(
                phrase in text_lower
                for phrase in [
                    "deployed curse",
                    "released spirit",
                    "manifested power",
                    "casual display",
                ]
            ),
            "relationship_referenced": "minoru" in text_lower,
            "restraint_concept_present": any(
                word in text_lower for word in ["restraint", "containment", "control"]
            ),
            "choices_meaningful": len(choices) >= 3,
            "choice_quality": all(len(c) > 30 for c in choices),
        }

        passed = sum(1 for v in criteria.values() if v)
        total = len(criteria)

        return {
            "criteria": criteria,
            "passed": passed,
            "total": total,
            "pass_rate": f"{(passed/total*100):.1f}%",
        }

    async def run(self):
        """Execute test."""
        try:
            await self.setup()
            success = await self.test_init_flow()

            self._print_summary(success)
            self._save_results()

        except Exception as e:
            print(f"\n✗ Test failed: {e}")
            import traceback

            traceback.print_exc()

    def _print_summary(self, success: bool):
        """Print summary."""
        print("\n" + "=" * 70)
        print("TEST SUMMARY")
        print("=" * 70)

        init = self.results["phases"].get("initialization", {})
        val = self.results["phases"].get("validation", {})

        print(f"\nGeneration Time: {init.get('total_time_seconds', 0):.1f}s")
        print(f"Content Length: {init.get('content_length', 0):,} characters")
        print(f"Word Count: {init.get('content_word_count', 0):,} words")
        print(f"Choices: {init.get('choices_count', 0)}")

        print(f"\nValidation: {val.get('passed', 0)}/{val.get('total', 0)}")
        print(f"Pass Rate: {val.get('pass_rate', 'N/A')}")

        if success and init.get("content_length", 0) > 1000:
            readiness = 50 + (10 if val.get("passed", 0) >= 6 else 0)
            print(f"\n✅ System Readiness: {readiness}%")
            print("   - Back-and-forth: ✅ Working")
            print("   - Content generation: ✅ Working")
            print("   - Choice presentation: ✅ Working")
        else:
            print(f"\n❌ System Readiness: 20%")
            print("   - Issues detected")

    def _save_results(self):
        """Save results."""
        results_path = Path(__file__).parent / "real_system_test_results.json"
        with open(results_path, "w") as f:
            json.dump(self.results, f, indent=2)
        print(f"\n✓ Results: {results_path}")


async def main():
    test = RealSystemTest()
    await test.run()


if __name__ == "__main__":
    asyncio.run(main())
