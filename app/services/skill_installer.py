"""Skill installation from URL, single file, or a zipped skill bundle.

Three upload shapes are supported:

* ``.md`` / ``.markdown`` — a SKILL.md body with optional YAML frontmatter.
* ``.json`` — an explicit skill record.
* ``.zip`` — the general skill layout (``<skill>/SKILL.md`` plus
  ``references/``, ``scripts/``, ``assets/`` …).  Every ``SKILL.md`` found in
  the archive becomes one skill; sibling files become that skill's bundle.

Everything that parses an archive treats it as hostile input: entry count,
uncompressed size, path shape and symlinks are all bounded before any member
is read.
"""
from __future__ import annotations

import io
import json
import mimetypes
import posixpath
import re
import stat
import zipfile
from typing import Any, Dict, List, Optional, Tuple

import httpx
import yaml

# --- limits (all enforced before any archive member is decompressed) ---
MAX_UPLOAD_BYTES = 10 * 1024 * 1024        # request payload cap
MAX_ZIP_ENTRIES = 500                      # members per archive
MAX_BUNDLE_FILE_BYTES = 2 * 1024 * 1024    # per extracted member
MAX_UNCOMPRESSED_TOTAL_BYTES = 10 * 1024 * 1024  # whole archive, inflated
MAX_COMPRESSION_RATIO = 100                # inflated / stored, per member

_SKILL_MD = "skill.md"
_MARKDOWN_SUFFIXES = (".md", ".markdown")

# Directory/file noise that must never become a bundle file.
_SKIP_DIR_PARTS = {"__MACOSX", ".git", ".github", "node_modules", "__pycache__"}
_SKIP_BASENAMES = {".DS_Store", "Thumbs.db"}

# Frontmatter keys that map onto Skill columns; anything else is preserved
# under metadata_json["frontmatter"] rather than being silently dropped.
_KNOWN_FRONTMATTER_KEYS = {
    "name", "description", "version", "category", "type",
    "permission_level", "requires_approval", "tags", "source",
}

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


# --- frontmatter ---------------------------------------------------------

def _parse_frontmatter_fallback(block: str) -> Dict[str, Any]:
    """Flat ``key: value`` parsing, used when the YAML is not well-formed."""
    meta: Dict[str, Any] = {}
    for line in block.split("\n"):
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key or not value:
            continue
        if value.lower() == "true":
            meta[key] = True
        elif value.lower() == "false":
            meta[key] = False
        else:
            meta[key] = value
    return meta


def _parse_frontmatter(content: str) -> Tuple[Dict[str, Any], str]:
    """Parse YAML frontmatter from markdown.

    Returns ``(metadata, body_without_frontmatter)``.  Lists and nested maps
    survive (``allowed-tools``, ``tags`` …).  Malformed YAML degrades to the
    flat key/value parser instead of failing the whole import.
    """
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return {}, content

    block = match.group(1)
    body = content[match.end():]

    try:
        loaded = yaml.safe_load(block)
    except yaml.YAMLError:
        return _parse_frontmatter_fallback(block), body

    if not isinstance(loaded, dict):
        return _parse_frontmatter_fallback(block), body
    return {str(k): v for k, v in loaded.items()}, body


def _coerce_tags(value: Any) -> Optional[List[str]]:
    if value is None:
        return None
    if isinstance(value, str):
        tags = [t.strip() for t in value.split(",")]
    elif isinstance(value, (list, tuple, set)):
        tags = [str(t).strip() for t in value]
    else:
        return None
    tags = [t for t in tags if t]
    return tags or None


def _normalize_skill_data(
    name: str,
    meta: Dict[str, Any],
    md_content: str,
    *,
    source: str = "import",
) -> Dict[str, Any]:
    """Build a Skill column dict from parsed metadata and body."""
    extra = {k: v for k, v in meta.items() if k not in _KNOWN_FRONTMATTER_KEYS}
    metadata_json: Dict[str, Any] = {
        "source": meta.get("source", source),
        "original_name": name,
    }
    if extra:
        metadata_json["frontmatter"] = extra

    category = meta.get("category") or meta.get("type") or None
    return {
        "name": str(meta.get("name") or name).strip(),
        "description": str(meta.get("description") or "")[:500],
        "version": str(meta.get("version") or "1.0.0"),
        "category": str(category) if category else None,
        "permission_level": str(meta.get("permission_level") or "medium"),
        "requires_approval": bool(meta.get("requires_approval", False)),
        "md_content": md_content,
        "is_active": True,
        "tags": _coerce_tags(meta.get("tags")),
        "metadata_json": metadata_json,
    }


# --- single-file parsing -------------------------------------------------

