"""Session settings must be clearable. Explicit JSON null is a write, not a skip."""
from types import SimpleNamespace
import uuid

import pytest

from app.core.auth import AuthenticatedUser
from app.core.database import AsyncSessionLocal
from app.models.conversation import Conversation
from app.models.user import User
from app.routers.conversations import ConversationUpdate, apply_conversation_update
from app.routers.conversations import update_conversation


def test_omitted_fields_do_not_appear_in_the_update_payload():
    body = ConversationUpdate.model_validate({"title": "kept"})
    dumped = body.model_dump(exclude_unset=True)
    assert dumped == {"title": "kept"}


def test_explicit_null_is_present_so_overrides_can_be_cleared():
    body = ConversationUpdate.model_validate({
        "system_prompt_override": None,
        "knowledge_base_id": None,
        "temperature_override": None,
    })
    dumped = body.model_dump(exclude_unset=True)
    assert dumped["system_prompt_override"] is None
    assert dumped["knowledge_base_id"] is None
    assert dumped["temperature_override"] is None


def test_apply_update_clears_knowledge_base_and_prompt_when_null_is_sent():
    conv = SimpleNamespace(
        title="session",
        messages_json="[]",
        system_prompt_override="custom",
        intent_parser_prompt_override="intent",
        summarizer_prompt_override="sum",
        model_override="old-model",
        temperature_override=0.2,
        knowledge_base_id=9,
    )
    body = ConversationUpdate.model_validate({
        "system_prompt_override": None,
        "knowledge_base_id": None,
        "title": "session",
    })
    apply_conversation_update(conv, body)
    assert conv.system_prompt_override is None
    assert conv.knowledge_base_id is None
    assert conv.title == "session"
    assert conv.temperature_override == 0.2


def test_apply_update_does_not_blank_title_when_title_is_omitted():
    conv = SimpleNamespace(title="keep me", knowledge_base_id=3)
    apply_conversation_update(conv, ConversationUpdate.model_validate({
        "knowledge_base_id": 4,
    }))
    assert conv.title == "keep me"
    assert conv.knowledge_base_id == 4


@pytest.mark.asyncio
async def test_update_route_clears_overrides_in_postgres():
    """Exercise the route's commit against PostgreSQL, not only a mock object."""
    suffix = uuid.uuid4().hex[:10]
    async with AsyncSessionLocal() as db:
        user = User(
            username=f"conversation_update_{suffix}",
            email=f"conversation_update_{suffix}@example.test",
            hashed_password="test-only",
            role="admin",
            is_active=True,
        )
        db.add(user)
        await db.flush()
        conv = Conversation(
            user_id=user.id,
            title="clearable settings",
            messages_json="[]",
            system_prompt_override="custom prompt",
        )
        db.add(conv)
        await db.commit()
        await db.refresh(conv)
        user_id = user.id
        conv_id = conv.id

        try:
            current_user = AuthenticatedUser(
                user_id=user_id,
                username=user.username,
                email=user.email,
                role=user.role,
            )
            response = await update_conversation(
                conv_id,
                ConversationUpdate.model_validate({
                    "system_prompt_override": None,
                    "knowledge_base_id": None,
                }),
                db,
                current_user,
            )

            assert response.system_prompt_override is None
            assert response.knowledge_base_id is None

            await db.refresh(conv)
            assert conv.system_prompt_override is None
            assert conv.knowledge_base_id is None
            assert conv.updated_at.tzinfo is None
        finally:
            await db.rollback()
            await db.execute(
                Conversation.__table__.delete().where(Conversation.user_id == user_id)
            )
            await db.execute(User.__table__.delete().where(User.id == user_id))
            await db.commit()
