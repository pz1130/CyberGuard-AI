"""Shared validation for multipart file uploads.

Single source of truth for allowed MIME types, the per-file size cap, and
magic-byte anti-spoofing for chat attachments.
"""
from fastapi import HTTPException, UploadFile, status

ALLOWED_ATTACHMENT_TYPES = {
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/json",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB per file

# Magic byte signatures for spoofing detection (claimed type must match content).
_MAGIC_BYTES = {
    "image/png": b"\x89PNG\r\n\x1a\n",
    "image/jpeg": b"\xff\xd8\xff",
    "image/gif": b"GIF8",
    "image/webp": b"RIFF",
    "application/pdf": b"%PDF",
    "application/msword": b"\xd0\xcf\x11\xe0",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": b"PK",
    "application/vnd.ms-excel": b"\xd0\xcf\x11\xe0",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": b"PK",
    "application/vnd.ms-powerpoint": b"\xd0\xcf\x11\xe0",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": b"PK",
}


async def validate_and_read_upload(file: UploadFile) -> tuple[bytes, str]:
    """Validate an UploadFile's type/size/magic-bytes; return (content, mime).

    Raises HTTPException(400) on any violation. Mirrors the checks previously
    inlined in the chat-attachments endpoint.
    """
    if file.content_type not in ALLOWED_ATTACHMENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {file.content_type}. "
                   f"Allowed: {', '.join(sorted(ALLOWED_ATTACHMENT_TYPES))}",
        )
    if file.size is not None and file.size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File '{file.filename}' exceeds maximum size of "
                   f"{MAX_FILE_SIZE // (1024 * 1024)} MB",
        )
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File '{file.filename}' exceeds maximum size of "
                   f"{MAX_FILE_SIZE // (1024 * 1024)} MB",
        )
    expected = _MAGIC_BYTES.get(file.content_type)
    if expected is not None and len(content) >= len(expected):
        if content[:len(expected)] != expected:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File '{file.filename}' content does not match declared "
                       f"type '{file.content_type}'",
            )
    return content, file.content_type
