from dotenv import load_dotenv
load_dotenv()

from src.app import app
from src.routers import stories as stories_router, branches as branches_router, setup as setup_router
from src.ws.handler import websocket_endpoint

# --- REST Routers ---
app.include_router(setup_router.router)
app.include_router(stories_router.router)
app.include_router(branches_router.router)

# --- WebSocket Route ---
app.add_api_websocket_route("/ws/{story_id}", websocket_endpoint)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
