"""Tests for group-chat hybrid semantic consensus (issue #14)."""
import pytest

from app.services.group_chat import (
    GroupChatService,
    GroupChatSession,
    GroupChatMessage,
)
from app.services.group_chat import _cosine


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


def test_cosine_identical_is_one():
    assert _cosine([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)


def test_cosine_orthogonal_is_zero():
    assert _cosine([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_cosine_zero_vector_is_zero():
    assert _cosine([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_cosine_length_mismatch_is_zero():
    assert _cosine([1.0, 2.0], [1.0, 2.0, 3.0]) == 0.0


def test_cosine_known_value():
    # angle between (1,0) and (1,1) is 45deg -> cos = 1/sqrt(2)
    assert _cosine([1.0, 0.0], [1.0, 1.0]) == pytest.approx(0.7071, abs=1e-4)


@pytest.mark.asyncio
async def test_first_agent_provider_id_none_when_no_agents():
    service = GroupChatService()
    session = GroupChatSession(session_id="x", user_id=1, agent_ids=[])
    assert await service._first_agent_provider_id(session) is None


@pytest.mark.asyncio
async def test_generate_summary_uses_first_agent_provider_id(monkeypatch):
    service = GroupChatService()
    session = _make_consensus_session(["agent says hello"])

    async def _pid(s):
        return 42
    monkeypatch.setattr(service, "_first_agent_provider_id", _pid)

    fake = FakeRouter(chat_result="summary text")
    monkeypatch.setattr("app.services.llm_router.get_llm_router", lambda: fake)

    await service._generate_summary(session)
    assert fake.chat_calls and fake.chat_calls[0]["provider_id"] == 42


def test_jaccard_consensus_identical_true():
    service = GroupChatService()
    assert service._jaccard_consensus(["block the ip", "block the ip"]) is True


def test_jaccard_consensus_dissimilar_false():
    service = GroupChatService()
    assert service._jaccard_consensus(["block the ip now", "let us order pizza"]) is False


@pytest.mark.asyncio
async def test_judge_yes_true(monkeypatch):
    service = GroupChatService()
    fake = FakeRouter(chat_result="YES")
    monkeypatch.setattr("app.services.llm_router.get_llm_router", lambda: fake)
    assert await service._llm_judge_consensus(["a", "b"], None) is True
    assert fake.chat_calls and fake.chat_calls[0]["provider_id"] is None


@pytest.mark.asyncio
async def test_judge_no_false(monkeypatch):
    service = GroupChatService()
    fake = FakeRouter(chat_result="No, they differ.")
    monkeypatch.setattr("app.services.llm_router.get_llm_router", lambda: fake)
    assert await service._llm_judge_consensus(["a", "b"], None) is False


@pytest.mark.asyncio
async def test_judge_unparseable_none(monkeypatch):
    service = GroupChatService()
    fake = FakeRouter(chat_result="maybe, unclear")
    monkeypatch.setattr("app.services.llm_router.get_llm_router", lambda: fake)
    assert await service._llm_judge_consensus(["a", "b"], None) is None


@pytest.mark.asyncio
async def test_judge_empty_none(monkeypatch):
    service = GroupChatService()
    fake = FakeRouter(chat_result="")
    monkeypatch.setattr("app.services.llm_router.get_llm_router", lambda: fake)
    assert await service._llm_judge_consensus(["a", "b"], None) is None


@pytest.mark.asyncio
async def test_judge_error_none(monkeypatch):
    service = GroupChatService()
    fake = FakeRouter(chat_error=RuntimeError("llm down"))
    monkeypatch.setattr("app.services.llm_router.get_llm_router", lambda: fake)
    assert await service._llm_judge_consensus(["a", "b"], None) is None


def _patch_no_provider(monkeypatch, service):
    async def _no_provider(s):
        return None
    monkeypatch.setattr(service, "_first_agent_provider_id", _no_provider)


@pytest.mark.asyncio
async def test_consensus_all_high_cosine_true_no_judge(monkeypatch):
    service = GroupChatService()
    session = _make_consensus_session(["block the IP", "block the IP now"])
    fake = FakeRouter(embed_result=[[1.0, 0.0], [1.0, 0.0]])  # cos 1.0
    monkeypatch.setattr("app.services.llm_router.get_llm_router", lambda: fake)
    _patch_no_provider(monkeypatch, service)
    judge_calls = {"n": 0}

    async def _judge(responses, provider_id):
        judge_calls["n"] += 1
        return True
    monkeypatch.setattr(service, "_llm_judge_consensus", _judge)

    assert await service._check_consensus(session) is True
    assert judge_calls["n"] == 0


@pytest.mark.asyncio
async def test_consensus_below_low_false_no_judge(monkeypatch):
    service = GroupChatService()
    session = _make_consensus_session(["block the IP", "open all ports"])
    fake = FakeRouter(embed_result=[[1.0, 0.0], [0.0, 1.0]])  # cos 0.0
    monkeypatch.setattr("app.services.llm_router.get_llm_router", lambda: fake)
    _patch_no_provider(monkeypatch, service)
    judge_calls = {"n": 0}

    async def _judge(responses, provider_id):
        judge_calls["n"] += 1
        return True
    monkeypatch.setattr(service, "_llm_judge_consensus", _judge)

    assert await service._check_consensus(session) is False
    assert judge_calls["n"] == 0


@pytest.mark.asyncio
async def test_consensus_gray_band_invokes_judge(monkeypatch):
    service = GroupChatService()
    session = _make_consensus_session(["resp a", "resp b"])
    fake = FakeRouter(embed_result=[[1.0, 0.0], [1.0, 1.0]])  # cos ~0.707 (gray)
    monkeypatch.setattr("app.services.llm_router.get_llm_router", lambda: fake)
    _patch_no_provider(monkeypatch, service)
    judge_calls = {"n": 0}

    async def _judge(responses, provider_id):
        judge_calls["n"] += 1
        return True
    monkeypatch.setattr(service, "_llm_judge_consensus", _judge)

    assert await service._check_consensus(session) is True
    assert judge_calls["n"] == 1


@pytest.mark.asyncio
async def test_consensus_embed_error_routes_to_judge(monkeypatch):
    service = GroupChatService()
    session = _make_consensus_session(["resp a", "resp b"])
    fake = FakeRouter(embed_error=RuntimeError("no embed provider"))
    monkeypatch.setattr("app.services.llm_router.get_llm_router", lambda: fake)
    _patch_no_provider(monkeypatch, service)

    async def _judge(responses, provider_id):
        return False
    monkeypatch.setattr(service, "_llm_judge_consensus", _judge)

    assert await service._check_consensus(session) is False


@pytest.mark.asyncio
async def test_consensus_judge_none_falls_back_to_jaccard(monkeypatch):
    service = GroupChatService()
    # identical responses -> Jaccard returns True
    session = _make_consensus_session(["block the ip now", "block the ip now"])
    fake = FakeRouter(embed_error=RuntimeError("no embed"))
    monkeypatch.setattr("app.services.llm_router.get_llm_router", lambda: fake)
    _patch_no_provider(monkeypatch, service)

    async def _judge(responses, provider_id):
        return None
    monkeypatch.setattr(service, "_llm_judge_consensus", _judge)

    assert await service._check_consensus(session) is True


@pytest.mark.asyncio
async def test_consensus_too_few_messages_false():
    service = GroupChatService()
    session = GroupChatSession(session_id="x", user_id=1, agent_ids=[1, 2])
    session.messages.append(GroupChatMessage(role="user", content="q"))
    assert await service._check_consensus(session) is False
