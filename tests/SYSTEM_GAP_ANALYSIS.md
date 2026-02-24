# FableWeaver System Gap Analysis: Kudou Kageaki Test Suite

## Executive Summary

The Kudou Kageaki character framework exposes **7 critical system gaps** that prevent proper handling of complex characters with:
- **Numeric state tracking** (restraint meter)
- **Emotional consequence propagation** (ambient effects)
- **Cumulative learning systems** (adaptation ledger)
- **Narrative constraint enforcement** (forbidden developments)

These gaps affect **ALL characters with persistent state**, not just Kudou. This analysis provides a prioritized roadmap for system improvements.

---

## Gap 1: Restraint Meter Tracking (HIGH PRIORITY)

### Current State
**Problem:**
- No numeric restraint field exists in character power systems
- Manual tracking required (e.g., "Archivist logs: -2 restraint")
- No threshold warnings (yellow/red alert)
- No automatic cost application

**Evidence:**
```json
// Current power_systems schema (missing)
"restraint_profile": {
  "baseline_restraint": 100,
  "current_restraint": 100  // ← NOT IN SCHEMA
}
```

### Impact
- **Phase 1 Test**: Cannot validate that restraint stays at 100
- **Phase 2 Test**: Cannot track cumulative stress (-5, -3, -2 = -10 total)
- **Phase 3 Test**: Cannot apply usage costs or trigger thresholds
- **Blocker**: Cannot implement emotional triggers or ambient scaling

### Solution Required

#### 1a. Schema Enhancement (Pydantic Model)
```python
# src/models/power_systems.py

class RestraintProfile(BaseModel):
    """Numeric containment tracking for restrained characters."""
    baseline_restraint: float = 100.0
    current_restraint: float = 100.0

    thresholds: Dict[str, float] = {
        "yellow_alert": 50.0,
        "red_alert": 30.0,
        "critical": 0.0
    }

    # Cost registry for different event types
    cost_map: Dict[str, float] = {
        "combat_engagement": -2.0,
        "family_pressure": -5.0,
        "minoru_threatened": -10.0,
        "power_deployment_base": -1.0,  # × usage%
    }

class PowerSystem(BaseModel):
    """Updated to include restraint tracking."""
    primary: Optional[PrimaryTechnique] = None
    secondary: Optional[SecondaryTechnique] = None
    restraint_profile: Optional[RestraintProfile] = None
```

#### 1b. Cost Application Function
```python
# src/tools/restraint_tools.py

async def apply_restraint_cost(
    story_id: str,
    cost_type: str,
    amount: Optional[float] = None,
    reason: str = ""
) -> Dict[str, Any]:
    """Apply restraint cost and check thresholds."""
    bible = await get_world_bible(story_id)
    restraint_profile = bible["character_sheet"]["power_systems"]["restraint_profile"]

    # Get cost from registry or use provided amount
    cost = amount or restraint_profile["cost_map"].get(cost_type, 0)

    # Apply cost
    current = restraint_profile["current_restraint"]
    restraint_profile["current_restraint"] = max(0, current + cost)

    # Check thresholds
    alert_level = "none"
    if restraint_profile["current_restraint"] <= restraint_profile["thresholds"]["critical"]:
        alert_level = "critical"
    elif restraint_profile["current_restraint"] <= restraint_profile["thresholds"]["red_alert"]:
        alert_level = "red"
    elif restraint_profile["current_restraint"] <= restraint_profile["thresholds"]["yellow_alert"]:
        alert_level = "yellow"

    # Save bible
    await update_world_bible(story_id, {"character_sheet": bible["character_sheet"]})

    return {
        "previous_restraint": current,
        "current_restraint": restraint_profile["current_restraint"],
        "cost_applied": cost,
        "reason": reason,
        "alert_level": alert_level,
    }
```

#### 1c. Integration with Archivist
```python
# In archivist.py or before_storyteller_callback

# After chapter generation, check if any cost events occurred
events_detected = await detect_restraint_events(chapter_content, story_id)
for event in events_detected:
    result = await apply_restraint_cost(
        story_id=story_id,
        cost_type=event["type"],
        reason=event["description"]
    )

    if result["alert_level"] != "none":
        # Log alert to system
        logger.warning(f"Restraint alert: {result['alert_level']} at {result['current_restraint']}")
```

