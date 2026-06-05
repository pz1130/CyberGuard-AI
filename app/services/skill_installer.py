"""Skill installation from URL or file import."""
import re
import httpx
from typing import Optional, Dict, Any, Tuple
from datetime import datetime


# Simple frontmatter parser (no PyYAML dependency)
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_frontmatter(content: str) -> Tuple[Dict[str, Any], str]:
    """
    Parse YAML frontmatter from markdown content.

    Returns (metadata_dict, body_without_frontmatter).
    If no frontmatter found, returns ({}, original_content).
    """
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return {}, content

    frontmatter_block = match.group(1)
    body = content[match.end():]

    # Simple key: value parsing (no nested structures)
    meta: Dict[str, Any] = {}
    for line in frontmatter_block.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value:
            # Handle booleans
            if value.lower() == "true":
                value = True
            elif value.lower() == "false":
                value = False
            meta[key] = value

    return meta, body


def _normalize_skill_data(
    name: str,
    meta: Dict[str, Any],
    md_content: str,
) -> Dict[str, Any]:
    """Build a skill dict from parsed metadata and body."""
    return {
        "name": meta.get("name", name),
        "description": meta.get("description", ""),
        "version": meta.get("version", "1.0.0"),
        "category": meta.get("category", meta.get("type", None)),
        "permission_level": meta.get("permission_level", "medium"),
        "requires_approval": meta.get("requires_approval", False),
        "md_content": md_content,
        "is_active": True,
        "metadata_json": {
            "source": meta.get("source", "import"),
            "original_name": name,
        },
    }


def _resolve_to_raw_skill_url(url: str) -> str:
    """
    Resolve common skill viewer / blob URLs to direct raw Markdown URLs.

    Supports:
    - https://www.skills.sh/{owner}/{repo}/{skill}  → raw .../skills/{skill}/SKILL.md
    - GitHub blob URLs → raw.githubusercontent.com
    """
    from urllib.parse import urlparse, urlunparse

    parsed = urlparse(url.strip())
    host = parsed.netloc.lower()
    path = parsed.path.strip("/")

    # skills.sh viewer pages (e.g. https://www.skills.sh/vercel-labs/skills/find-skills)
    if host in ("skills.sh", "www.skills.sh"):
        parts = [p for p in path.split("/") if p]
        if len(parts) >= 3:
            owner, repo, skill = parts[0], parts[1], parts[2]
            # Common layout in vercel-labs style repos
            return f"https://raw.githubusercontent.com/{owner}/{repo}/main/skills/{skill}/SKILL.md"
        # Fallback: try to treat last segment as skill and guess
        if len(parts) >= 2:
            owner, repo = parts[0], parts[1]
            if len(parts) > 2:
                skill = parts[2]
                return f"https://raw.githubusercontent.com/{owner}/{repo}/main/skills/{skill}/SKILL.md"
        return url

    # GitHub blob view → raw
    if "github.com" in host and "/blob/" in path:
        raw_path = path.replace("/blob/", "/raw/", 1)
        return urlunparse(("https", "raw.githubusercontent.com", raw_path, "", "", ""))

    # Already raw or direct .md link — leave as-is
    return url


async def install_skill_from_url(
    url: str,
    headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Fetch a skill from a URL and parse its frontmatter.

    Automatically resolves skills.sh pages and GitHub blob URLs to raw .md.
    """
    original_url = url
    url = _resolve_to_raw_skill_url(url)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers or {})
            response.raise_for_status()
            content = response.text

            # Guard against still getting HTML (e.g. wrong path, private repo without auth, etc.)
            c = content.strip().lower()
            if c.startswith("<!doctype") or c.startswith("<html") or "<html" in c[:200]:
                hint = ""
                if "skills.sh" in original_url.lower():
                    hint = " (skills.sh page resolved; check that the skill name matches the repo layout)"
                return {
                    "success": False,
                    "error": "Fetched content looks like an HTML web page (not raw Markdown). "
                             "Use the raw URL (e.g. raw.githubusercontent.com or 'Raw' button on GitHub)."
                             + hint,
                }
    except httpx.TimeoutException:
        return {"success": False, "error": "Request timed out"}
    except httpx.HTTPStatusError as e:
        return {"success": False, "error": f"HTTP {e.response.status_code}: {e.response.text[:200]}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

    return install_skill_from_content(url, content)


def install_skill_from_content(
    source: str,
    content: str,
) -> Dict[str, Any]:
    """
    Parse skill content and return skill data ready for DB insertion.

    Args:
        source: URL or filename used as fallback name
        content: Full file content (may contain YAML frontmatter)

    Returns:
        Dict with success=True and skill_data, or success=False and error
    """
    try:
        meta, body = _parse_frontmatter(content)

        # Derive name from source URL/filename if not in frontmatter
        name = meta.get("name", "")
        if not name:
            # Try to extract filename from URL or path
            name = source.split("/")[-1].replace(".md", "").replace(".markdown", "").strip()
            if not name:
                name = "imported-skill"

        skill_data = _normalize_skill_data(name, meta, body)

        # Basic validation
        if not skill_data["name"]:
            return {"success": False, "error": "Skill name could not be determined"}
        if not skill_data["md_content"].strip():
            return {"success": False, "error": "Skill content is empty"}

        return {"success": True, "skill_data": skill_data}
    except Exception as e:
        return {"success": False, "error": f"Parse error: {str(e)}"}