def _name_from_filename(filename: str) -> str:
    stem = posixpath.basename(filename.replace("\\", "/")).strip()
    for suffix in (*_MARKDOWN_SUFFIXES, ".json", ".zip"):
        if stem.lower().endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    return stem.strip() or "imported-skill"


def install_skill_from_content(source: str, content: str) -> Dict[str, Any]:
    """Parse one markdown skill.  Returns ``{success, skill_data}`` or an error.

    Kept as the single-skill contract used by the URL installer.
    """
    try:
        meta, body = _parse_frontmatter(content)
        skill_data = _normalize_skill_data(_name_from_filename(source), meta, body)

        if not skill_data["name"]:
            return {"success": False, "error": "Skill name could not be determined"}
        if not skill_data["md_content"].strip():
            return {"success": False, "error": "Skill content is empty"}
        return {"success": True, "skill_data": skill_data}
    except Exception as e:  # noqa: BLE001 - surfaced to the caller as an error string
        return {"success": False, "error": f"Parse error: {str(e)}"}


def _parse_skill_json(filename: str, text: str) -> Dict[str, Any]:
    """Parse an explicit skill record supplied as JSON."""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"Invalid JSON: {e.msg} (line {e.lineno})"}
    if not isinstance(payload, dict):
        return {"success": False, "error": "Invalid JSON: expected a skill object"}

    body = ""
    for key in ("md_content", "content", "body", "markdown", "instructions"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            body = value
            break
    if not body.strip():
        return {
            "success": False,
            "error": "JSON skill has no body (expected 'md_content', 'content' or 'body')",
        }

    meta = {k: v for k, v in payload.items() if k not in
            {"md_content", "content", "body", "markdown", "instructions"}}
    skill_data = _normalize_skill_data(_name_from_filename(filename), meta, body)
    if not skill_data["name"]:
        return {"success": False, "error": "Skill name could not be determined"}
    return {"success": True, "skill_data": skill_data}


# --- zip bundles ---------------------------------------------------------

class _BundleError(Exception):
    """A zip archive violated a structural or size constraint."""


def _safe_member_path(name: str) -> str:
    """Normalize a zip member path, rejecting anything that escapes the root."""
    normalized = name.replace("\\", "/")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:/", normalized):
        raise _BundleError(f"Unsafe path in archive (absolute): {name}")
    parts = [p for p in normalized.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise _BundleError(f"Unsafe path in archive (traversal): {name}")
    return "/".join(parts)


def _is_noise(path: str) -> bool:
    parts = path.split("/")
    if any(p in _SKIP_DIR_PARTS for p in parts[:-1]):
        return True
    if parts[0] in _SKIP_DIR_PARTS:
        return True
    return parts[-1] in _SKIP_BASENAMES


def _scan_zip(data: bytes) -> Tuple[zipfile.ZipFile, Dict[str, zipfile.ZipInfo]]:
    """Open the archive and validate every member before anything is read."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise _BundleError("File is not a valid zip archive")

    infos = [i for i in zf.infolist() if not i.is_dir()]
    if len(infos) > MAX_ZIP_ENTRIES:
        raise _BundleError(
            f"Archive has too many entries ({len(infos)} > {MAX_ZIP_ENTRIES})"
        )

    members: Dict[str, zipfile.ZipInfo] = {}
    total = 0
    for info in infos:
        path = _safe_member_path(info.filename)
        if stat.S_ISLNK(info.external_attr >> 16):
            raise _BundleError(f"Archive contains a symlink entry: {info.filename}")
        if info.file_size > MAX_BUNDLE_FILE_BYTES:
            raise _BundleError(
                f"File '{path}' is too large "
                f"({info.file_size} bytes > {MAX_BUNDLE_FILE_BYTES})"
            )
        if info.compress_size > 0 and (
            info.file_size / info.compress_size > MAX_COMPRESSION_RATIO
        ):
            raise _BundleError(f"File '{path}' has a suspicious compression ratio")
        total += info.file_size
        if total > MAX_UNCOMPRESSED_TOTAL_BYTES:
            raise _BundleError(
                "Archive contents are too large when uncompressed "
                f"(> {MAX_UNCOMPRESSED_TOTAL_BYTES} bytes)"
            )
        if not _is_noise(path):
            members[path] = info
    return zf, members


def _read_member(zf: zipfile.ZipFile, info: zipfile.ZipInfo, path: str) -> bytes:
    with zf.open(info) as fh:
        payload = fh.read(MAX_BUNDLE_FILE_BYTES + 1)
    if len(payload) > MAX_BUNDLE_FILE_BYTES:
        raise _BundleError(f"File '{path}' is too large when uncompressed")
    return payload


def _bundle_file(path: str, payload: bytes) -> Dict[str, Any]:
    """Split an extracted member into the text or binary column."""
    guessed, _ = mimetypes.guess_type(path)
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        return {
            "path": path,
            "content_text": None,
            "content_blob": payload,
            "size_bytes": len(payload),
            "mime": guessed or "application/octet-stream",
        }
    return {
        "path": path,
        "content_text": text,
        "content_blob": None,
        "size_bytes": len(payload),
        "mime": guessed or "text/plain",
    }


def _skill_roots(members: Dict[str, zipfile.ZipInfo]) -> Dict[str, str]:
    """Map ``skill root dir -> SKILL.md member path`` for every skill found."""
    roots: Dict[str, str] = {}
    for path in members:
        if posixpath.basename(path).lower() == _SKILL_MD:
            roots[posixpath.dirname(path)] = path
    return roots


def _install_from_zip(filename: str, data: bytes) -> Dict[str, Any]:
    zf, members = _scan_zip(data)
    roots = _skill_roots(members)

    if not roots:
        # A zipped single skill file is still a reasonable thing to upload.
        loose = [p for p in members if p.lower().endswith(_MARKDOWN_SUFFIXES)]
        if len(loose) == 1:
            payload = _read_member(zf, members[loose[0]], loose[0])
            text = _decode_utf8(payload, loose[0])
            single = install_skill_from_content(loose[0], text)
            if not single["success"]:
                return single
            return {"success": True, "skills": [{"skill_data": single["skill_data"], "files": []}]}
        raise _BundleError(
            "No SKILL.md found in the archive. A skill bundle needs a "
            "SKILL.md at its root (e.g. my-skill/SKILL.md)."
        )

    sorted_roots = sorted(roots, key=len, reverse=True)
    skills: List[Dict[str, Any]] = []

    for root in sorted(roots):
        skill_md_path = roots[root]
        prefix = f"{root}/" if root else ""
        # A deeper root owns its own subtree, so this skill stops there.
        nested = [r for r in sorted_roots if r != root and r.startswith(prefix)]

        body_bytes = _read_member(zf, members[skill_md_path], skill_md_path)
        meta, body = _parse_frontmatter(_decode_utf8(body_bytes, skill_md_path))
        fallback = posixpath.basename(root) or _name_from_filename(filename)
        skill_data = _normalize_skill_data(fallback, meta, body, source="zip-import")
        if not skill_data["name"]:
            raise _BundleError(f"Skill name could not be determined for '{skill_md_path}'")
        if not skill_data["md_content"].strip():
            raise _BundleError(f"'{skill_md_path}' has an empty body")

        files: List[Dict[str, Any]] = []
        for path, info in members.items():
            if path == skill_md_path or not path.startswith(prefix):
                continue
            if any(path.startswith(f"{n}/") or path == n for n in nested):
                continue
            relative = path[len(prefix):]
            files.append(_bundle_file(relative, _read_member(zf, info, path)))

        files.sort(key=lambda f: f["path"])
        skills.append({"skill_data": skill_data, "files": files})

    return {"success": True, "skills": skills}


def _decode_utf8(payload: bytes, label: str) -> str:
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError:
        raise _BundleError(f"'{label}' must be UTF-8 encoded")


# --- unified upload entry point -----------------------------------------

def install_skills_from_upload(filename: str, data: bytes) -> Dict[str, Any]:
    """Parse an uploaded skill file into one or more skills.

    Returns ``{"success": True, "skills": [{"skill_data": …, "files": […]}]}``
    or ``{"success": False, "error": …}``.  ``files`` is always present and is
    empty for the single-file formats.
    """
    if len(data) > MAX_UPLOAD_BYTES:
        return {
            "success": False,
            "error": f"File is too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB)",
        }

    lowered = (filename or "").lower()
    try:
        if lowered.endswith(".zip"):
            return _install_from_zip(filename, data)

        if lowered.endswith(".json"):
            result = _parse_skill_json(filename, _decode_utf8(data, filename))
        elif lowered.endswith(_MARKDOWN_SUFFIXES) or not lowered:
            result = install_skill_from_content(filename, _decode_utf8(data, filename))
        else:
            return {
                "success": False,
                "error": "Unsupported file type. Upload a .md, .json, or .zip "
                         "skill bundle (SKILL.md at the bundle root).",
            }
    except _BundleError as e:
        return {"success": False, "error": str(e)}

    if not result["success"]:
        return result
    return {"success": True, "skills": [{"skill_data": result["skill_data"], "files": []}]}


# --- URL install ---------------------------------------------------------

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
