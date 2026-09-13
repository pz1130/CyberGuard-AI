"""Chat must collapse the same think-tag variants the backend strips.

MiniMax / Qwen / DeepSeek emit <think>, <think>0, <think>_1, <think>abc, not
only the bare <think> token. The WebUI splitter has to accept those openings
or the raw markers leak into the answer.
"""
from pathlib import Path
import re

REASONING_TS = (
    Path(__file__).resolve().parents[1] / "webui" / "src" / "lib" / "splitReasoningContent.ts"
)


def test_chat_opening_tag_accepts_think_attribute_variants():
    src = REASONING_TS.read_text(encoding="utf-8")
    assert re.search(r"think\[\^>\]\*", src), (
        "splitReasoningContent.ts must match <think...> openings, not only <think>"
    )


def split_reasoning_content(content: str):
    """Mirror of webui/src/pages/Chat.tsx splitReasoningContent."""
    reasoning = []
    answer = ""
    cursor = 0
    opening = re.compile(r"<(think[^>]*|reasoning)>", re.I)
    for match in opening.finditer(content):
        answer += content[cursor:match.start()]
        body_start = match.end()
        name = match.group(1)
        close_name = "think" if name.lower().startswith("think") else "reasoning"
        closing = re.search(rf"</{close_name}>", content[body_start:], re.I)
        if not closing:
            partial = content[body_start:].strip()
            if partial:
                reasoning.append(partial)
            cursor = len(content)
            break
        body = content[body_start:body_start + closing.start()].strip()
        if body:
            reasoning.append(body)
        cursor = body_start + closing.end()
    answer += content[cursor:]
    answer = re.sub(r"</(?:think|reasoning)>", "", answer, flags=re.I)
    return reasoning, answer


def test_bare_think_and_reasoning_tags_collapse():
    reasoning, answer = split_reasoning_content(
        "<think>secret</think>visible <reasoning>r</reasoning>ok"
    )
    assert reasoning == ["secret", "r"]
    assert "secret" not in answer and "visible" in answer and "ok" in answer


def test_think_suffix_variants_collapse():
    for raw in (
        "<think>0\nhidden</think>\nvisible",
        "<think_1>hidden</think>visible",
        "<think abc>hidden</think>visible",
    ):
        reasoning, answer = split_reasoning_content(raw)
        assert any("hidden" in part for part in reasoning), raw
        assert "hidden" not in answer and "visible" in answer, raw
        assert "<think" not in answer.lower(), raw
