# Kudou Kageaki Test Execution Plan

## Overview

This document outlines how to test the FableWeaver system using the Kudou Kageaki character dataset to identify gaps and drive system improvements.

---

## Test Execution Phases

### Phase 1: Manual Baseline Tests (Scenarios 1-2)

**Objective:** Establish baseline system behavior with simple scenarios

**Test 1.1: Enrollment Scene**
```bash
# Prompt to Storyteller:
"Write the first day of Kudou Kageaki at First High School.
Emphasis: His reserved personality, avoidance of power display,
observation of peers. Set restraint baseline at 100."

# Expected Output:
- Quiet, watchful characterization
- NO casual power deployment
- Acknowledgment of Minoru (if mentioned)
- Establishment of containment premise

# Success Criteria:
- [ ] No power creep in Day 1 scene
- [ ] Personality consistent with "emotionally muted, polite"
- [ ] Setup hints at hidden capability without display
```

**Test 1.2: Classroom Conflict**
```bash
# Prompt to Storyteller:
"A classmate insults Kageaki; he responds verbally but does not
escalate to power use. Log: Combat conflict cost -2 restraint.
Current restraint: 100 → 98"

# Expected Output:
- Verbal response only
- Maintains composure
- No supernatural elements

# Success Criteria:
- [ ] Conflict resolved without power
- [ ] Personality remains restrained
- [ ] NO ambient curse effects triggered
```

**Phase 1 Expected Result:**
- System can handle basic personality-driven scenes
- IDENTIFIES GAP: No automatic restraint tracking

---

### Phase 2: State Tracking Tests (Scenario 3)

**Objective:** Test restraint degradation and ambient effect propagation

**Test 2.1: Cumulative Stress**
```bash
# Prompt to Storyteller + Archivist:
"Chapter sequence:
- Day 1: Family meeting about Kageaki's future (-5 restraint)
- Day 2: Minoru struggling academically (-3 restraint)
- Day 3: Overhear threat to Kudou interests (-2 restraint)

Current restraint: 100 → 90

Generate narrative with ambient manifestations."

# Expected Behavior:
- Restraint tracking system active
- Ambient curse effects generated at restraint 90/100 level
- Minor supernatural activity hinted at

# Success Criteria:
- [ ] System tracks cumulative restraint changes
- [ ] Ambient effects scale appropriately (restraint 90 = minor)
- [ ] Storyteller references effect naturally
- [ ] Archivist validates restraint math
```

**Phase 2 Expected Result:**
- IDENTIFIES GAPS:
  1. No automatic restraint cost tracking
  2. No ambient effect generation system
  3. Storyteller doesn't know to reference restraint level in narrative

---

### Phase 3: Combat & Scaling Tests (Scenarios 4-5)

**Objective:** Test power usage costs and emotional triggers

**Test 3.1: Power Usage Cost**
```bash
# Prompt:
"Kageaki in combat with Course 1 elite. Uses ~25% of capability
to win without revealing full power.
Cost calculation: 25% usage × 1.5 multiplier = -37.5 restraint
Restraint: 90 → 52.5 (YELLOW ALERT)"

# Expected Output:
- Combat scene shows restraint
- Clear narrative strain
- Victory without overkill
- System recognizes YELLOW_ALERT threshold

# Validation:
- [ ] Power usage costs applied correctly
- [ ] Restraint threshold warning triggered
- [ ] Narrative reflects increasing strain
```

**Test 3.2: Minoru Threat Response**
```bash
# Prompt:
"Minoru targeted by outside faction. Kageaki learns of threat.
Emotional response: -10 restraint (brother threatened)
Restraint: 52.5 → 42.5 (RED ALERT - CRITICAL)"

# Expected Output:
- Immediate personality shift
- Cold, efficient response
- Power restraint abandoned
- Rapid action without hesitation

# Validation:
- [ ] Emotional trigger recognized
- [ ] Automatic -10 penalty applied
- [ ] RED_ALERT threshold triggered
- [ ] Narrative reflects personality shift
```

**Phase 3 Expected Result:**
- IDENTIFIES GAPS:
  1. No power usage cost calculation system
  2. No emotional trigger response system
  3. Threshold warnings not implemented
  4. Storyteller doesn't scale to restraint level

---

### Phase 4: Adaptation & Persistence Tests (Scenario 6)

**Objective:** Test cumulative state tracking across chapters

**Test 4.1: Initial Adaptation**
```bash
# Prompt (Chapter 3):
"Mahoraga faces psion-based binding technique. Adapts successfully.
Add to ledger: adaptations: ['psion_interference']"

# Expected:
- [ ] Adaptation logged in World Bible
- [ ] Timestamp recorded
- [ ] Persists to next chapter
```

**Test 4.2: Future Encounter**
```bash
# Prompt (Chapter 8):
"New opponent uses psion-based attack. Mahoraga should show
adaptation advantage from prior learning."

# Expected:
- [ ] Storyteller references prior adaptation
- [ ] Applies -1 difficulty modifier
- [ ] Shows learning/growth narrative
- [ ] Maintains continuity

# Validation:
- [ ] Can query: "What has Mahoraga adapted to?"
- [ ] Answer: ['psion_interference'] ← correct
- [ ] Future encounter respects this
```

**Phase 4 Expected Result:**
- IDENTIFIES GAPS:
  1. Adaptation ledger not queried by Storyteller
  2. No historical context provided to narrative generation
  3. No difficulty modifier system

---

### Phase 5: Validation & Constraint Tests (Scenarios 7-8)

