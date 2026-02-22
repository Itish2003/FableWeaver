# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FableWeaver is an Interactive Fiction engine powered by Google Gemini 2.5 Flash. It uses a multi-agent system (Lore Hunters, Lore Keeper, Storyteller, Archivist) to generate canonically-accurate fanfiction with real-time streaming via WebSockets.

## Development Commands

### Backend (Python/FastAPI)
```bash
# Install dependencies
uv sync

# Start server (port 8000)
./.venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 8000

# Run database migrations
alembic upgrade head

# Create new migration
alembic revision --autogenerate -m "description"
```

### Frontend (React/Vite)
```bash
cd frontend
npm install
npm run dev      # Development server (port 5173)
npm run build    # Production build
npm run lint     # ESLint
```

### Environment Variables (.env)
```
GOOGLE_API_KEYS=key1,key2,key3    # Comma-separated, preferably from different GCP projects
DATABASE_URL=postgresql+asyncpg://user@localhost/fable
MODEL_STORYTELLER=gemini-2.5-flash
MODEL_ARCHIVIST=gemini-2.5-flash
MODEL_RESEARCH=gemini-2.5-flash
```

## Architecture

### Multi-Agent Pipeline
The system uses Google ADK with a nested agent structure:

```
SequentialAgent (Main Pipeline)
├── Phase 1: Initialization
│   ├── ParallelAgent (Lore Hunter Swarm) → Web scraping for canon research
│   ├── Lore Keeper → Synthesizes research into World Bible
│   └── Storyteller → Generates Chapter 1
└── Phase 2: Game Loop (per turn)
    ├── Archivist → Updates World Bible from player choices
    └── Storyteller → Generates next chapter
```

### Key Backend Components
- **src/main.py**: FastAPI app, WebSocket handler, agent orchestration (~1600 lines)
- **src/agents/research.py**: Lore Hunter swarm + Lore Keeper agents
- **src/agents/narrative.py**: Storyteller + Archivist agents
- **src/utils/resilient_client.py**: Wraps GenAI client with 429 retry logic and key rotation
- **src/utils/auth.py**: API key pool management with cooldown tracking
- **src/tools/**: Bible management (core_tools.py) and meta tools (meta_tools.py)

### World Bible (src/world_bible.json)
Central JSON state containing: metadata, character sheet, power origins, world state, character voices, canon constraints, and anti-Worfing rules. All agents read/write through dedicated tools.

### Database Models (src/models.py)
- **Story**: Main entity with branching support (parent_story_id)
- **History**: Chapter records with choices
- **WorldBible**: Per-story state storage
- **AdkSession/AdkEvent/AdkAppState/AdkUserState**: Google ADK state persistence

### Frontend Architecture
- **hooks/useFableEngine.js**: WebSocket + API integration hook
- **components/**: ConfigForm (story init), StoryView (narrative display), TimelineComparison

## API Patterns

### Rate Limit Handling
The ResilientClient (`src/utils/resilient_client.py`) automatically:
1. Catches 429/503 errors
2. Rotates to next API key in pool
3. Uses exponential backoff (up to 10 retries)
4. Keys from different GCP projects bypass project-level limits

### WebSocket Protocol
Messages streamed as JSON with type markers for: content chunks, choices, research progress, errors.

## Tech Stack
- **Backend**: FastAPI, SQLAlchemy (async), PostgreSQL, Google ADK/GenAI, Playwright
- **Frontend**: React 19, Vite (rolldown), Tailwind CSS, Framer Motion
- **Package Managers**: uv (Python), npm (Node)
- **Python**: 3.13+
