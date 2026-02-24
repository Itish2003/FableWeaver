# Kudou Kageaki - FableWeaver System Test Suite

## Overview

This test suite uses the **Kudou Kageaki character framework** to identify gaps in the FableWeaver system and drive targeted improvements. The character presents unique challenges that expose system limitations:

- **Restraint Meter**: Numeric containment tracking (core narrative mechanic)
- **Ambient Effects**: State-driven narrative propagation
- **Power Scaling**: Consistent feat tracking against canonical benchmarks
- **Cumulative State**: Persistent adaptation ledger across chapters
- **Emotional Triggers**: Automatic response systems
- **Narrative Constraints**: Forbidden development enforcement

---

## Files Included

### 1. `kudou_test_dataset.json`
**Comprehensive character dataset** including:
- Full World Bible entry for Kageaki
- Dual power systems (CSM + TST) with detailed mechanics
- Restraint profile with cost calculations
- Adaptation ledger structure
- 8 numbered test scenarios with validation criteria
- System improvement targets (high/medium priority)

**Usage:** Load this into the World Bible system to initialize Kageaki's story context.

### 2. `kudou_test_plan.md`
**Detailed test execution playbook** including:
- 5 test phases (Baseline → Combat → Persistence → Validation)
- 8 specific test scenarios with expected outputs
- Validation criteria for each test
- System gaps identified at each phase
- Priority matrix of required improvements
- Success criteria for system readiness

**Usage:** Follow this guide to manually execute tests and document system behavior.

### 3. `KUDOU_SYSTEM_TEST_README.md` (this file)
**Meta-documentation** explaining the overall test strategy.

---

## Quick Start: Execute Phase 1

### Step 1: Load Test Dataset

```json
// Load kudou_test_dataset.json into World Bible
POST /stories/{story_id}/bible
Body: kudou_test_dataset.json
```

### Step 2: Generate Enrollment Scene

**Prompt to Storyteller:**
```
Write the first day of Kudou Kageaki at First High School.
Emphasis: His reserved personality, avoidance of power display,
observation of peers. Set restraint baseline at 100.
Include: subtle hints of hidden capability without actual power display.
Include: acknowledgment of relationship with Minoru (if mentioned).
Establish: the containment/restraint premise of the character.

World context: He's the Designated Heir of the Kudou Family, a hybrid
cursed spirit + Ten Shadows user, deliberately restrained and protected
by family authority. This is his official enrollment as a normal student.
```

### Step 3: Validate Output

**Check Against Criteria:**
- [ ] Scene avoids casual power deployment
- [ ] Personality consistent with "calm, watchful, emotionally muted"
- [ ] Establishes reserved demeanor despite capability
- [ ] Sets up Minoru relationship (if present in scene)

### Step 4: Document Results

**Log in `test_results.md`:**
```markdown
## Phase 1.1: Enrollment Scene

**Status:** PASS / FAIL

**Observations:**
- [What the Storyteller generated]

**Gaps Identified:**
- [What didn't work as expected]

**System Readiness:** TBD
```

---

## Expected System Gaps (Pre-Test)

### HIGH PRIORITY (Blocks Narrative)

1. **❌ Restraint Meter Tracking**
   - Current: No numeric restraint field exists
   - Needed: Automatic cost calculation and threshold warnings
   - Impact: Can't track "containment degradation" arc

2. **❌ Ambient Effect Generation**
   - Current: Archivist must manually add ambient effects
   - Needed: Auto-generate based on restraint level
   - Impact: Story doesn't feel organic/connected to internal state

3. **❌ Power Usage Cost System**
   - Current: No mechanism to track capability deployment
   - Needed: Calculate `usage% × 1.5` cost automatically
   - Impact: Combat scenes don't reflect restraint consequences

### MEDIUM PRIORITY (Improves Consistency)

4. **❌ Adaptation Ledger Persistence**
   - Current: Schema exists, Storyteller doesn't query it
   - Needed: Automatic context injection about prior adaptations
   - Impact: Mahoraga learns but future chapters don't show it

5. **❌ Power Scaling Validator**
   - Current: Manual validation only
   - Needed: Automatic feat consistency checks
   - Impact: Power creep or inconsistent scaling possible

6. **❌ Emotional Trigger Handlers**
   - Current: Generic emotional responses
   - Needed: Specific trigger conditions (Minoru threatened = -10)
   - Impact: Character responses feel generic, not tailored

7. **❌ Narrative Constraint Enforcement**
   - Current: Documented but not validated
   - Needed: Automatic enforcement of "cannot_develop" rules
   - Impact: Forbidden developments might appear in narrative

---

## Test Execution Workflow

```
Phase 1: Baseline Tests (Scenarios 1-2)
  ↓ IDENTIFIES: Restraint tracking, ambient effects
  ↓
Phase 2: State Tracking (Scenario 3)
  ↓ IDENTIFIES: Cumulative cost calculation, effect propagation
  ↓
Phase 3: Combat & Emotions (Scenarios 4-5)
  ↓ IDENTIFIES: Usage costs, trigger responses, thresholds
  ↓
Phase 4: Persistence (Scenario 6)
  ↓ IDENTIFIES: Ledger queries, historical context
  ↓
Phase 5: Validation (Scenarios 7-8)
  ↓ IDENTIFIES: Scaling checks, constraint enforcement
  ↓
GENERATE SYSTEM IMPROVEMENTS
  ↓
RE-RUN ALL PHASES
  ↓
DOCUMENT READINESS
```