### Testing
- **Phase 1**: Verify restraint stays at 100 after baseline tests
- **Phase 2**: Verify restraint degrades to 90 after cumulative stress
- **Phase 3**: Verify threshold warnings trigger at red_alert (30)

---

## Gap 2: Ambient Effect Generation (HIGH PRIORITY)

### Current State
**Problem:**
- No system to auto-generate ambient effects based on restraint level
- Archivist manually adds ambient effects (if remembers to)
- No scaling: minor vs district-level vs city-level contamination
- Story feels disconnected from internal character state

**Evidence:**
```
Storyteller context (missing):
"ambient_effects": None  // ← Should scale with restraint_profile.current_restraint
```

### Impact
- **Phase 2 Test**: Cannot validate ambient effects scale with restraint
- **Narrative consequence**: Story doesn't reflect character's internal struggle
- **Canon consistency**: Jujutsu Kaisen establishes curse leakage from emotional instability

### Solution Required

#### 2a. Ambient Effect Generator Function
```python
# src/tools/ambient_effects.py

async def get_ambient_effects(story_id: str) -> Dict[str, Any]:
    """Generate ambient effects based on restraint level."""
    bible = await get_world_bible(story_id)
    restraint = bible["character_sheet"]["power_systems"]["restraint_profile"]["current_restraint"]

    # Scale effects to restraint level
    if restraint > 75:
        # Fully restrained - no effects
        effects = {
            "level": "none",
            "description": None,
            "scale": None,
        }
    elif restraint > 50:
        # Minor stress - localized hints
        effects = {
            "level": "minor",
            "description": "Subtle curse manifestations near character - fleeting shadows, temperature drops, animals acting strangely",
            "scale": "character-proximal (5-10 meter radius)",
            "intensity": (75 - restraint) / 25,  # 0.0 to 1.0
        }
    elif restraint > 25:
        # Moderate stress - district-level contamination
        effects = {
            "level": "moderate",
            "description": "Curse saturation in surrounding area - widespread minor incidents, infrastructure degradation, animal deaths",
            "scale": "district-level (100+ meter radius)",
            "intensity": (50 - restraint) / 25,
        }
    else:
        # Critical stress - city-level contamination
        effects = {
            "level": "severe",
            "description": "City-scale curse contamination - mass incidents, infrastructure collapse, rapid animal/plant death",
            "scale": "city-level (1+ km radius)",
            "intensity": (25 - restraint) / 25,
        }

    return effects

async def inject_ambient_effects_context(story_id: str, context: Dict) -> Dict:
    """Inject ambient effects into Storyteller context."""
    effects = await get_ambient_effects(story_id)

    if effects["level"] != "none":
        context["ambient_effects"] = {
            "active": True,
            "level": effects["level"],
            "description": effects["description"],
            "scale": effects["scale"],
            "narrative_cue": f"Background detail: {effects['description']}"
        }
    else:
        context["ambient_effects"] = {"active": False}

    return context
```

#### 2b. Integration with Storyteller Pipeline
```python
# In run_pipeline (src/ws/runner.py)

# Before sending prompt to Storyteller:
storyteller_context = await inject_ambient_effects_context(story_id, base_context)

storyteller_prompt = f"""
{base_prompt}

AMBIENT CONTEXT:
{storyteller_context['ambient_effects']['narrative_cue']}
"""
```

#### 2c. Validation in Archivist
```python
# After Storyteller generates chapter, validate ambient effect consistency

def validate_ambient_consistency(chapter_content: str, restraint_level: float) -> bool:
    """Verify generated chapter respects ambient effect constraints."""

    if restraint_level > 75:
        # Should have NO supernatural manifestations
        forbidden_terms = ["curse", "contamination", "manifestation", "pressure"]
        return not any(term in chapter_content.lower() for term in forbidden_terms)

    elif restraint_level > 50:
        # Can reference minor manifestations but NOT district-scale
        allowed = ["shadow", "fleeting", "subtle", "temperature"]
        forbidden = ["district", "widespread", "city", "mass"]

        has_allowed = any(term in chapter_content.lower() for term in allowed)
        has_forbidden = any(term in chapter_content.lower() for term in forbidden)

        return has_allowed and not has_forbidden

    # ... etc for other levels

    return True
```

