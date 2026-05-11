# Chat File & Image Upload — Design Spec

**Date:** 2026-05-10
**Status:** Approved

---

## Overview

Add file/image attachment support to the Chat.tsx chat interface. Users can attach up to 10 images and/or documents to a message, preview them before sending, and receive responses from the LLM based on all attached content.

---

## Supported Formats

| Type | Formats |
|------|---------|
| Images | `png`, `jpg`, `jpeg`, `gif`, `webp` |
| Documents | `pdf`, `doc`, `docx`, `xls`, `xlsx`, `ppt`, `pptx`, `txt`, `md`, `csv`, `json` |

**Limit:** Max 10 files per message.

---

## UI Design

### Theme
Follow existing CyberGuard terminal aesthetic: dark background (`#050505`), phosphor green accent (`#00ff41`), JetBrains Mono font, dashed-border upload zones.

### Layout

```
[ File Preview Area — stacked chips above input ]
[ Image: thumbnail  ]
[ Doc: filename.type + icon + × ]
...
[ Input Row ]
[ 📎 ] [ textarea                               ] [ SEND ]
```

### Components

**Upload Button**
- Position: left of textarea
- Icon: paperclip/attachment icon (Lucide `Paperclip` or `Upload`)
- Triggers hidden `<input type="file" multiple>`
- Styled with border, transparent background, `--text-muted` color

**File Preview Chips**
- Position: above textarea input row, collapses when empty
- **Image:** small square thumbnail (48x48px, object-cover), click to open lightbox/preview
- **Document:** filename text + file type badge + × remove button, monospace font, green border
- Each chip has a remove (×) button to deselect before sending

**Lightbox for Images**
- Clicking image thumbnail opens a modal/overlay showing full-size image
- Simple overlay with close button, dark background

**Send Button**
- Sends all text + all file attachments as one message
- Disabled while loading or no input

---

## Data Flow

1. User clicks upload button → file picker opens
2. User selects up to 10 files → preview chips render in preview area
3. User types message + clicks Send
4. Frontend reads files as `File[]`, sends to backend via `FormData` (multipart)
5. Backend stores/handles files, sends to LLM with message text
6. Backend returns task_id, polling proceeds as normal
7. Response displays in chat as usual

### Frontend API (client.ts)

```typescript
// New method — uploads files as FormData
uploadChatAttachments: (files: File[], message: string, conversationId: number, modelOverride?: object) => {
  const token = localStorage.getItem('token')
  const fd = new FormData()
  files.forEach(f => fd.append('files', f))
  fd.append('message', message)
  fd.append('conversation_id', String(conversationId))
  if (modelOverride) fd.append('model_override', JSON.stringify(modelOverride))
  return fetch(`${BASE}/chat/attachments`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: fd,
  }).then(r => r.json())
}
```

---

## Backend Interface Required

**New endpoint:** `POST /chat/attachments`
- Accepts: `multipart/form-data`
- Fields: `files` (multiple), `message` (string), `conversation_id` (int), `model_override` (optional JSON string)
- Returns: `{ task_id: string, status: string, message: string }` (same shape as `/chat`)
- Behavior: forwards files + text to LLM for multimodal processing

**Backend responsibility:** If `/chat` does not currently support file uploads, implement `/chat/attachments` as a parallel endpoint that wraps the same task-dispatch logic but includes file handling (extracting text from PDFs/docs, passing images to vision-capable models).

---

## File Structure Changes

```
webui/src/
  pages/Chat.tsx          — add upload state, file chips, upload button, lightbox
  api/client.ts           — add uploadChatAttachments() method
```

---

## Error Handling

- File type not supported → alert user before sending
- More than 10 files → alert user, reject extras
- Upload fails → show error in chat as assistant message
- Empty message + only files → send allowed (just the files as content)

---

## Scope

**In scope:**
- Chat.tsx UI changes (upload button, preview chips, image lightbox)
- client.ts API method
- Backend `/chat/attachments` endpoint (coordinate with backend agent if separate)

**Out of scope:**
- Drag-and-drop (can be added later)
- Progress bar during upload
- File download from chat history (viewing attachments in old messages)
- GroupChat / other chat pages