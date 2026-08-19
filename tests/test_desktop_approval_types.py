"""approval_type 的取值集合是渲染层标题映射的事实源。

渲染层 usePlan.tsx 的 APPROVAL_LABEL_KEYS 按 approval_type 查词条；
sidecar 若新增第三种审批类型而渲染层没跟上，英文界面会漏出中文
ui_label（11-OPEN-QUESTIONS §K.1）。这条测试钉住集合，新增即红。
"""
from __future__ import annotations

import json
import pathlib
import re

I18N = pathlib.Path(__file__).resolve().parents[1] / "apps/desktop/renderer/i18n"
USE_PLAN = (
    pathlib.Path(__file__).resolve().parents[1]
    / "apps/desktop/renderer/state/usePlan.tsx"
)

KNOWN_APPROVAL_TYPES = {"self", "segregation"}


def _renderer_mapped_types() -> set[str]:
    src = USE_PLAN.read_text(encoding="utf-8")
    block = re.search(
        r"APPROVAL_LABEL_KEYS:\s*Record<string, string>\s*=\s*\{(.*?)\}",
        src,
        re.S,
    )
    assert block, "没找到 APPROVAL_LABEL_KEYS —— 渲染层改名了？"
    return set(re.findall(r"^\s*(\w+):", block.group(1), re.M))


def test_sidecar_approval_types_unchanged():
    """plan_mode 只产出 self / segregation。加第三种时本测试会红。"""
    from apps.desktop.sidecar import plan_mode

    src = pathlib.Path(plan_mode.__file__).read_text(encoding="utf-8")
    found = set(re.findall(r'approval_type\s*==\s*"(\w+)"', src))
    found |= set(re.findall(r'approval_type[:=]\s*"(\w+)"', src))
    unknown = found - KNOWN_APPROVAL_TYPES
    assert not unknown, (
        f"plan_mode.py 出现新的 approval_type: {sorted(unknown)}。"
        "请同步 renderer/state/usePlan.tsx 的 APPROVAL_LABEL_KEYS "
        "与 i18n/{zh,en}.json 的词条，否则英文界面会漏出中文 ui_label"
    )


def test_renderer_covers_every_approval_type():
    """渲染层映射表必须覆盖全部已知类型。"""
    missing = KNOWN_APPROVAL_TYPES - _renderer_mapped_types()
    assert not missing, f"usePlan.tsx 的 APPROVAL_LABEL_KEYS 缺: {sorted(missing)}"


def test_mapped_keys_exist_in_both_locales():
    """映射到的词条 key 两份词条里都得有，否则英文回落中文。"""
    src = USE_PLAN.read_text(encoding="utf-8")
    keys = set(re.findall(r'"(plan\.\w+)"', src))
    zh = json.loads((I18N / "zh.json").read_text(encoding="utf-8"))
    en = json.loads((I18N / "en.json").read_text(encoding="utf-8"))
    for k in sorted(keys):
        assert k in zh, f"{k} 缺中文词条"
        assert k in en, f"{k} 缺英文词条"
