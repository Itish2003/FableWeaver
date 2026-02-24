"""
Conversational Story Setup Wizard

Multi-turn AI-guided setup system for clarifying story parameters before initialization.
Users provide rough input → AI asks clarifying questions → Final story created with
explicit metadata that guides Lore Keeper and Storyteller behavior.
"""
import logging
import json
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone
import uuid

from google.genai import Client as GenAIClient
from src.database import AsyncSessionLocal
from src.models import Story, WorldBible
from src.utils.auth import get_api_key
from src.utils.resilient_client import ResilientClient
from src.config import get_settings
from src.tools.core_tools import get_enhanced_default_bible

logger = logging.getLogger("fable.setup")
router = APIRouter(prefix="/api/setup", tags=["setup"])


# ============================================================================
#                           SCHEMAS
# ============================================================================

class SetupInitialRequest(BaseModel):
    """Initial user input for story setup."""
    user_input: str = Field(..., description="User's rough story idea")


class SetupClarificationResponse(BaseModel):
    """Response with clarifying questions."""
    questions: List[str] = Field(..., description="List of questions for user")
    current_understanding: Dict[str, Any] = Field(default_factory=dict)


class SetupRefineRequest(BaseModel):
    """User answer to clarification question."""
    current_config: Dict[str, Any] = Field(..., description="Current config state")
    user_answer: str = Field(..., description="User's answer to latest question")
    question_index: int = Field(default=0, description="Which question was answered")


class SetupRefineResponse(BaseModel):
    """Updated config and next question."""
    updated_config: Dict[str, Any] = Field(...)
    next_question: Optional[str] = Field(None, description="Next question or None if review ready")
    is_review_ready: bool = Field(False, description="Ready to show review?")


class SetupReviewRequest(BaseModel):
    """Review and confirm final setup."""
    final_config: Dict[str, Any] = Field(...)
    confirmed: bool = Field(True, description="User confirmed the setup")


class StorySetupConfig(BaseModel):
    """Final story configuration from wizard."""
    title: str = Field(default="Untitled Story")
    universes: List[str] = Field(default_factory=list)
    story_universe: str = Field(...)
    character_origin: Optional[str] = Field(None)
    powers: List[str] = Field(default_factory=list)
    power_level: str = Field(default="city")  # street | city | planetary | cosmic
    isolate_powerset: bool = Field(default=True)
    story_tone: str = Field(default="balanced")  # dark | balanced | comedic | grimdark
    themes: List[str] = Field(default_factory=list)
    chapter_min_words: int = Field(default=6000)
    chapter_max_words: int = Field(default=8000)
    research_focus: List[str] = Field(default_factory=list)
    power_limitations: str = Field(default="")
    user_context: str = Field(default="")


# ============================================================================
#                       CLARIFICATION PROMPT
# ============================================================================

def get_clarification_prompt(user_input: str) -> str:
    """Generate prompt for initial clarification."""
    return f"""You are the Setup Wizard for FableWeaver - an Interactive Fiction engine for canonically-accurate fanfiction.

The user has provided this initial story concept:
---
{user_input}
---

Your job is to ask clarifying questions to understand:
1. POWER MECHANICS: Does the OC have powers? From which universe? What's the power level?
2. ISOLATION STRATEGY: Should the powerset be isolated from source universe context?
3. STORY TONE: What's the overall tone? (dark, balanced, comedic, grimdark)
4. RESEARCH FOCUS: What should research prioritize?
5. PRACTICAL CONSTRAINTS: Chapter length preference, specific themes

Guidelines:
- Ask ONE question at a time
- Be conversational and friendly
- Use the user's own terms and concepts
- Acknowledge what you understand before asking the next question
- Make questions specific, not open-ended

Generate exactly 5 clarifying questions, one per line. Each question should be:
- Specific to their story concept
- Answerable with brief input (1-2 sentences)
- Building toward a complete understanding

Format each question as a natural follow-up, like:
"I see you're interested in [CONCEPT]. Before we start research, I need to understand: [QUESTION]?"

Generate the 5 questions now (one per line):
"""