### Testing
- **Phase 2**: Verify effects scale from "none" at 100 to "minor" at 90
- **Phase 2+**: Verify effects progress through levels as restraint degrades

---

## Gap 3: Power Usage Cost System (HIGH PRIORITY)

### Current State
**Problem:**
- No mechanism to track capability deployment percentage
- Combat power usage doesn't deduct restraint
- Cannot model restraint-degradation arc narrative

### Solution Required

```python
# src/tools/power_usage_costs.py

async def calculate_power_usage_cost(
    story_id: str,
    deployment_percent: float,
    technique: str = "unspecified"
) -> float:
    """
    Calculate restraint cost for power deployment.

    Cost = deployment_percent × 1.5
    Examples:
    - 25% deployment = -37.5 restraint
    - 50% deployment = -75 restraint
    - 100% deployment = -150 restraint (instant critical)
    """
    cost = deployment_percent * 1.5
    return -cost

async def apply_power_usage_cost(
    story_id: str,
    deployment_percent: float,
    technique: str,
    opponent: str = ""
) -> Dict:
    """Apply power usage cost after combat."""
    cost = await calculate_power_usage_cost(story_id, deployment_percent, technique)

    result = await apply_restraint_cost(
        story_id=story_id,
        cost_type="power_deployment",
        amount=cost,
        reason=f"Used {deployment_percent}% {technique} against {opponent or 'opponent'}"
    )

    return {
        "deployment_percent": deployment_percent,
        "cost_applied": cost,
        "new_restraint": result["current_restraint"],
        "alert_level": result["alert_level"],
    }
```

### Testing
- **Phase 3**: Verify 25% deployment costs -37.5 (90 → 52.5)
- **Phase 3**: Verify threshold trigger at red_alert

---

## Gap 4: Adaptation Ledger Persistence (MEDIUM PRIORITY)

### Current State
**Problem:**
- Adaptation ledger schema exists but is never queried
- Storyteller doesn't know about past adaptations
- No difficulty modifier system for repeated encounters

### Solution Required

```python
# src/tools/adaptation_ledger.py

async def get_mahoraga_adaptations(story_id: str) -> List[str]:
    """Query all Mahoraga adaptations from World Bible."""
    bible = await get_world_bible(story_id)
    shikigami_data = bible["character_sheet"]["power_systems"]["secondary"]["shikigami_roster"]["mahoraga"]
    return shikigami_data.get("adaptations", [])

async def inject_adaptation_context(story_id: str, context: Dict) -> Dict:
    """Provide Storyteller with adaptation history."""
    adaptations = await get_mahoraga_adaptations(story_id)

    if adaptations:
        context["mahoraga_history"] = {
            "previous_adaptations": adaptations,
            "note": "Mahoraga has learned to counter these techniques before"
        }

    return context
```

### Testing
- **Phase 4**: Verify adaptation is logged after encounter
- **Phase 4**: Verify future encounter references prior adaptation

---

## Gap 5: Emotional Trigger Handlers (MEDIUM PRIORITY)

### Current State
**Problem:**
- Generic emotional responses
- No character-specific trigger conditions
- Cannot model Kageaki's cold response to Minoru threat

### Solution Required

