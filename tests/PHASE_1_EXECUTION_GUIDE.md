# Phase 1 Test Execution Guide

## Quick Start: Manual Phase 1 Execution

This guide walks you through executing Phase 1 baseline tests manually. Phase 1 is designed to establish baseline system behavior and identify critical gaps in restraint tracking and ambient effect generation.

---

## Step 1: Create Test Story

### Via API (REST)
```bash
curl -X POST http://localhost:8000/stories \
  -H "Content-Type: application/json" \
  -d '{"title": "[TEST] Kudou Kageaki - Containment Arc Test Suite"}'
```

**Response:**
```json
{
  "id": "story_12345",
  "title": "[TEST] Kudou Kageaki - Containment Arc Test Suite",
  "updated_at": "2026-02-24T..."
}
```

Save the `story_id` for the next step: `STORY_ID=story_12345`

---

## Step 2: Load Test Dataset into World Bible

### Via API (REST)
```bash
curl -X PATCH http://localhost:8000/stories/$STORY_ID/bible \
  -H "Content-Type: application/json" \
  -d @tests/kudou_test_dataset.json
```

**Verification:**
```bash
curl http://localhost:8000/stories/$STORY_ID/bible
```

Should return the complete Kudou Kageaki World Bible with all character data, power systems, restraint profile, and test scenarios.

---

## Step 3: Connect WebSocket and Execute Test 1.1 (Enrollment Scene)

### WebSocket Connection
```bash
# In browser console or WebSocket client:
ws = new WebSocket('ws://localhost:8000/ws/story_12345')
```

### Send Prompt to Storyteller
```json
{
  "action": "choice",
  "payload": {
    "choice": "Write the first day of Kudou Kageaki at First High School.\n\nEMPHASIS:\n- Reserved personality, avoidance of power display\n- Observation of peers\n- Set restraint baseline at 100\n- Include: subtle hints of hidden capability without actual power display\n- Include: acknowledgment of relationship with Minoru (if mentioned)\n- Establish: the containment/restraint premise of the character\n\nWORLD CONTEXT:\nHe's the Designated Heir of the Kudou Family, a hybrid cursed spirit + Ten Shadows user,\ndeliberately restrained and protected by family authority. This is his official enrollment\nas a normal student."
  }
}
```

### Capture Response
The Storyteller will stream the narrative. Capture the full output.

**Expected Duration:** 30-60 seconds

---

## Step 4: Validate Test 1.1 Against Criteria

### Success Criteria Checklist

**Criterion 1: NO POWER CREEP**
- ✅ Does the narrative describe power deployment? (Should be NO)
- ✅ Power keywords to avoid: "deployed," "released," "manifested," "summoned"
- ✅ It's OK if these words appear in world-building/dialogue, but not in action descriptions

**Example PASS:**
> "Kageaki entered First High calmly, observing students with quiet attention. **He could sense** the magical currents around him, but **he showed nothing**."

**Example FAIL:**
> "Kageaki entered First High and **released a Nue shikigami** to scout the campus..."

---

**Criterion 2: PERSONALITY CONSISTENCY**
- ✅ Does Kageaki display emotional restraint?
- ✅ Look for: "calm," "composed," "controlled," "quiet," "measured," "restrained"
- ✅ Should NOT show casual arrogance or aggressive behavior

**Example PASS:**
> "His voice was quiet and measured. He answered the teacher's question with precision but without pride."

**Example FAIL:**
> "Kageaki laughed loudly and announced his superiority to the class."

---

**Criterion 3: CAPABILITY HINTS**
- ✅ Does the narrative hint at hidden strength?
- ✅ Look for: "watchful," "intelligent," "capable," "observant," "efficient"
- ✅ These should be **character trait hints**, not **power demonstrations**

**Example PASS:**
> "His eyes tracked everything—exits, power sources, potential threats. Someone trained. Someone dangerous."

**Example FAIL:**
> "Kageaki stood up and lifted a desk with one finger to show his strength."

---

**Criterion 4: MINORU RELATIONSHIP**
- ✅ Is Minoru mentioned? (Context-dependent, but good sign if present)
- ✅ How is the relationship characterized?
- ✅ Should show protective concern, not romantic/friendship idealization

