# Kudou Kageaki Test Suite - Complete Guide

## What Has Been Created

You now have a **complete system testing infrastructure** designed to expose and drive improvements to FableWeaver's character handling capabilities. The test suite uses the Kudou Kageaki character framework (Jujutsu Kaisen × The Irregular at Magic High School crossover) to test advanced narrative mechanics.

---

## Files Overview

### 1. **kudou_test_dataset.json** (Character Data)
- **600+ lines** of structured character data
- Complete World Bible entry for Kudou Kageaki
- Dual power systems: Cursed Spirit Manipulation (CSM) + Ten Shadows Technique (TST)
- Restraint profile with emotional stress costs
- Adaptation ledger for Mahoraga learning
- 8 detailed test scenarios with validation criteria
- **Usage**: Load this into the World Bible system to set up test story context

### 2. **kudou_test_plan.md** (Test Execution Playbook)
- **5 test phases** with specific scenarios
- Phase 1: Baseline Tests (Enrollment + Classroom Conflict)
- Phase 2: State Tracking (Cumulative Stress)
- Phase 3: Combat & Scaling (Power Usage + Emotional Triggers)
- Phase 4: Persistence (Adaptation Ledger)
- Phase 5: Validation (Power Scaling + Constraints)
- 8 test scenarios with success criteria
- System improvement matrix
- **Usage**: Reference guide for understanding what's being tested

### 3. **KUDOU_SYSTEM_TEST_README.md** (Meta Documentation)
- Overview of test strategy and objectives
- Expected system gaps (7 items)
- Quick start guide for Phase 1
- Tier 1 and Tier 2 improvement recommendations
- Expected outcomes at each phase
- System readiness assessment framework
- **Usage**: Strategic overview before diving into details

### 4. **PHASE_1_EXECUTION_GUIDE.md** (Manual Test Guide) ⭐ START HERE
- **Step-by-step Phase 1 execution** (new!)
- Exact API calls: REST endpoints + WebSocket payloads
- Success criteria checklists for each test
- PASS/FAIL validation examples
- Troubleshooting guide
- Results documentation template
- **Usage**: Follow this guide to manually execute Phase 1 tests

### 5. **SYSTEM_GAP_ANALYSIS.md** (Implementation Roadmap) ⭐ CRITICAL
- **Comprehensive analysis of 7 system gaps**
- Each gap includes:
  - Problem statement
  - Impact analysis
  - Complete solution code (Python)
  - Integration points
  - Testing strategy
- Tier 1 (4-6 hours): Restraint, Ambient, Cost
- Tier 2 (5-8 hours): Adaptation, Triggers, Scaling, Constraints
- Time estimates and implementation priority
- Benefits for all characters with persistent state
- **Usage**: Reference guide for development team

### 6. **test_runner.py** (Automated Test Framework)
- Python script for automated Phase 1 execution
- Creates test story and loads World Bible
- Generates enrollment scene + classroom conflict
- Validates against success criteria
- Outputs results to JSON
- Mock response generation for offline testing
- **Usage**: `python tests/test_runner.py --phase 1`

---

## Quick Start Path

### For Researchers / System Designers
1. Read **SYSTEM_GAP_ANALYSIS.md** (30 minutes)
2. Understand the 7 gaps and their impact
3. Review time estimates and implementation roadmap
4. Decide which gaps to prioritize

### For Testers
1. Read **PHASE_1_EXECUTION_GUIDE.md** (15 minutes)
2. Create a test story via API
3. Load kudou_test_dataset.json into World Bible
4. Execute Phase 1 tests (Enrollment + Classroom Conflict)
5. Document results using provided template
6. Proceed to Phase 2 guide

### For Developers
1. Read **SYSTEM_GAP_ANALYSIS.md** (45 minutes)
2. Focus on "Solution Required" sections for each gap
3. Implement Tier 1 gaps first (critical path)
4. Re-run Phase 1 tests to validate
5. Implement Tier 2 gaps
6. Run full test suite

---

## System Gaps Identified

