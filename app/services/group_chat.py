"""Group chat service for multi-agent discussions."""
import json
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

from app.core.redis_client import cache, get_redis
from app.services.agent_executor import AgentExecutor


_RUN_LOCK_TTL = 3600  # seconds; a completion run must never exceed this


def _lock_key(session_id: str) -> str:
    return f"groupchat:lock:{session_id}"


def _cancel_key(session_id: str) -> str:
    return f"groupchat:cancel:{session_id}"


def _cosine(a: List[float], b: List[float]) -> float:
    """Cosine similarity of two equal-length vectors.

    Returns 0.0 when the vectors differ in length or either has zero norm.
    """
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


@dataclass
class GroupChatMessage:
    """A single message in a group chat."""
    role: str  # "user", "agent", or "system"
    content: str
    agent_id: Optional[int] = None
    agent_name: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class GroupChatSession:
    """A group chat session involving multiple agents."""
    session_id: str
    user_id: int
    agent_ids: List[int]
    messages: List[GroupChatMessage] = field(default_factory=list)
    max_rounds: int = 5
    current_round: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "active"  # active, completed, cancelled
    parent_conversation_id: Optional[int] = None


class GroupChatService:
    """
    Service for managing group chat sessions between multiple agents.
    
    Supports round-robin discussions, consensus building, and result aggregation.
    """
    
    def __init__(self):
        self.executor = AgentExecutor()
        self._active_sessions: Dict[str, GroupChatSession] = {}

    async def acquire_run_lock(self, session_id: str) -> bool:
        """Acquire the cross-worker run lock. True if acquired, False if held."""
        try:
            r = await get_redis()
            acquired = await r.set(_lock_key(session_id), "1", nx=True, ex=_RUN_LOCK_TTL)
            return bool(acquired)
        except Exception:
            return False

    async def release_run_lock(self, session_id: str) -> None:
        try:
            r = await get_redis()
            await r.delete(_lock_key(session_id))
        except Exception:
            pass

    async def is_running(self, session_id: str) -> bool:
        """Whether a completion run holds the lock (cross-worker)."""
        try:
            r = await get_redis()
            return bool(await r.exists(_lock_key(session_id)))
        except Exception:
            return False

    async def _set_cancel_flag(self, session_id: str) -> None:
        try:
            r = await get_redis()
            await r.set(_cancel_key(session_id), "1", ex=_RUN_LOCK_TTL)
        except Exception:
            pass

    async def _clear_cancel_flag(self, session_id: str) -> None:
        try:
            r = await get_redis()
            await r.delete(_cancel_key(session_id))
        except Exception:
            pass

    async def _is_cancelled(self, session_id: str) -> bool:
        try:
            r = await get_redis()
            return bool(await r.exists(_cancel_key(session_id)))
        except Exception:
            return False

    async def start_completion(self, session_id: str) -> Dict[str, Any]:
        """Acquire the cross-worker run lock and dispatch the completion to Celery.

        Idempotent: if the lock is already held (a run is in flight on any
        worker), this is a no-op and just returns the current summary.
        """
        session = await self.load_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        if await self.acquire_run_lock(session_id):
            await self._clear_cancel_flag(session_id)
            from app.workers.tasks import run_group_chat_completion_task
            run_group_chat_completion_task.apply_async(args=[session_id])

        return await self.get_session_summary(session_id)

    async def create_session(
        self,
        user_id: int,
        agent_ids: List[int],
        initial_message: str,
        max_rounds: int = 5,
        parent_conversation_id: Optional[int] = None,
    ) -> str:
        """
        Create a new group chat session.

        Args:
            user_id: ID of the user initiating the chat
            agent_ids: List of agent IDs to include
            initial_message: The starting message/prompt
            max_rounds: Maximum discussion rounds before concluding
            parent_conversation_id: Parent conversation ID for internal agent memory slices

        Returns:
            Session ID string
        """
        import uuid

        session_id = str(uuid.uuid4())

        session = GroupChatSession(
            session_id=session_id,
            user_id=user_id,
            agent_ids=agent_ids,
            max_rounds=max_rounds,
            parent_conversation_id=parent_conversation_id,
        )
        
        # Add initial user message
        session.messages.append(GroupChatMessage(
            role="user",
            content=initial_message,
        ))
        
        self._active_sessions[session_id] = session
        
        # Store in Redis for persistence
        await self._persist_session(session)
        
        return session_id
    
    async def add_message(
        self,
        session_id: str,
        content: str,
        role: str = "user",
        agent_id: Optional[int] = None,
    ) -> GroupChatMessage:
        """
        Add a message to an existing session.
        
        Args:
            session_id: Session to add message to
            content: Message content
            role: Message role (user/agent/system)
            agent_id: Agent ID if role is "agent"
            
        Returns:
            Created GroupChatMessage
        """
        session = self._active_sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        if session.status != "active":
            raise ValueError(f"Session is {session.status}")
        
        message = GroupChatMessage(
            role=role,
            content=content,
            agent_id=agent_id,
        )
        
        session.messages.append(message)
        await self._persist_session(session)
        
        return message
    
    async def run_round(self, session_id: str) -> Dict[str, Any]:
        """
        Run one round of the group chat where each agent responds once.
        
        Args:
            session_id: Session to run round for
            
        Returns:
            Round results with all agent responses
        """
        session = self._active_sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        if session.current_round >= session.max_rounds:
            return {"status": "max_rounds_reached", "session_id": session_id}
        
        session.current_round += 1
        round_responses = []
        
        # Get the latest user message context
        latest_message = session.messages[-1].content if session.messages else ""
        
        # Execute each agent in sequence (could be parallel for efficiency)
        for agent_id in session.agent_ids:
            try:
                result = await self.executor.execute(
                    agent_id=agent_id,
                    task=f"Group chat response to: {latest_message}",
                    user_id=session.user_id,
                    context={"conversation_id": session.parent_conversation_id},
                )
                
                agent_message = GroupChatMessage(
                    role="agent",
                    content=result.get("output") or "No response",
                    agent_id=agent_id,
                    agent_name=result.get("agent_name"),
                )
                
                session.messages.append(agent_message)
                round_responses.append({
                    "agent_id": agent_id,
                    "status": result.get("status"),
                    "output": result.get("output"),
                    "error": result.get("error"),
                })
                
            except Exception as e:
                round_responses.append({
                    "agent_id": agent_id,
                    "status": "error",
                    "error": str(e),
                })
        
        await self._persist_session(session)
        
        return {
            "session_id": session_id,
            "round": session.current_round,
            "responses": round_responses,
        }
    
    async def run_to_completion(self, session_id: str) -> Dict[str, Any]:
        """
        Run the group chat to completion (max_rounds or consensus).
        
        Args:
            session_id: Session to run
            
        Returns:
            Final session results
        """
        session = self._active_sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        # NOTE: re-fetch the session at the top of every iteration. A concurrent
        # request (e.g. a poll that calls load_session) could otherwise replace
        # self._active_sessions[session_id] with a new object, leaving this loop
        # reading a stale `current_round` that never advances — an infinite,
        # non-yielding busy-loop that pins the event loop at 100% CPU and starves
        # every other request (including login). See group-chat hang incident.
        while True:
            session = self._active_sessions.get(session_id)
            if not session or session.status != "active":
                break
            if await self._is_cancelled(session_id):
                session.status = "cancelled"
                break
            if session.current_round >= session.max_rounds:
                break

            round_result = await self.run_round(session_id)
            # run_round is the authority on whether rounds remain; if it reports
            # the cap is reached, stop rather than trusting our local counter.
            if round_result.get("status") == "max_rounds_reached":
                break

            # Check for early termination (all agents agree). Re-fetch first in
            # case the object was swapped during the awaits above.
            session = self._active_sessions.get(session_id)
            if session and await self._check_consensus(session):
                session.status = "completed"
                break

            # Always yield to the event loop between rounds so no single run can
            # monopolise the (single-worker) loop, even if a future round becomes
            # CPU-bound rather than I/O-bound.
            await asyncio.sleep(0)

        session = self._active_sessions.get(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found")
        if session.status == "active":
            session.status = "completed"

        # Generate a master-agent summary of the discussion
        await self._generate_summary(session)

        await self._persist_session(session)

        return await self.get_session_summary(session_id)
    
    async def _check_consensus(self, session: GroupChatSession) -> bool:
        """
        Check if agents have reached consensus.
        
        For now, simple check - all last responses must be similar.
        """
        if len(session.messages) < len(session.agent_ids) + 1:
            return False
        
        # Get last responses from each agent
        agent_responses = [
            m.content for m in session.messages[-len(session.agent_ids):]
            if m.role == "agent"
        ]
        
        if len(agent_responses) < len(session.agent_ids):
            return False
        
        # Simple consensus: responses within 10% similarity (crude heuristic)
        # In production, use embedding similarity
        first_response = (agent_responses[0] or "").lower()
        consensus_threshold = 0.7

        similar_count = sum(
            1 for r in agent_responses[1:]
            if self._text_similarity(first_response, (r or "").lower()) > consensus_threshold
        )
        
        return similar_count >= len(agent_responses) - 1
    
    def _text_similarity(self, text1: str, text2: str) -> float:
        """Simple Jaccard similarity for quick comparison."""
        words1 = set(text1.split())
        words2 = set(text2.split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1 & words2
        union = words1 | words2
        
        return len(intersection) / len(union)

    async def _first_agent_provider_id(self, session: GroupChatSession) -> Optional[int]:
        """Return the llm_provider_id of the first participating agent, or None."""
        if not session.agent_ids:
            return None
        from app.core.database import AsyncSessionLocal
        from app.models.agent import AgentConfig
        from sqlalchemy import select
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(AgentConfig).where(AgentConfig.id == session.agent_ids[0])
            )
            agent_obj = result.scalar_one_or_none()
            return agent_obj.llm_provider_id if agent_obj else None

    async def _generate_summary(self, session: GroupChatSession) -> None:
        """Use the LLM to generate a master-agent summary of the discussion."""
        try:
            from app.services.llm_router import get_llm_router

            # Build a transcript of all agent responses
            transcript_lines: List[str] = []
            for m in session.messages:
                if m.role == "agent" and m.content:
                    name = m.agent_name or f"Agent-{m.agent_id}"
                    transcript_lines.append(f"[{name}]: {m.content}")

            if not transcript_lines:
                return

            provider_id = await self._first_agent_provider_id(session)

            transcript = "\n\n".join(transcript_lines)
            prompt = (
                "You are the Master Agent summarising a multi-agent group discussion. "
                "Below are the responses from each participating agent.\n\n"
                "--- TRANSCRIPT ---\n"
                f"{transcript}\n"
                "--- END ---\n\n"
                "Please provide a concise synthesis:\n"
                "1. Key points of agreement\n"
                "2. Key differences or open questions\n"
                "3. Recommended next steps\n\n"
                "Keep it actionable and under 300 words."
            )

            router = get_llm_router()
            summary_text = await router.chat(
                messages=[{"role": "user", "content": prompt}],
                provider_id=provider_id,
            )

            if summary_text:
                session.messages.append(GroupChatMessage(
                    role="system",
                    content=f"📋 **Discussion Summary**\n\n{summary_text}",
                ))
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to generate group chat summary: {e}")

    async def get_session_summary(self, session_id: str) -> Dict[str, Any]:
        """
        Get a summary of the session.
        
        Args:
            session_id: Session to summarize
            
        Returns:
            Session summary with messages and metadata
        """
        session = self._active_sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        return {
            "session_id": session_id,
            "user_id": session.user_id,
            "agent_ids": session.agent_ids,
            "status": session.status,
            "current_round": session.current_round,
            "max_rounds": session.max_rounds,
            "message_count": len(session.messages),
            "messages": [
                {
                    "role": m.role,
                    "content": m.content,
                    "agent_id": m.agent_id,
                    "agent_name": m.agent_name,
                    "timestamp": m.timestamp,
                }
                for m in session.messages
            ],
            "created_at": session.created_at,
        }
    
    async def _persist_session(self, session: GroupChatSession):
        """Save session to Redis."""
        session_data = {
            "session_id": session.session_id,
            "user_id": session.user_id,
            "agent_ids": session.agent_ids,
            "messages": [
                {
                    "role": m.role,
                    "content": m.content,
                    "agent_id": m.agent_id,
                    "agent_name": m.agent_name,
                    "timestamp": m.timestamp,
                }
                for m in session.messages
            ],
            "max_rounds": session.max_rounds,
            "current_round": session.current_round,
            "status": session.status,
            "created_at": session.created_at,
        }
        
        await cache.set_json(
            f"groupchat:session:{session.session_id}",
            session_data,
            expire=3600 * 24,  # 24 hour expiration
        )
    
    async def load_session(self, session_id: str) -> Optional[GroupChatSession]:
        """
        Load a session from Redis.
        
        Args:
            session_id: Session ID to load
            
        Returns:
            GroupChatSession if found, None otherwise
        """
        # Redis is authoritative. Completion now runs in a Celery worker (a
        # different process from the API workers serving polls), so the original
        # in-process object-swap hazard cannot occur here: no run_to_completion
        # loop shares this process with these polls. Always read fresh state.
        data = await cache.get_json(f"groupchat:session:{session_id}")

        if not data:
            return None

        session = GroupChatSession(
            session_id=data["session_id"],
            user_id=data["user_id"],
            agent_ids=data["agent_ids"],
            max_rounds=data.get("max_rounds", 5),
            current_round=data.get("current_round", 0),
            status=data.get("status", "active"),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
        )
        
        session.messages = [
            GroupChatMessage(
                role=m["role"],
                content=m["content"],
                agent_id=m.get("agent_id"),
                agent_name=m.get("agent_name"),
                timestamp=m.get("timestamp", datetime.now(timezone.utc).isoformat()),
            )
            for m in data.get("messages", [])
        ]
        
        self._active_sessions[session_id] = session
        return session
    
    async def cancel_session(self, session_id: str) -> bool:
        """Cancel an active session (cross-worker).

        Sets status=cancelled in Redis and raises a dedicated cancel flag that
        the Celery completion loop polls each round. The flag is a separate key
        the running task never overwrites, so a cancel cannot be clobbered by
        the task's own end-of-round persist.

        Returns True if cancelled, False if not found.
        """
        session = await self.load_session(session_id)
        if not session:
            return False

        session.status = "cancelled"
        await self._persist_session(session)
        await self._set_cancel_flag(session_id)
        return True


# Singleton instance
_group_chat_service: Optional[GroupChatService] = None


def get_group_chat_service() -> GroupChatService:
    """Get or create group chat service singleton."""
    global _group_chat_service
    if _group_chat_service is None:
        _group_chat_service = GroupChatService()
    return _group_chat_service