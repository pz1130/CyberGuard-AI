"""Group chat service for multi-agent discussions."""
import json
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

from app.core.redis_client import cache
from app.services.agent_executor import AgentExecutor


@dataclass
class GroupChatMessage:
    """A single message in a group chat."""
    role: str  # "user", "agent", or "system"
    content: str
    agent_id: Optional[int] = None
    agent_name: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class GroupChatSession:
    """A group chat session involving multiple agents."""
    session_id: str
    user_id: int
    agent_ids: List[int]
    messages: List[GroupChatMessage] = field(default_factory=list)
    max_rounds: int = 5
    current_round: int = 0
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    status: str = "active"  # active, completed, cancelled


class GroupChatService:
    """
    Service for managing group chat sessions between multiple agents.
    
    Supports round-robin discussions, consensus building, and result aggregation.
    """
    
    def __init__(self):
        self.executor = AgentExecutor()
        self._active_sessions: Dict[str, GroupChatSession] = {}
    
    async def create_session(
        self,
        user_id: int,
        agent_ids: List[int],
        initial_message: str,
        max_rounds: int = 5,
    ) -> str:
        """
        Create a new group chat session.
        
        Args:
            user_id: ID of the user initiating the chat
            agent_ids: List of agent IDs to include
            initial_message: The starting message/prompt
            max_rounds: Maximum discussion rounds before concluding
            
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
                )
                
                agent_message = GroupChatMessage(
                    role="agent",
                    content=result.get("output", "No response"),
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
        
        while session.current_round < session.max_rounds and session.status == "active":
            round_result = await self.run_round(session_id)
            
            # Check for early termination (all agents agree)
            if await self._check_consensus(session):
                session.status = "completed"
                break
        
        if session.status == "active":
            session.status = "completed"
        
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
        first_response = agent_responses[0].lower()
        consensus_threshold = 0.7
        
        similar_count = sum(
            1 for r in agent_responses[1:]
            if self._text_similarity(first_response, r.lower()) > consensus_threshold
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
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
        )
        
        session.messages = [
            GroupChatMessage(
                role=m["role"],
                content=m["content"],
                agent_id=m.get("agent_id"),
                agent_name=m.get("agent_name"),
                timestamp=m.get("timestamp", datetime.utcnow().isoformat()),
            )
            for m in data.get("messages", [])
        ]
        
        self._active_sessions[session_id] = session
        return session
    
    async def cancel_session(self, session_id: str) -> bool:
        """
        Cancel an active session.
        
        Args:
            session_id: Session to cancel
            
        Returns:
            True if cancelled, False if not found
        """
        session = self._active_sessions.get(session_id)
        if not session:
            return False
        
        session.status = "cancelled"
        await self._persist_session(session)
        return True


# Singleton instance
_group_chat_service: Optional[GroupChatService] = None


def get_group_chat_service() -> GroupChatService:
    """Get or create group chat service singleton."""
    global _group_chat_service
    if _group_chat_service is None:
        _group_chat_service = GroupChatService()
    return _group_chat_service