```python
# src/tools/emotional_triggers.py

EMOTIONAL_TRIGGERS = {
    "minoru_threatened": {"cost": -10, "personality_shift": "cold_protective"},
    "family_pressure": {"cost": -5, "personality_shift": "restrained_duty"},
    "combat_conflict": {"cost": -2, "personality_shift": "neutral"},
}

async def detect_emotional_triggers(chapter_content: str, story_id: str) -> List[Dict]:
    """Detect triggered emotions in chapter."""
    bible = await get_world_bible(story_id)
    character_name = bible["character_sheet"]["name"]

    triggers_detected = []

    if "Minoru" in chapter_content and ("threaten" in chapter_content.lower() or "attack" in chapter_content.lower()):
        triggers_detected.append({
            "trigger": "minoru_threatened",
            "evidence": f"Minoru mentioned in threatening context",
            "cost": EMOTIONAL_TRIGGERS["minoru_threatened"]["cost"],
        })

    if "family" in chapter_content.lower() and ("pressure" in chapter_content.lower() or "decision" in chapter_content.lower()):
        triggers_detected.append({
            "trigger": "family_pressure",
            "evidence": "Family pressure mentioned",
            "cost": EMOTIONAL_TRIGGERS["family_pressure"]["cost"],
        })

    return triggers_detected

async def apply_emotional_triggers(story_id: str, triggers: List[Dict]) -> Dict:
    """Apply all detected emotional triggers."""
    results = []

    for trigger in triggers:
        result = await apply_restraint_cost(
            story_id=story_id,
            cost_type=trigger["trigger"],
            amount=trigger["cost"],
            reason=trigger["evidence"]
        )
        results.append(result)

    return {"triggers_applied": len(results), "results": results}
```

### Testing
- **Phase 3**: Verify -10 cost when Minoru threatened
- **Phase 3**: Verify personality shift (cold/protective tone)

---

## Gap 6: Power Scaling Validator (MEDIUM PRIORITY)

### Current State
**Problem:**
- Manual validation only
- Cannot flag inconsistent power deployment
- No canonical benchmark comparison

### Solution Required

```python
# src/tools/power_scaling_validator.py

POWER_SCALING_BENCHMARKS = {
    "nue": {
        "system": "JJK/Ten Shadows",
        "capability": "Lightning/Storm manifestation",
        "scale": "skyscraper-scale (~100-200m)",
        "feats": ["Dwarfs skyscrapers", "Disrupts city power infrastructure"],
        "canonical_limit": "city-level phenomena"
    },
    "max_elephant": {
        "system": "JJK/Ten Shadows",
        "capability": "Water release",
        "scale": "flood-level (~multi-city scale)",
        "feats": ["Infrastructure collapse", "Mass displacement"],
    },
    # ... etc
}

async def validate_power_feat(
    chapter_content: str,
    power_name: str,
    deployment_description: str
) -> Dict[str, Any]:
    """Validate power usage against canonical benchmarks."""

    if power_name not in POWER_SCALING_BENCHMARKS:
        return {"status": "unknown", "power": power_name}

    benchmark = POWER_SCALING_BENCHMARKS[power_name]
    canonical_scale = benchmark["scale"]

    # Naive text analysis (better: LLM-based comparison)
    deployment_lower = deployment_description.lower()

    if "stadium" in deployment_lower and "skyscraper" in canonical_scale:
        return {
            "status": "consistent",
            "power": power_name,
            "canonical": canonical_scale,
            "deployed": "stadium-scale (~100m)",
        }
    elif "wall" in deployment_lower and "skyscraper" in canonical_scale:
        return {
            "status": "inconsistent_low",
            "power": power_name,
            "canonical": canonical_scale,
            "deployed": "wall-scale (~10m)",
            "issue": "Power significantly under-deployed",
        }

    return {"status": "neutral", "power": power_name}
```

### Testing
- **Phase 5**: Verify Nue stadium-scale deployment is consistent with canon
- **Phase 5**: Flag any inconsistencies

---

## Gap 7: Narrative Constraint Enforcement (MEDIUM PRIORITY)

### Current State
**Problem:**
- Constraints documented but not validated
- Forbidden developments might appear in narrative
- No automatic detection/blocking

### Solution Required

```python
# src/tools/constraint_enforcer.py

async def validate_narrative_constraints(
    chapter_content: str,
    story_id: str
) -> Dict[str, Any]:
    """Validate chapter respects narrative constraints."""

    bible = await get_world_bible(story_id)
    constraints = bible["character_sheet"].get("narrative_constraints", {})

    violations = []

    # Check cannot_develop
    if "cannot_develop" in constraints:
        for forbidden in constraints["cannot_develop"]:
            if forbidden.lower() in chapter_content.lower():
                violations.append({
                    "type": "forbidden_development",
                    "constraint": forbidden,
                    "status": "violated",
                })

    # Check must_maintain
    if "must_maintain" in constraints:
        for required in constraints["must_maintain"]:
            if required.lower() not in chapter_content.lower():
                violations.append({
                    "type": "missing_requirement",
                    "constraint": required,
                    "status": "violated",
                })

    return {
        "total_constraints": len(constraints.get("cannot_develop", [])) + len(constraints.get("must_maintain", [])),
        "violations_detected": len(violations),
        "violations": violations,
        "status": "pass" if not violations else "fail",
    }
```

