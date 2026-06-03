"""Tests for group-chat hybrid semantic consensus (issue #14)."""
import pytest

from app.services.group_chat import (
    GroupChatService,
    GroupChatSession,
    GroupChatMessage,
)


class FakeRouter:
    """Stand-in for the LLM router. Configure embed/chat results or errors."""

    def __init__(self, *, embed_result=None, embed_error=None,
                 chat_result=None, chat_error=None):
        self.embed_result = embed_result
        self.embed_error = embed_error
        self.chat_result = chat_result
        self.chat_error = chat_error
        self.embed_calls = []
        self.chat_calls = []

    async def embed(self, texts, model=None, provider_id=None):
        self.embed_calls.append({"texts": texts, "provider_id": provider_id})
        if self.embed_error is not None:
            raise self.embed_error
        return self.embed_result

    async def chat(self, messages=None, provider_id=None, **kwargs):
        self.chat_calls.append({"messages": messages, "provider_id": provider_id})
        if self.chat_error is not None:
            raise self.chat_error
        return self.chat_result


def _make_consensus_session(responses):
    """A session with one user msg + one agent msg per response."""
    s = GroupChatSession(
        session_id="consensus-test",
        user_id=1,
        agent_ids=list(range(1, len(responses) + 1)),
    )
    s.messages.append(GroupChatMessage(role="user", content="question"))
    for i, r in enumerate(responses):
        s.messages.append(GroupChatMessage(role="agent", content=r, agent_id=i + 1))
    return s


def test_groupchat_consensus_settings_defaults():
    from app.config import settings
    assert settings.GROUPCHAT_CONSENSUS_HIGH == 0.85
    assert settings.GROUPCHAT_CONSENSUS_LOW == 0.65
    assert settings.GROUPCHAT_JACCARD_THRESHOLD == 0.7
