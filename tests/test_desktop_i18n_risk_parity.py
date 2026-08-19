"""预设任务中英两版必须命中同一组风险关键词。

否则「告警分诊」在中文下要审批、切英文后不要——同一个按钮在两种语言下
审批行为不一致，这是 INV-06 层面的问题，不是文案问题。

测试放 Python 侧是因为 RISK_KEYWORDS 的唯一事实源在 plan_mode.py，
在 TS 里复制一份清单等于埋一颗漂移的雷。
"""
import json
import pathlib

import pytest

from apps.desktop.sidecar import plan_mode

I18N = pathlib.Path(__file__).resolve().parents[1] / "apps/desktop/renderer/i18n"


def _load(name: str) -> dict:
    return json.loads((I18N / name).read_text(encoding="utf-8"))


def _sample_text_keys(zh: dict) -> list[str]:
    return sorted(k for k in zh if k.startswith("sample.") and k.endswith(".text"))


def test_sample_text_keys_exist():
    zh = _load("zh.json")
    assert _sample_text_keys(zh), "没找到 sample.*.text，预设任务的 key 命名变了？"


@pytest.mark.parametrize("key", _sample_text_keys(_load("zh.json")))
def test_risk_keyword_parity(key: str):
    zh, en = _load("zh.json"), _load("en.json")
    assert key in en, f"{key} 缺英文版"
    zh_hit = plan_mode._task_has_risk_keyword(zh[key])
    en_hit = plan_mode._task_has_risk_keyword(en[key])
    assert zh_hit == en_hit, (
        f"{key} 两版风险判定不一致：zh={zh_hit} en={en_hit}。"
        "同一个预设在两种语言下审批行为必须一致（INV-06）"
    )