### Testing
- **Phase 5**: Verify Domain Expansion development is blocked
- **Phase 5**: Verify required constraint maintains

---

## Implementation Priority

### Tier 1 (Critical - Blocks Phase 1-3)
1. **Restraint Meter System** (Gap 1)
   - Time: 2-3 hours
   - Blocker for: Gaps 2, 3, 4, 5
   - Schema + cost application + threshold checks

2. **Ambient Effect Generator** (Gap 2)
   - Time: 1.5-2 hours
   - Depends on: Gap 1
   - Scaling function + context injection + validation

3. **Power Usage Cost Calculator** (Gap 3)
   - Time: 1 hour
   - Depends on: Gap 1
   - Cost formula + application + logging

### Tier 2 (Important - Blocks Phase 4-5)
4. **Adaptation Ledger Query** (Gap 4)
   - Time: 1 hour
   - Context injection + validation

5. **Emotional Trigger System** (Gap 5)
   - Time: 1.5 hours
   - Detection + application + personality shift flags

6. **Power Scaling Validator** (Gap 6)
   - Time: 2-3 hours
   - Benchmark database + comparison logic + flagging

7. **Narrative Constraint Enforcer** (Gap 7)
   - Time: 1-1.5 hours
   - Constraint parsing + violation detection + suggestions

---

## Testing Strategy

### Phase 1: Baseline (Validates Gaps 1, 2)
- Setup: Load Kudou dataset, generate enrollment + conflict scenes
- Expected: Identifies lack of restraint tracking and ambient effects
- Outcome: 20-35% system readiness

### Phase 2: State Tracking (Validates Gaps 1, 2)
- Setup: Cumulative stress scenario (3 events = -10 restraint total)
- Expected: Identifies ambient effect scaling gaps
- Outcome: 30-50% system readiness if Gap 1&2 partially working

### Phase 3: Combat & Emotional (Validates Gaps 1, 3, 5)
- Setup: Combat with power deployment + Minoru threat
- Expected: Identifies usage cost and trigger gaps
- Outcome: 50-70% system readiness if Gaps 1,3,5 working

### Phase 4: Persistence (Validates Gap 4)
- Setup: Mahoraga adaptation + future encounter
- Expected: Identifies adaptation ledger gaps
- Outcome: 70-80% system readiness if Gap 4 working

### Phase 5: Validation (Validates Gaps 6, 7)
- Setup: Power scaling + constraint enforcement
- Expected: Validates power consistency and rule adherence
- Outcome: 80-90%+ system readiness if Gaps 6,7 working

---

## Benefits Beyond Kudou Kageaki

These improvements benefit **ALL characters** with:
- **Persistent state tracking**: Any character with cumulative injuries, madness, corruption
- **Environmental effects**: Any character with aura/presence that affects surroundings
- **Learning systems**: Any character that adapts, evolves, or develops
- **Emotional triggers**: Any character with specific emotional responses
- **Power constraints**: Any character with forbidden developments or required characteristics

---

## Estimated Total Implementation Time

- **Tier 1**: 4-6 hours (critical path for Phase 1-3)
- **Tier 2**: 5-8 hours (enables Phase 4-5)
- **Total**: 9-14 hours to full 90%+ system readiness

---

## Next Steps

1. ✅ **Test Infrastructure Created** (this document + test files)
2. ⏭️ **Execute Phase 1** (manual tests with PHASE_1_EXECUTION_GUIDE.md)
3. ⏭️ **Implement Tier 1 Gaps** (Gaps 1, 2, 3)
4. ⏭️ **Re-run Phase 1-3** (validate improvements)
5. ⏭️ **Implement Tier 2 Gaps** (Gaps 4, 5, 6, 7)
6. ⏭️ **Run All Phases** (full test suite)
7. ⏭️ **Generate Readiness Report**