**Objective:** Test power scaling consistency and narrative constraints

**Test 5.1: Feat Consistency**
```bash
# Generated narrative:
"Nue's lightning devastated the stadium, splitting it in two."

# System should validate:
- Nue capability: "skyscraper-scale lightning (JJK canon)"
- Scenario scale: Stadium << Skyscraper ✓
- Validation result: CONSISTENT
- Log: feat_validation PASS

# Failure case:
"Nue's lightning gently singed a wall."
- Expected scale: Skyscraper-level
- Actual deployment: Wall-level
- Validation: INCONSISTENT - FLAG
```

**Test 5.2: Forbidden Technique Check**
```bash
# Pressure scenario:
"Intense 1v5 combat, Kageaki at absolute limit.
Should he develop Domain Expansion?"

# System constraints:
"cannot_develop": ["Domain Expansion (explicitly forbidden by family)"]

# Expected behavior:
- Kageaki does NOT develop domain despite pressure
- Uses maximum non-domain power instead
- Narrative respects constraint
- Archivist validates: "Domain development attempted - BLOCKED"
```

**Phase 5 Expected Result:**
- IDENTIFIES GAPS:
  1. No power scaling validator
  2. No canonical benchmark comparison
  3. No narrative constraint enforcement

---

## Test Execution Matrix

| Phase | Scenario | Status | Gap Type | Priority | Fix Required |
|-------|----------|--------|----------|----------|--------------|
| 1 | Enrollment | TBD | None (baseline) | - | - |
| 1 | Conflict | TBD | Restraint tracking | HIGH | Implement meter |
| 2 | Stress | TBD | State propagation | HIGH | Ambient effects |
| 3 | Combat | TBD | Usage costs | HIGH | Power budget |
| 3 | Emotional | TBD | Trigger response | HIGH | Event handlers |
| 4 | Adaptation | TBD | Persistence | MEDIUM | Ledger query |
| 5 | Scaling | TBD | Validation | MEDIUM | Feat checker |
| 5 | Constraint | TBD | Enforcement | MEDIUM | Rule validator |

---

## System Improvements Required

### Tier 1 (Critical - Blocks Narrative)

1. **Restraint Meter System**
   - [ ] Add numeric restraint field to power_systems
   - [ ] Implement cost function: `restraint -= cost`
   - [ ] Add threshold checks: yellow (50), red (30), critical (0)
   - [ ] Integrate into Archivist validation
   - [ ] Provide to Storyteller in context

2. **Ambient Effect Generator**
   - [ ] Create function: `ambient_effects(restraint_level) → narrative`
   - [ ] Map restraint ranges to manifestation intensity
   - [ ] Auto-inject into Storyteller context
   - [ ] Example: restraint 45 → "District-level curse saturation reported"

3. **Power Usage Cost Calculator**
   - [ ] Track capability deployment percentage
   - [ ] Apply multiplier: `usage % × 1.5`
   - [ ] Deduct from restraint
   - [ ] Log for Archivist validation

### Tier 2 (Important - Improves Consistency)

4. **Adaptation Ledger Query**
   - [ ] Archivist queries: `character.power_systems.secondary.shikigami.mahoraga.adaptations`
   - [ ] Returns: `['psion_interference', ...]`
   - [ ] Provides to Storyteller: "Mahoraga has previously adapted to: [list]"
   - [ ] Storyteller references in narrative

5. **Emotional Trigger System**
   - [ ] Identify trigger conditions: `minoru_threatened`, `family_pressure`, etc.
   - [ ] Automatic cost application when triggered
   - [ ] Personality shift flags for Storyteller
   - [ ] Log for continuity

6. **Power Scaling Validator**
   - [ ] Create feat benchmark database: `{entity, system, capability, scale}`
   - [ ] Archivist checks: "Is this feat consistent with known scaling?"
   - [ ] Flag inconsistencies for review
   - [ ] Example: Nue deployment vs stadium scale

7. **Narrative Constraint Enforcer**
   - [ ] Parse `cannot_develop`, `must_maintain` fields
   - [ ] Flag story violations: "Domain Expansion attempted - violates constraint"
   - [ ] Suggest narrative alternatives
   - [ ] Validation report for each chapter

---

## Success Criteria (Overall)

For the system to be considered "ready" for this character:

- [ ] Restraint meter auto-tracks across all chapters
- [ ] Ambient effects propagate naturally without manual intervention
- [ ] Power usage costs reflect in-story strain and narrative consequences
- [ ] Mahoraga adaptations persist and are referenced in future encounters
- [ ] Power scaling remains consistent with canonical benchmarks
- [ ] Narrative constraints are enforced (no forbidden developments)
- [ ] Storyteller generates coherent arcs driven by restraint degradation
- [ ] Archivist flags all inconsistencies automatically

---

## Next Steps

1. **Execute Phase 1** → Document baseline
2. **Implement Tier 1 fixes** → Restraint + Ambient + Usage costs
3. **Re-run Phase 1-3** → Verify improvements
4. **Implement Tier 2 fixes** → Adaptation + Triggers + Validation
5. **Run all phases** → Full system validation
6. **Generate test report** → Document system readiness

---

## Test Report Template

```
Test Execution: [Date]
Character: Kudou Kageaki
Phases Completed: [1/5, 2/5, etc.]

Scenarios Passed: X/8
Gaps Identified: [list]
Fixes Applied: [list]
Remaining Work: [list]

System Readiness: [0-100%]
```

