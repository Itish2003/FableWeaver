# FableWeaver Engine 2.0 (WebSocket Edition)

FableWeaver is an advanced Interactive Fiction engine powered by Google Gemini 2.5 Flash. It uses a multi-agent system (Lore Hunters, Storyteller, Game Master) to generate deep, researched narratives based on user prompts.

## Key Features

- **Real-Time Streaming**: Uses WebSockets for instant content delivery.
- **Multi-Agent Research**: "Lore Hunters" scrape the web to ensure canon accuracy.
- **Dynamic World Bible**: Maintains a JSON "bible" of the world state.
- **Magnificent UI**: A glassmorphism-styled React frontend with animations.
- **Resilient API Client**: Automatically rotates keys on `429` errors and retries.

## Setup

1. **Backend**:

   ```bash
   # Install dependencies
   uv sync

   # Set API Keys in .env
   # GOOGLE_API_KEYS=key1,key2,key3...

   # Start Server
   ./.venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 8000
   ```

2. **Frontend**:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
   Open `http://localhost:5173`.

## Architecture

- `src/main.py`: FastAPI + WebSocket server. Orchestrates agents.
- `src/agents/research.py`: Sequential web scraping agents (Lore Hunters).
- `src/agents/narrative.py`: Storyteller and Game Master agents.
- `src/utils/auth.py`: Handles Key Rotation logic.
- `src/utils/resilient_client.py`: Global GenAI Client proxy for 429 retries.

## Rate Limits & Quotas

> **Important**: This system uses Google Gemini 2.5 Flash relative strictly.
> If you provide multiple API keys, ensure they belong to **separate Google Cloud Projects** to effectively bypass the project-level rate limits (20 RPM / 1500 RPD).
> If keys share a project, you may encounter `429 RESOURCE_EXHAUSTED` errors.
> **Update**: The system now includes a `ResilientClient` that detects these errors and automatically rotates to the next key in your pool, ensuring uninterrupted gameplay as long as _one_ key has quota.

## Usage

1. Connect via the Frontend.
2. Enter Universes (e.g., "Marvel, DC") and Deviation.
3. Wait for Research (approx. 1-2 mins).
4. Read Chapter 1 (streamed).
5. Make a Choice.
6. Repeat.