---

## System Improvements Roadmap

### Tier 1: Critical (Must implement)

#### 1a. Restraint Meter System
```python
# Add to power_systems schema:
{
  "restraint_profile": {
    "baseline_restraint": 100,
    "current_restraint": 100,
    "thresholds": {
      "yellow_alert": 50,
      "red_alert": 30,
      "critical": 0
    }
  }
}

# Implement function:
def apply_restraint_cost(character, cost_type, amount):
    cost = COST_MAP[cost_type]  # e.g., "combat" → -2
    character.current_restraint -= cost
    if character.current_restraint <= THRESHOLDS["red_alert"]:
        alert_archivist("RED_ALERT: Restraint critical")
```

#### 1b. Ambient Effect Generator
```python
def generate_ambient_effects(character, restraint_level):
    if restraint_level > 75:
        return None  # No effects
    elif restraint_level > 50:
        return "minor_curse_manifestations"  # Near character
    elif restraint_level > 25:
        return "district_curse_saturation"  # Neighborhood scale
    else:
        return "city_curse_contamination"  # Wide scale

# Inject into Storyteller context:
context["ambient_effects"] = generate_ambient_effects(character)
```

#### 1c. Power Usage Cost Calculator
```python
def calculate_usage_cost(power_deployment_percent):
    return power_deployment_percent * 1.5  # e.g., 25% → -37.5 restraint

# Apply after combat:
deployment = 25  # percent
cost = calculate_usage_cost(deployment)
apply_restraint_cost(character, "power_usage", cost)
```

### Tier 2: Important (Improves consistency)

#### 2a. Adaptation Ledger Query
```python
# Archivist queries Mahoraga adaptations:
adaptations = character.power_systems.secondary.shikigami.mahoraga.adaptations
# Returns: ["psion_interference", "information_erasure", ...]

# Provide to Storyteller:
context["character_history"] = {
    "mahoraga_learned": adaptations,
    "each_adaptation_grants": "advantage_in_future_encounters"
}
```

#### 2b. Emotional Trigger System
```python
EMOTIONAL_TRIGGERS = {
    "minoru_threatened": -10,
    "family_pressure": -5,
    "combat_conflict": -2,
}

def check_emotional_triggers(chapter_events):
    for event in chapter_events:
        if event in EMOTIONAL_TRIGGERS:
            cost = EMOTIONAL_TRIGGERS[event]
            apply_restraint_cost(character, "emotion", cost)
```

---

## Expected Outcomes

### After Phase 1 (Baseline Tests)
**System Readiness: 20%**
- ✅ Personality consistency confirmed
- ❌ Restraint tracking not implemented
- ❌ Ambient effects not generated

### After Phase 3 (Tier 1 Fixes Implemented)
**System Readiness: 65%**
- ✅ Restraint meter working
- ✅ Ambient effects auto-generated
- ✅ Power usage costs applied
- ✅ Combat scenarios maintain consistency
- ❌ Adaptation ledger not referenced
- ❌ Scaling validation missing

### After Phase 5 (All Fixes Implemented)
**System Readiness: 90%+**
- ✅ Full restraint tracking
- ✅ Ambient effects
- ✅ Usage costs
- ✅ Adaptation persistence
- ✅ Scaling validation
- ✅ Constraint enforcement
- ⚠️ Manual fine-tuning may still be needed

---

## How to Use These Tests

### For Researchers / System Designers
1. Read `kudou_test_plan.md` to understand system limitations
2. Use as spec for implementing missing features
3. Re-run tests to validate improvements

### For Narrative Writers
1. Load `kudou_test_dataset.json` into World Bible
2. Follow `kudou_test_plan.md` scenarios to generate test chapters
3. Document how well the system maintains character consistency

### For System Implementers
1. Study the gap analysis in this README
2. Implement Tier 1 fixes first
3. Re-run Phase 1-3 to verify
4. Implement Tier 2 fixes
5. Run full test suite

---

## Next Actions

- [ ] Load kudou_test_dataset.json into World Bible
- [ ] Execute Phase 1 test (enrollment scene)
- [ ] Document results in test_results.md
- [ ] Identify critical gaps
- [ ] Implement Tier 1 system improvements
- [ ] Re-run Phase 1-3
- [ ] Implement Tier 2 improvements
- [ ] Run all phases
- [ ] Generate final readiness report

---

## Contact / Notes

This test suite exposes fundamental gaps in how the system handles:
- **Numeric state tracking** (restraint meter)
- **Emotional consequence propagation** (ambient effects)
- **Cumulative learning systems** (adaptation ledger)
- **Narrative constraint enforcement** (forbidden developments)

These improvements will benefit ALL characters with complex internal states or multi-chapter arcs, not just Kudou Kageaki.

**Estimated Implementation Time:** 2-4 hours for Tier 1, 2-3 hours for Tier 2

---

*Test Suite Created: 2026-02-24*
*Character: Kudou Kageaki (Kudou Elder Brother)*
*Framework: Jujutsu Kaisen × The Irregular at Magic High School*