### HIGH PRIORITY (Blocks Narrative Flow)

#### 1. **Restraint Meter Tracking**
- **Problem**: No numeric restraint field; manual tracking required
- **Impact**: Cannot track containment degradation arc
- **Time to Fix**: 2-3 hours
- **Blocks**: Gaps 2, 3, 4, 5

#### 2. **Ambient Effect Generation**
- **Problem**: No auto-generation based on restraint level
- **Impact**: Story doesn't feel organic/connected to character state
- **Time to Fix**: 1.5-2 hours
- **Depends on**: Gap 1

#### 3. **Power Usage Cost System**
- **Problem**: No mechanism to track capability deployment percentage
- **Impact**: Combat power usage doesn't deduct restraint
- **Time to Fix**: 1 hour
- **Depends on**: Gap 1

### MEDIUM PRIORITY (Improves Consistency)

#### 4. **Adaptation Ledger Persistence**
- **Problem**: Schema exists but Storyteller doesn't query it
- **Impact**: Mahoraga learns but future chapters don't show it
- **Time to Fix**: 1 hour

#### 5. **Emotional Trigger Handlers**
- **Problem**: Generic responses; no specific trigger conditions
- **Impact**: Character responses feel generic, not tailored
- **Time to Fix**: 1.5 hours

#### 6. **Power Scaling Validator**
- **Problem**: Manual validation only; no canonical consistency checks
- **Impact**: Power creep or inconsistent scaling possible
- **Time to Fix**: 2-3 hours

#### 7. **Narrative Constraint Enforcement**
- **Problem**: Documented but not validated
- **Impact**: Forbidden developments might appear in narrative
- **Time to Fix**: 1-1.5 hours

---

## Expected Test Outcomes

### Phase 1: Baseline Tests (20-35% readiness)
**Objective**: Establish baseline personality consistency

Tests:
- ✓ Enrollment Scene (quiet, watchful, no power display)
- ✓ Classroom Conflict (verbal response, no escalation)

Expected Gaps Exposed:
- No restraint meter tracking
- No ambient effect generation
- No automatic state management

---

### Phase 2: State Tracking (30-50% readiness)
**Objective**: Test cumulative restraint degradation

Tests:
- Cumulative stress: 100 → 90 restraint over 3 events
- Ambient effect scaling with restraint level

Expected Gaps Exposed:
- Cannot track cumulative costs
- No automatic ambient effect generation

---

### Phase 3: Combat & Emotional (50-70% readiness)
**Objective**: Test power usage costs and emotional triggers

Tests:
- Combat: 25% power deployment = -37.5 restraint
- Emotional: Minoru threatened = -10 restraint
- Threshold warnings at yellow/red alert

Expected Gaps Exposed:
- No usage cost calculator
- No emotional trigger system
- No threshold warnings

---

### Phase 4: Persistence (70-80% readiness)
**Objective**: Test cumulative learning across chapters

Tests:
- Mahoraga adapts to psion-based technique
- Future encounter shows adaptation advantage

Expected Gaps Exposed:
- Adaptation ledger not queried
- No historical context provision

---

### Phase 5: Validation (80-90%+ readiness)
**Objective**: Test power scaling and constraint enforcement

Tests:
- Nue deployment consistency vs canon
- Domain Expansion development blocked

Expected Gaps Exposed:
- No scaling validator
- No constraint enforcement

---

## Next Steps

### Immediate (Today)
1. ✅ **Test infrastructure created** (you are here)
2. Read **PHASE_1_EXECUTION_GUIDE.md** (15 minutes)
3. Create test story and load Kudou dataset
4. Execute Phase 1 tests

### Short Term (This Week)
1. Document Phase 1 results
2. Review **SYSTEM_GAP_ANALYSIS.md**
3. Prioritize gaps to implement
4. Begin Tier 1 implementation

### Medium Term (This Sprint)
1. Implement Tier 1 gaps (Restraint, Ambient, Cost)
2. Re-run Phase 1-3 tests
3. Validate improvements
4. Implement Tier 2 gaps

