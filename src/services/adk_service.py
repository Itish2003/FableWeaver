from __future__ import annotations
import uuid
import logging
import pickle
from datetime import datetime, timezone
from typing import Any, Optional, List
from sqlalchemy import select, delete, desc
from sqlalchemy.orm import selectinload

from google.adk.sessions.base_session_service import BaseSessionService, GetSessionConfig, ListSessionsResponse
from google.adk.sessions.session import Session
from google.adk.events.event import Event
from google.genai import types

from src.database import AsyncSessionLocal
from src.models import AdkSession, AdkEvent, AdkAppState, AdkUserState

logger = logging.getLogger(__name__)

class FableSessionService(BaseSessionService):
    """
    Async implementation of SessionService using SQLAlchemy models.
    """
    
    async def create_session(
        self,
        *,
        app_name: str,
        user_id: str,
        state: Optional[dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> Session:
        sid = session_id or str(uuid.uuid4())
        
        async with AsyncSessionLocal() as db:
            # Check if exists
            result = await db.execute(
                select(AdkSession).where(
                    AdkSession.app_name == app_name,
                    AdkSession.user_id == user_id,
                    AdkSession.adk_session_id == sid
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                 # In ADK, create might throw if exists, or return existing. 
                 # BaseSessionService doesn't specify throw, but DatabaseSessionService did.
                 # We will return existing to be safe/idempotent.
                 logger.info(f"Session {sid} already exists, returning it.")
                 return await self.get_session(app_name=app_name, user_id=user_id, session_id=sid)

            new_session = AdkSession(
                app_name=app_name,
                user_id=user_id,
                adk_session_id=sid,
                state=state or {},
                create_time=datetime.now(timezone.utc),
                update_time=datetime.now(timezone.utc)
            )
            db.add(new_session)
            await db.commit()
            
            return Session(
                id=sid,
                app_name=app_name,
                user_id=user_id,
                state=state or {},
                events=[]
            )

    async def get_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        config: Optional[GetSessionConfig] = None,
    ) -> Optional[Session]:
        
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(AdkSession).where(
                    AdkSession.app_name == app_name,
                    AdkSession.user_id == user_id,
                    AdkSession.adk_session_id == session_id
                )
            )
            storage_session = result.scalar_one_or_none()
            if not storage_session:
                return None
            
            # Fetch Events
            query = select(AdkEvent).where(
                AdkEvent.app_name == app_name,
                AdkEvent.user_id == user_id,
                AdkEvent.adk_session_id == session_id
            ).order_by(AdkEvent.timestamp)

            if config and config.after_timestamp:
                after_dt = datetime.fromtimestamp(config.after_timestamp, timezone.utc)
                query = query.where(AdkEvent.timestamp >= after_dt)
            
            if config and config.num_recent_events:
                # To get N *recent* events, we usually sort desc, limit, then reverse.
                # But here we used simple order_by timestamp asc.
                # Let's do subquery or python slice if huge? 
                # For efficiency with simple history:
                pass 
                # Implementing basic load for now.
                
            result_events = await db.execute(query)
            db_events = result_events.scalars().all()
            
            # Convert DB events to ADK Events
            session_events = []
            for dbe in db_events:
                 evt = self._to_event(dbe)
                 session_events.append(evt)
            
            return Session(
                id=session_id,
                app_name=app_name,
                user_id=user_id,
                state=storage_session.state,
                events=session_events
            )

    async def list_sessions(
        self, *, app_name: str, user_id: Optional[str] = None
    ) -> ListSessionsResponse:
        # Not strictly needed for InMemoryRunner but good to have
        async with AsyncSessionLocal() as db:
            query = select(AdkSession).where(AdkSession.app_name == app_name)
            if user_id:
                query = query.where(AdkSession.user_id == user_id)
            
            result = await db.execute(query)
            rows = result.scalars().all()
            
            sessions = [
                Session(id=r.adk_session_id, app_name=r.app_name, user_id=r.user_id, state=r.state)
                for r in rows
            ]
            return ListSessionsResponse(sessions=sessions)

    async def delete_session(
        self, *, app_name: str, user_id: str, session_id: str
    ) -> None:
        async with AsyncSessionLocal() as db:
            await db.execute(
                delete(AdkSession).where(
                    AdkSession.app_name == app_name,
                    AdkSession.user_id == user_id,
                    AdkSession.adk_session_id == session_id
                )
            )
            # Cascade should handle events if configured in DB, otherwise delete events too
            # Our model definition has cascade="all, delete-orphan", so SQLAlchemy handles it if we loaded it, 
            # but for raw DELETE statement, we rely on DB FK cascade or manual delete.
            # Safe to manually delete events too.
            await db.execute(
                delete(AdkEvent).where(
                    AdkEvent.app_name == app_name,
                    AdkEvent.user_id == user_id,
                    AdkEvent.adk_session_id == session_id
                )
            )
            await db.commit()

    async def append_event(self, session: Session, event: Event) -> Event:
        # Save to DB
        async with AsyncSessionLocal() as db:
             db_event = self._from_event(session, event)
             db.add(db_event)
             
             # Also update session update_time?
             # Fetch session to update time
             result = await db.execute(select(AdkSession).where(
                 AdkSession.app_name == session.app_name,
                 AdkSession.user_id == session.user_id,
                 AdkSession.adk_session_id == session.id
             ))
             db_session = result.scalar_one_or_none()
             if db_session:
                 db_session.update_time = datetime.now(timezone.utc)
                 # Update state if needed (skipped for now for simplicity, rely on base class for memory state)
                 pass
             
             await db.commit()
        
        # Update in-memory
        return await super().append_event(session, event)

    def _to_event(self, db_event: AdkEvent) -> Event:
        # Convert JSON content back to types.Content if possible
        # We assume content is stored as dict compatible with Event generic type
        # In Fable/Gemini case, content is types.Content.
        # We need to reconstruct it.
        
        content_obj = None
        if db_event.content:
            # Assuming db_event.content is a dict like {"parts": [...], "role": ...}
            # verification needed: how google.genai.types.Content deserializes?
            # types.Content(**db_event.content) might work.
            try:
                # If it looks like Content
                if "parts" in db_event.content:
                    # parts need to be converted to Part objects?
                    # types.Content.from_dict?
                    # Let's try flexible instantiation
                    # parts=[types.Part(text=...)]
                    parts_data = db_event.content.get("parts") or []  # Handle None explicitly
                    parts_objs = []

                    # Skip if parts is None or empty - this event has no content
                    if parts_data:
                        for p in parts_data:
                            if isinstance(p, dict) and "text" in p:
                                parts_objs.append(types.Part(text=p["text"]))
                            # handle other types if needed

                    # Only create Content if we have valid parts, otherwise skip
                    if parts_objs:
                        content_obj = types.Content(parts=parts_objs, role=db_event.content.get("role"))
                    else:
                        # Empty content - just store None
                        content_obj = None
                else:
                    content_obj = db_event.content
            except Exception as e:
                 logger.warning(f"Failed to deserialize content for event {db_event.id}: {e}")
                 content_obj = db_event.content # Fallback

        return Event(
            id=db_event.adk_event_id,
            author=db_event.author,
            content=content_obj,
            actions=pickle.loads(db_event.actions) if db_event.actions else None,
            timestamp=db_event.timestamp.replace(tzinfo=timezone.utc).timestamp(), # Event expects float timestamp? BaseSessionService.append_event uses it
            turn_complete=db_event.turn_complete or False
        )

    def _from_event(self, session: Session, event: Event) -> AdkEvent:
        # Serialize content
        content_dict = None
        if event.content:
             if hasattr(event.content, "model_dump"):
                 content_dict = event.content.model_dump(mode='json')
             elif hasattr(event.content, "to_dict"):
                 content_dict = event.content.to_dict()
             else:
                 # Try basic dict
                 try:
                     content_dict = dict(event.content)
                 except:
                     content_dict = str(event.content) # Fallback

        return AdkEvent(
            adk_event_id=event.id or str(uuid.uuid4()),
            app_name=session.app_name,
            user_id=session.user_id,
            adk_session_id=session.id,
            invocation_id=str(uuid.uuid4()), # Event doesn't have invocation_id always?
            author=event.author,
            actions=pickle.dumps(event.actions) if event.actions else b"",
            timestamp=datetime.now(timezone.utc),
            content=content_dict,
            turn_complete=event.turn_complete
        )