def get_refinement_prompt(
    current_config: Dict[str, Any],
    user_answer: str,
    question_index: int,
) -> str:
    """Generate prompt for refining understanding."""
    config_summary = json.dumps(current_config, indent=2)

    refinement_guide = {
        0: "This is about POWER MECHANICS. Extract: power_level (street|city|planetary|cosmic), whether OC has powers, from which universe.",
        1: "This is about ISOLATION. Extract: isolate_powerset (true if user wants pure mechanics, false if wants context included).",
        2: "This is about STORY TONE. Extract: story_tone (dark|balanced|comedic|grimdark) and any themes mentioned.",
        3: "This is about RESEARCH FOCUS. Extract: research_focus (array of: power_systems, characters, lore, politics, etc).",
        4: "This is about PRACTICAL SETTINGS. Extract: chapter_min_words, chapter_max_words, any other preferences.",
    }

    guide_text = refinement_guide.get(question_index, "Extract relevant configuration data.")

    return f"""You are updating a story configuration based on user feedback.

Current understanding:
```json
{config_summary}
```

User just answered:
---
{user_answer}
---

{guide_text}

Your task:
1. Parse the user's answer for relevant information
2. Update the config with new/clarified values
3. Decide if more questions are needed or if understanding is complete

Respond with ONLY valid JSON, no other text:
{{
  "updated_config": {{
    "title": "...",
    "universes": [...],
    "story_universe": "...",
    "character_origin": "...",
    "powers": [...],
    "power_level": "city|planetary|cosmic|street",
    "isolate_powerset": true|false,
    "story_tone": "dark|balanced|comedic|grimdark",
    "themes": [...],
    "chapter_min_words": 6000,
    "chapter_max_words": 8000,
    "research_focus": [...],
    "power_limitations": "...",
    "user_context": "..."
  }},
  "next_question": "Question string or null if ready for review",
  "is_review_ready": true|false
}}

Ensure JSON is valid and complete.
"""


def get_review_prompt(final_config: Dict[str, Any]) -> str:
    """Generate review summary for user."""
    config_str = json.dumps(final_config, indent=2)
    return f"""You are summarizing a story setup for user confirmation.

Final configuration:
```json
{config_str}
```

Generate a friendly, concise summary (4-6 sentences) that:
1. Confirms the story universe and setup
2. Emphasizes the power level and isolation strategy
3. Notes the story tone and research focus
4. Asks if everything looks good

Make it conversational and warm. End with: "Does this capture your vision? (reply 'yes' to confirm or describe changes needed)"
"""


# ============================================================================
#                           ENDPOINTS
# ============================================================================

@router.post("/clarify")
async def clarify_setup(request: SetupInitialRequest) -> SetupClarificationResponse:
    """
    First turn: Analyze user input and generate initial clarifying questions.

    Takes rough user input and generates 5 specific questions about:
    - Power mechanics and level
    - Universe isolation
    - Story tone
    - Research focus
    - Practical constraints
    """
    try:
        settings = get_settings()
        client = ResilientClient(api_key=get_api_key())

        prompt = get_clarification_prompt(request.user_input)

        response = await client.aio.models.generate_content(
            model=settings.model_research,
            contents=prompt,
        )

        questions_text = response.text.strip()
        questions = [q.strip() for q in questions_text.split("\n") if q.strip()]

        # Limit to 5 questions
        questions = questions[:5]

        # Extract initial understanding from user input
        initial_understanding = {
            "user_input": request.user_input,
            "universes": [],
            "story_universe": "",
            "character_origin": "",
            "powers": [],
            "power_level": "city",
            "isolate_powerset": True,
            "story_tone": "balanced",
            "themes": [],
            "chapter_min_words": 6000,
            "chapter_max_words": 8000,
            "research_focus": [],
            "power_limitations": "",
            "user_context": request.user_input,
        }

        logger.info(f"Generated {len(questions)} clarifying questions for user input")

        return SetupClarificationResponse(
            questions=questions,
            current_understanding=initial_understanding,
        )

    except Exception as e:
        logger.error(f"Error in clarify_setup: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/refine")
