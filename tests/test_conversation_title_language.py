"""A conversation title must not be born in one particular language.

Two separate defects met here. The placeholder was a Chinese literal stored in
the database, so an English UI showed Chinese for any conversation that never
got a real title. And the placeholder doubled as the "not yet titled" sentinel,
so translating it without touching the comparisons would have stopped
auto-titling silently — the title would simply never change, with no error.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
CJK = re.compile(r"[一-鿿]")


def _code_lines(path: Path):
    """Lines that are code, not comments or docstrings."""
    for i, line in enumerate(path.read_text().split("\n"), 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        yield i, line


def test_the_placeholder_is_not_a_chinese_literal():
    from app.models.conversation import Conversation

    default = Conversation.__table__.columns["title"].default
    assert default is None or not CJK.search(str(getattr(default, "arg", ""))), (
        "the stored placeholder must not be in any one language"
    )


def test_the_title_column_accepts_no_title():
    from app.models.conversation import Conversation

    assert Conversation.__table__.columns["title"].nullable is True, (
        "an untitled conversation needs a way to say so"
    )


@pytest.mark.parametrize("path", [
    "app/routers/conversations.py",
    "app/routers/chat_stream.py",
    "app/workers/tasks.py",
    "app/models/conversation.py",
])
def test_no_chinese_title_literals_remain(path):
    offenders = [
        f"{path}:{i}: {line.strip()}"
        for i, line in _code_lines(REPO / path)
        if CJK.search(line) and ("title" in line or "对话" in line)
    ]
    assert offenders == [], "Chinese title literals:\n" + "\n".join(offenders)


@pytest.mark.parametrize("path,marker", [
    ("app/routers/chat_stream.py", "Write a short title"),
    ("app/workers/tasks.py", "Write a short title"),
])
def test_the_auto_title_prompt_does_not_force_a_language(path, marker):
    """A Chinese prompt yields Chinese titles whatever the UI is set to."""
    source = (REPO / path).read_text()
    assert marker in source, f"{path} should ask for a title in a neutral way"


def test_auto_titling_keys_off_an_absent_title_not_a_magic_string():
    """The sentinel must be "no title", so it cannot drift from the placeholder."""
    for path in ("app/routers/chat_stream.py", "app/workers/tasks.py"):
        source = (REPO / path).read_text()
        assert "新对话" not in source, f"{path} still compares against a Chinese literal"


def test_the_response_schema_allows_an_absent_title():
    """The model can return None now; a required str would 500 on every read."""
    from app.routers.conversations import ConversationResponse

    field = ConversationResponse.model_fields["title"]
    assert not field.is_required()


def test_the_schema_carries_no_language_specific_default():
    """The column default lived in the database, so the Python change alone
    would have left new rows getting Chinese from Postgres itself."""
    migration = (REPO / "alembic" / "versions" /
                 "040_conv_title_no_default.py").read_text()
    assert "ALTER COLUMN title DROP DEFAULT" in migration
