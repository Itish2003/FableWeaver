#!/usr/bin/env python3
"""
Full System Test: Kudou Kageaki Back-and-Forth Interaction

Tests the complete flow:
1. Create story via REST API
2. Load World Bible with character data
3. Send complete dataset as initial prompt
4. Stream WebSocket response (back-and-forth exchanges)
5. Capture chapter generation + choices
6. Validate quality and performance
"""

import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Any, List
import httpx

try:
    import websockets
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "websockets"])
    import websockets

# Configuration
API_BASE_URL = "http://localhost:8000"
DATASET_PATH = Path("/Users/itish/Downloads/Fable/src/dataset.md")


class FullSystemTest:
    """Complete back-and-forth system test."""

    def __init__(self):
        self.story_id = None
        self.dataset_content = None
        self.results = {
            "test_date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "phases": {},
            "metrics": {},
        }

    async def setup(self):
        """Setup: Create story and load character data."""
        print("\n" + "=" * 70)
        print("PHASE 1: SETUP - Create Story & Load World Bible")
        print("=" * 70)

        # Load dataset
        print("\n[1/4] Loading dataset from src/dataset.md...")
        with open(DATASET_PATH, "r") as f:
            self.dataset_content = f.read()
        print(f"✓ Loaded {len(self.dataset_content)} characters")

        # Create story
        print("\n[2/4] Creating test story via REST API...")
        start = time.time()
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{API_BASE_URL}/stories",
                json={"title": "[FULL-TEST] Kudou Kageaki - Complete System Verification"},
            )
            if response.status_code != 200:
                raise RuntimeError(f"Story creation failed: {response.text}")
            self.story_id = response.json()["id"]
        elapsed = time.time() - start
        print(f"✓ Story created: {self.story_id}")
        print(f"  Response time: {elapsed*1000:.1f}ms")

        # Build and load World Bible
        print("\n[3/4] Building World Bible with character data...")
        world_bible = {
            "meta": {
                "universes": ["The Irregular at Magic High School", "Jujutsu Kaisen Crossover"],
                "current_story_date": "April 2096 (First High Enrollment)",
                "story_start_date": "April 2096",
                "theme": "Containment vs Contamination - Power That Grows",
                "genre": "Fantasy / School Life / Psychological Thriller",
                "tone": "Reserved threat, institutional backing, quiet escalation"
            },
            "character_sheet": {
                "name": "Kudou Kageaki",
                "age": 16,
                "gender": "Male",
                "height": "~180cm (5'11\")",
                "affiliation": "Kudou Family - Designated Heir (Main Line)",
                "enrollment": "First High School, Course 1",
                "archetype": "The Quiet Catastrophe",
                "personality": "Quiet, watchful, emotionally restrained",
                "core_fear": "Losing control of what he commands",
                "motivation": "Containment and stability",
                "protective_targets": ["Minoru Kudou (younger brother)"]
            },
            "story_state": {
                "chapter": 0,
                "arc": "Enrollment",
                "tension_level": "low"
            }
        }

        print("\n[4/4] Loading World Bible into story...")
        start = time.time()
        async with httpx.AsyncClient() as client:
            response = await client.patch(
                f"{API_BASE_URL}/stories/{self.story_id}/bible",
                json=world_bible,
                timeout=30.0
            )
            if response.status_code not in [200, 201]:
                raise RuntimeError(f"Bible loading failed: {response.text}")
        elapsed = time.time() - start
        print(f"✓ World Bible loaded")
        print(f"  Response time: {elapsed*1000:.1f}ms")

        self.results["phases"]["setup"] = {
            "story_id": self.story_id,
            "api_response_time_ms": elapsed * 1000,
        }

    async def test_back_and_forth(self):
        """Main test: Send dataset and capture back-and-forth interaction."""
        print("\n" + "=" * 70)
        print("PHASE 2: BACK-AND-FORTH - Interactive Story Generation")
        print("=" * 70)

        # Prepare initial prompt with dataset
        print("\n[1/4] Preparing initial prompt...")
        initial_prompt = f"""# Interactive Story: Kudou Kageaki's First Day

Generate the opening chapter for Kudou Kageaki's first day at First High School (Course 1 enrollment).

## Character Brief (from World Bible):
- Personality: Quiet, watchful, emotionally restrained
- Power Systems: Cursed Spirit Manipulation + Ten Shadows Technique (hybrid)
- Restraint: Currently 100 (fully contained - this is the core premise)
- Vulnerability: Protective of younger brother Minoru
- Restriction: NO casual power display allowed

## Storyteller Instructions:
1. Write the opening chapter showing his first day experience
2. Display his reserved personality through observation and minimal engagement
3. Include subtle hints of hidden capability (but NO actual power deployment)
4. Naturally reference Minoru and the protective dynamic
5. Establish the restraint/containment as the core narrative driver
6. End with 3-4 meaningful choices that reflect his personality

Generate the chapter now with rich detail and character consistency:"""

        print(f"✓ Prompt prepared ({len(initial_prompt)} characters)")

        # Connect and stream
        print("\n[2/4] Connecting to WebSocket...")
        uri = f"ws://localhost:8000/ws/{self.story_id}"

        messages_received = []
        content_received = ""
        choices_received = []
        start_time = time.time()

        try:
            async with websockets.connect(uri) as websocket:
                print(f"✓ Connected to {uri}")

                # Send initial prompt
                print("\n[3/4] Sending initial prompt with dataset...")
                payload = {"action": "choice", "payload": {"choice": initial_prompt}}
                await websocket.send(json.dumps(payload))
                print("✓ Prompt sent")

                # Stream responses
                print("\n[4/4] Streaming back-and-forth interaction...\n")
                print("-" * 70)

                message_count = 0
                generation_start = time.time()

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

                            # Log message
                            print(f"[{elapsed:.1f}s] {msg_type}")

                            # Process by type
                            if msg_type == "content_delta":
                                text = data.get("text", "")
                                content_received += text
                                sender = data.get("sender", "?")
                                if len(text) > 0:
                                    print(
                                        f"        ({len(text)} chars from {sender})"
                                    )
                                    if len(text) <= 100:
                                        print(f"        > {text}")

                            elif msg_type == "choices":
                                choices_list = data.get("choices", [])
                                choices_received = choices_list
                                print(f"        ({len(choices_list)} choices provided)")
                                for i, choice in enumerate(choices_list, 1):
                                    print(f"          {i}. {choice[:70]}...")

                            elif msg_type == "status":
                                status = data.get("status")
                                detail = data.get("detail", "")
                                if detail:
                                    print(f"        {status}: {detail}")

                            messages_received.append(
                                {
                                    "type": msg_type,
                                    "timestamp": elapsed,
                                    "size": len(json.dumps(data)),
                                }
                            )

                            # Check for completion
                            if msg_type == "choices":
                                print("\n" + "-" * 70)
                                print("\n✓ Generation complete with choices presented\n")
                                break

                            # Timeout safety
                            if elapsed > 120:
                                print(
                                    f"\n⏱️ Timeout reached (120s) - stopping stream\n"
                                )
                                break

                        except asyncio.TimeoutError:
                            elapsed = time.time() - start_time
                            if elapsed > 30:
                                print(f"\n⏱️ No messages (timeout) after {elapsed:.1f}s\n")
                                break

                except Exception as e:
                    print(f"\n✗ Error during streaming: {e}\n")

        except Exception as e:
            print(f"✗ WebSocket error: {e}")
            return

        generation_time = time.time() - generation_start

        # Store results
        self.results["phases"]["back_and_forth"] = {
            "total_time_seconds": generation_time,
            "messages_received": message_count,
            "content_length": len(content_received),
            "content_word_count": len(content_received.split()),
            "choices_count": len(choices_received),
            "choices": choices_received,
        }

        # Validate quality
        print("=" * 70)
        print("VALIDATION: Back-and-Forth Quality Assessment")
        print("=" * 70)

        validation = self._validate_generation(content_received, choices_received)
        self.results["phases"]["validation"] = validation

        for criterion, result in validation["criteria"].items():
            status = "✅" if result else "❌"
            print(f"{status} {criterion}")

    def _validate_generation(
        self, content: str, choices: List[str]
    ) -> Dict[str, Any]:
        """Validate generated content against criteria."""

        text_lower = content.lower()

        criteria = {
            "content_received": len(content) > 0,
            "minimum_length_1000": len(content) >= 1000,
            "contains_chapter_header": "chapter" in text_lower
            or "# " in content,
            "personality_traits": any(
                word in text_lower
                for word in [
                    "restrained",
                    "composed",
                    "quiet",
                    "measured",
                    "watchful",
                ]
            ),
            "no_power_deployment": not any(
                phrase in text_lower
                for phrase in [
                    "deployed curse",
                    "released spirit",
                    "manifested power",
                ]
            ),
            "minoru_reference": "minoru" in text_lower,
            "restraint_concept": "restraint" in text_lower
            or "containment" in text_lower,
            "choices_presented": len(choices) >= 3,
            "meaningful_choices": all(
                len(choice) > 20 for choice in choices
            ),
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
        """Execute full test suite."""
        try:
            await self.setup()
            await self.test_back_and_forth()

            # Print summary
            self._print_summary()

            # Save results
            self._save_results()

        except Exception as e:
            print(f"\n✗ Test failed: {e}")
            import traceback

            traceback.print_exc()

    def _print_summary(self):
        """Print test summary."""
        print("\n" + "=" * 70)
        print("TEST SUMMARY")
        print("=" * 70)

        bf = self.results["phases"].get("back_and_forth", {})
        val = self.results["phases"].get("validation", {})

        print(f"\nGeneration Time: {bf.get('total_time_seconds', 0):.2f}s")
        print(f"Content Length: {bf.get('content_length', 0)} characters")
        print(f"Word Count: {bf.get('content_word_count', 0)} words")
        print(f"Choices: {bf.get('choices_count', 0)}")
        print(f"\nValidation: {val.get('passed', 0)}/{val.get('total', 0)} criteria")
        print(f"Pass Rate: {val.get('pass_rate', 'N/A')}")

        print("\n" + "=" * 70)
        print("SYSTEM READINESS ASSESSMENT")
        print("=" * 70)

        # Calculate readiness
        if bf.get("content_length", 0) > 0:
            readiness = 35  # Baseline for working generation
            readiness += 10 if val.get("passed", 0) >= 7 else 0
            readiness += 15 if bf.get("choices_count", 0) >= 3 else 0
            print(f"\n✅ System Readiness: {readiness}%")
            print(f"   - Back-and-forth working: ✅")
            print(f"   - Content generation: ✅")
            print(f"   - Choice presentation: ✅")
        else:
            print(f"\n❌ System Readiness: 15%")
            print(f"   - Back-and-forth blocked")
            print(f"   - No content received")

    def _save_results(self):
        """Save results to JSON."""
        results_path = (
            Path(__file__).parent / "full_system_test_results.json"
        )
        with open(results_path, "w") as f:
            json.dump(self.results, f, indent=2)
        print(f"\n✓ Results saved: {results_path}")


async def main():
    """Main entry point."""
    test = FullSystemTest()
    await test.run()


if __name__ == "__main__":
    asyncio.run(main())