### Long Term (Full System Readiness)
1. Execute all 5 test phases
2. Achieve 90%+ system readiness
3. Apply patterns to other complex characters
4. Build character framework library

---

## Key Insights

### This Test Suite Solves:
✅ **Systematic gap identification** - No more guessing what's missing
✅ **Prioritized roadmap** - Clear implementation order
✅ **Measurable progress** - Each phase shows improvement %
✅ **Reusable framework** - Works for any character with persistent state
✅ **Canon consistency** - Validates power scaling and constraints

### Why This Matters:
- These gaps prevent proper handling of **all complex characters**
- Restraint/stress/corruption systems apply to many narratives
- Emotional trigger systems improve character authenticity
- Adaptation/learning systems enable character growth
- Constraint enforcement prevents canon violations

### Benefits Beyond Kudou:
- **Persistent state**: Injury, madness, corruption tracking
- **Environmental effects**: Aura, presence, contamination
- **Learning systems**: Evolution, adaptation, growth
- **Emotional responses**: Character-specific triggers
- **Power constraints**: Forbidden/required developments

---

## File Locations

```
/Users/itish/Downloads/Fable/tests/
├── kudou_test_dataset.json           (Character data)
├── kudou_test_plan.md                (Execution plan)
├── KUDOU_SYSTEM_TEST_README.md       (Meta documentation)
├── PHASE_1_EXECUTION_GUIDE.md        (Manual test guide) ⭐ START HERE
├── SYSTEM_GAP_ANALYSIS.md            (Implementation roadmap) ⭐ CRITICAL
├── test_runner.py                    (Automated runner)
└── README_TEST_SUITE.md              (This file)
```

---

## Usage Examples

### Manual Phase 1 Execution
```bash
# 1. Create test story
curl -X POST http://localhost:8000/stories \
  -H "Content-Type: application/json" \
  -d '{"title": "[TEST] Kudou Kageaki - Containment Arc Test Suite"}'

# 2. Load World Bible
curl -X PATCH http://localhost:8000/stories/$STORY_ID/bible \
  -H "Content-Type: application/json" \
  -d @tests/kudou_test_dataset.json

# 3. Connect WebSocket and send test prompts
ws = new WebSocket('ws://localhost:8000/ws/$STORY_ID')
ws.send(JSON.stringify({action: "choice", payload: {choice: "...prompt..."}}))

# 4. Validate results against PHASE_1_EXECUTION_GUIDE.md criteria
```

### Automated Phase 1 Execution
```bash
python tests/test_runner.py --phase 1 --verbose
# Outputs: tests/test_results.json
```

---

## Support & Troubleshooting

### Common Issues

**Q: "Story creation fails with 404"**
A: Ensure server is running: `ps aux | grep uvicorn`

**Q: "World Bible won't load"**
A: Check JSON format: `jq . tests/kudou_test_dataset.json`

**Q: "WebSocket connection refused"**
A: Verify route: `/ws/{story_id}` and check firewall

### Getting Help
- Reference **SYSTEM_GAP_ANALYSIS.md** for implementation questions
- Check **PHASE_1_EXECUTION_GUIDE.md** troubleshooting section
- Review **kudou_test_plan.md** for test specifications

---

## Summary

You now have:

✅ **Complete test infrastructure** for systematic system improvement
✅ **Manual execution guide** for Phase 1 testing
✅ **Comprehensive gap analysis** with solution code
✅ **Prioritized implementation roadmap** (9-14 hours total)
✅ **Measurable progress tracking** via 5 test phases
✅ **Reusable framework** for other complex characters

**Next action**: Read `PHASE_1_EXECUTION_GUIDE.md` and execute Phase 1 tests to establish baseline behavior and identify critical gaps.

---

*Test Suite Created: 2026-02-24*
*Character: Kudou Kageaki (Kudou Elder Brother)*
*Framework: Jujutsu Kaisen × The Irregular at Magic High School*
*Estimated Implementation Time: 9-14 hours for 90%+ system readiness*