**Example PASS:**
> "He noticed Minoru among the first-year students and maintained discreet observation."

---

### Test 1.1 Result

**Record:**
```markdown
## Test 1.1: Enrollment Scene

| Criterion | Result | Notes |
|-----------|--------|-------|
| No Power Creep | ✅ PASS / ❌ FAIL | [Specific examples from narrative] |
| Personality Consistency | ✅ PASS / ❌ FAIL | [Quotes demonstrating restraint/composition] |
| Capability Hints | ✅ PASS / ❌ FAIL | [How capability is hinted without deployment] |
| Minoru Relationship | ✅ PASS / ❌ FAIL | [How is Minoru referenced] |

**Overall Status:** PASS / FAIL
**Word Count:** [actual count]
```

---

## Step 5: Execute Test 1.2 (Classroom Conflict)

### Send Prompt to Storyteller
```json
{
  "action": "choice",
  "payload": {
    "choice": "A classmate made an ill-considered comment about Kudou Kageaki's quiet demeanor,\nsuggesting he is 'too boring' for prestigious Course 1.\n\nKageaki responds verbally but does not escalate to power use.\n\nCONSTRAINTS:\n- Verbal response only, no power deployment\n- Maintains composure and emotional restraint\n- No supernatural elements manifest\n- Conflict resolved within normal social bounds\n\nWORLD CONTEXT:\nCurrent restraint: 100 (unchanged from baseline)\nThis is a test of personality-driven conflict resolution without power escalation.\nLog: Combat conflict cost -2 restraint (manual tracking)\nUpdated restraint: 98"
  }
}
```

### Capture Response

**Expected Duration:** 30-60 seconds

---

## Step 6: Validate Test 1.2 Against Criteria

### Success Criteria Checklist

**Criterion 1: VERBAL RESPONSE ONLY**
- ✅ Does Kageaki respond verbally?
- ✅ Look for: "replied," "said," "responded," "answered," "spoke," "commented"
- ✅ Should show verbal wit/intelligence, NOT physical intimidation

**Example PASS:**
> "'Too boring,' he replied calmly. 'Quiet observation is more efficient than constant noise.'"

**Example FAIL:**
> "Kageaki grabbed the student by the collar and lifted him off the ground..."

---

**Criterion 2: NO POWER DEPLOYMENT**
- ✅ Does the conflict escalate to supernatural power use?
- ✅ Same power keywords as Criterion 1 of Test 1.1
- ✅ Even a subtle manifestation (curse aura, energy leak) = FAIL

**Example PASS:**
> "Kageaki's response was delivered with the precise coldness of someone in control."

**Example FAIL:**
> "A wave of curse energy pulsed from Kageaki, silencing the room."

---

**Criterion 3: COMPOSURE MAINTAINED**
- ✅ Does Kageaki remain emotionally restrained throughout?
- ✅ Should NOT show anger, fear, or other emotional extremes
- ✅ Response should be calculated, not reactive

**Example PASS:**
> "He held the classmate's gaze for a moment longer, then returned to his meal without further comment."

**Example FAIL:**
> "Kageaki's face flushed with anger as he glared at the student..."

---

**Criterion 4: NO AMBIENT EFFECTS**
- ✅ Do supernatural effects manifest in the environment?
- ✅ Look for: "curse aura," "spiritual pressure," "energy leak," "contamination," "manifestation"
- ✅ At restraint 100, ambient effects should be ZERO

**Example PASS:**
> "The classroom remained unchanged—no hint of supernatural presence."

**Example FAIL:**
> "The fluorescent lights flickered, and students felt an inexplicable chill..."

---

### Test 1.2 Result

**Record:**
```markdown
## Test 1.2: Classroom Conflict

| Criterion | Result | Notes |
|-----------|--------|-------|
| Verbal Response Only | ✅ PASS / ❌ FAIL | [Dialogue examples] |
| No Power Deployment | ✅ PASS / ❌ FAIL | [Absence of power keywords] |
| Composure Maintained | ✅ PASS / ❌ FAIL | [Evidence of emotional control] |
| No Ambient Effects | ✅ PASS / ❌ FAIL | [Clean environment, no supernatural manifestations] |

**Overall Status:** PASS / FAIL
**Word Count:** [actual count]
```

---