async def refine_setup(request: SetupRefineRequest) -> SetupRefineResponse:
    """
    Subsequent turns: Refine understanding based on user answers.

    Updates config based on answer, determines if more questions needed.
    """
    try:
        settings = get_settings()
        client = ResilientClient(api_key=get_api_key())

        prompt = get_refinement_prompt(
            request.current_config,
            request.user_answer,
            request.question_index,
        )

        response = await client.aio.models.generate_content(
            model=settings.model_research,
            contents=prompt,
        )

        # Parse JSON response
        response_text = response.text.strip()

        # Extract JSON from response (handle markdown code blocks)
        if "```json" in response_text:
            json_start = response_text.find("```json") + 7
            json_end = response_text.find("```", json_start)
            json_str = response_text[json_start:json_end].strip()
        elif "```" in response_text:
            json_start = response_text.find("```") + 3
            json_end = response_text.find("```", json_start)
            json_str = response_text[json_start:json_end].strip()
        else:
            json_str = response_text

        result = json.loads(json_str)

        logger.info(
            f"Refined config. "
            f"Next question: {'yes' if result.get('next_question') else 'no'}. "
            f"Review ready: {result.get('is_review_ready')}"
        )

        return SetupRefineResponse(
            updated_config=result.get("updated_config", request.current_config),
            next_question=result.get("next_question"),
            is_review_ready=result.get("is_review_ready", False),
        )

    except Exception as e:
        logger.error(f"Error in refine_setup: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/review")
async def review_setup(request: SetupReviewRequest) -> Dict[str, str]:
    """
    Generate review summary for user to confirm.
    """
    try:
        settings = get_settings()
        client = ResilientClient(api_key=get_api_key())

        prompt = get_review_prompt(request.final_config)

        response = await client.aio.models.generate_content(
            model=settings.model_research,
            contents=prompt,
        )

        return {
            "summary": response.text.strip(),
        }

    except Exception as e:
        logger.error(f"Error in review_setup: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/confirm")
async def confirm_setup(config: StorySetupConfig) -> Dict[str, str]:
    """
    Final step: Create story with clarified configuration.

    Creates Story, WorldBible, and initializes pipeline with setup metadata
    that guides Lore Keeper and Storyteller behavior.
    """
    try:
        # Create Story record
        story_id = str(uuid.uuid4())
        story = Story(
            id=story_id,
            title=config.title or "Untitled Story",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            # NEW: Per-story chapter length overrides
            chapter_min_words_override=config.chapter_min_words,
            chapter_max_words_override=config.chapter_max_words,
        )

        # Create World Bible with setup metadata
        bible_content = get_enhanced_default_bible()

        # Add setup context to meta
        bible_content["meta"].update({
            "title": config.title,
            "universes": config.universes,
            # NEW SETUP METADATA:
            "story_universe": config.story_universe,
            "character_origin": config.character_origin,
            "power_level": config.power_level,  # street | city | planetary | cosmic
            "isolation_strategy": config.isolate_powerset,  # True = pure mechanics
            "story_tone": config.story_tone,  # dark | balanced | comedic | grimdark
            "themes": config.themes,
            "research_focus": config.research_focus,
            "power_limitations": config.power_limitations,
            "user_intent": config.user_context,
        })

        bible = WorldBible(
            id=story_id,
            story_id=story_id,
            content=bible_content,
        )

        # Persist to database
        async with AsyncSessionLocal() as session:
            session.add(story)
            session.add(bible)
            await session.commit()

        logger.info(
            f"Created story {story_id} via setup wizard. "
            f"Power level: {config.power_level}, "
            f"Isolate powerset: {config.isolate_powerset}, "
            f"Tone: {config.story_tone}"
        )

        return {
            "story_id": story_id,
            "status": "initializing",
            "message": f"Story '{config.title}' created. Beginning narrative generation...",
        }

    except Exception as e:
        logger.error(f"Error in confirm_setup: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