## Step 7: Document Phase 1 Results

### Summary Template

```markdown
# Phase 1 Test Execution Results

**Execution Date:** 2026-02-24
**Tester:** [Your Name]
**API Status:** Online
**Story ID:** [STORY_ID]

## Test 1.1: Enrollment Scene

**Overall Result:** PASS / FAIL
**Scenarios Passed:** 4/4 criteria

[Full results from Step 4]

## Test 1.2: Classroom Conflict

**Overall Result:** PASS / FAIL
**Scenarios Passed:** 4/4 criteria

[Full results from Step 6]

## Phase 1 Summary

**Total Tests:** 2
**Tests Passed:** 2/2 or [X/2]

### Gaps Identified

Based on Phase 1 execution, the following system gaps were identified:

- **Restraint Meter Tracking** (HIGH): No numeric restraint field exists in character data
- **Ambient Effect Generation** (HIGH): No automatic effect propagation based on restraint level
- **Manual State Tracking** (MEDIUM): Archivist must manually track restraint changes (-2 logged manually, not auto-applied)

### Next Steps

Phase 2 will test cumulative restraint degradation and ambient effect propagation by sending:
- Day 1: Family meeting (-5 restraint)
- Day 2: Minoru struggling (-3 restraint)
- Day 3: Threat to Kudou interests (-2 restraint)
- Cumulative: 100 → 90 restraint

Expected to expose:
- Lack of ambient effect scaling system
- No automatic cost application mechanism

### Estimated System Readiness After Phase 1

- **Baseline:** 20% (system can handle basic personality scenes)
- **If all tests pass:** 35-40% (adds character consistency validation)
- **Critical gaps remain:** Restraint tracking, ambient effects, emotional triggers
```

---

## Expected Phase 1 Outcome

### If All Tests PASS (Best Case)
- ✅ System can generate personality-consistent narrative
- ✅ Power escalation is avoided appropriately
- ✅ Character relationships are referenced naturally
- ⚠️ But: No automatic restraint tracking, no ambient effects, manual state management required

### If Tests Partially FAIL (Likely Case)
- ✅ Personality may be mostly consistent
- ❌ May include casual power deployment that shouldn't happen
- ❌ Minoru relationship may not be referenced
- ❌ Ambient effects may appear despite high restraint level

### Critical Gaps Phase 1 Exposes

1. **No Restraint Meter System**
   - Archivist cannot track numeric restraint value
   - Cannot apply costs automatically
   - Cannot warn at thresholds (yellow/red alert)

2. **No Ambient Effect Generator**
   - Storyteller doesn't know restraint level affects environment
   - Cannot generate scaled supernatural manifestations
   - No system for "minor" vs "district-level" contamination

3. **No Power Deployment Cost Calculator**
   - Combat power usage not tracked numerically
   - Cannot calculate `usage% × 1.5` cost automatically
   - No mechanism for restraint degradation during power escalation

---

## Moving to Phase 2

Once Phase 1 is complete:
1. Document all gaps in `tests/test_results.json`
2. Proceed to Phase 2: State Tracking Tests
3. Phase 2 will test cumulative stress and restraint degradation
4. Expected to further expose ambient effect generation gaps

---

## Troubleshooting

### Story Creation Fails
```
Error: 404 Not Found
```
- Verify server is running: `ps aux | grep uvicorn`
- Check API is accessible: `curl http://localhost:8000/stories`

### World Bible Won't Load
```
Error: Failed to load World Bible
```
- Verify test_dataset.json format: `jq . tests/kudou_test_dataset.json`
- Check story_id is correct
- Verify PATCH endpoint: `curl -X PATCH http://localhost:8000/stories/{story_id}/bible`

### WebSocket Connection Fails
```
Error: WebSocket connection refused
```
- Verify WebSocket route: `/ws/{story_id}`
- Check firewall/network issues
- Try from browser console first

### Storyteller Not Responding
- Check API key configuration in `.env`
- Verify `GOOGLE_API_KEYS` is set
- Check server logs: `.venv/bin/tail -f logs/fable.log`

---

## Next: Phase 2 Execution

After Phase 1 is complete and results are documented, proceed to `PHASE_2_EXECUTION_GUIDE.md` to test cumulative restraint degradation and ambient effect scaling.
