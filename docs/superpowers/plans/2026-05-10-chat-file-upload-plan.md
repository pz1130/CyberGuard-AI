# Chat File & Image Upload — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable users to attach up to 10 images/documents to a chat message in Chat.tsx, with pre-upload preview and LLM processing of all content.

**Architecture:** Frontend adds a file input + preview chips to Chat.tsx and sends files as FormData to a new `/chat/attachments` backend endpoint. Backend extracts text from documents and passes images to vision-capable LLM models.

**Tech Stack:** React (existing Chat.tsx), FastAPI (existing backend), Python Celery worker, Lucide icons

---

## File Map

```
webui/src/
  pages/Chat.tsx          — MODIFY: add upload state, preview chips, upload button, lightbox
  api/client.ts          — MODIFY: add uploadChatAttachments() FormData method

app/
  routers/chat.py        — MODIFY: add /chat/attachments endpoint (multipart)
  schemas/chat.py        — MODIFY: add ChatAttachmentsRequest schema
```

---

## Backend Changes

### Task 1: New Schema — ChatAttachmentsRequest

**Files:**
- Modify: `app/schemas/chat.py`

- [ ] **Step 1: Read existing chat.py schema**

```python
# Read app/schemas/chat.py to see current ChatRequest / AgentChatRequest
```

- [ ] **Step 2: Add ChatAttachmentsRequest schema**

```python
from fastapi import File, UploadFile, Form
from typing import Optional, List

class ChatAttachmentsRequest(BaseModel):
    message: str = Field(..., description="Text message content")
    conversation_id: Optional[int] = None
    agent_id: Optional[str] = None
    provider_id: Optional[int] = None
    model: Optional[str] = None

# Alternative: use Form fields directly in router instead of schema
```

**Note:** Since this endpoint uses `multipart/form-data`, the request body cannot be a Pydantic model with `File`/`UploadFile` fields the same way. The router will read `Form()` fields directly.

---

### Task 2: New Endpoint — POST /chat/attachments

**Files:**
- Modify: `app/routers/chat.py`

- [ ] **Step 1: Read current chat.py router**

Read `app/routers/chat.py` to understand current `chat()` endpoint, imports, and dependencies.

- [ ] **Step 2: Add new endpoint**

Add after the existing `chat()` endpoint:

```python
@router.post("/chat/attachments", status_code=status.HTTP_202_ACCEPTED)
async def chat_attachments(
    message: str = Form(...),
    conversation_id: Optional[int] = Form(None),
    agent_id: Optional[str] = Form(None),
    provider_id: Optional[int] = Form(None),
    model: Optional[str] = Form(None),
    files: List[UploadFile] = File(default=[]),
):
    """
    Accept file attachments + text message, forward to Celery worker for LLM processing.
    Supports images (png, jpg, gif, webp) and documents (pdf, doc, docx, txt, md, csv, json, xls, xlsx, ppt, pptx).
    Max 10 files.
    """
    if len(files) > 10:
        raise HTTPException(status_code=400, detail="Max 10 files allowed")

    # Validate file types
    allowed_image_types = {"image/png", "image/jpeg", "image/gif", "image/webp"}
    allowed_doc_types = {
        "application/pdf", "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/plain", "text/markdown", "text/csv",
        "application/json",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-powerpoint",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    }
    for f in files:
        if f.content_type not in allowed_image_types | allowed_doc_types:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {f.content_type} ({f.filename})"
            )

    # Read file contents
    file_contents: list[dict] = []
    for f in files:
        content = await f.read()
        file_contents.append({
            "filename": f.filename,
            "content_type": f.content_type,
            "content": base64.b64encode(content).decode("utf-8"),
        })

    # Build task payload (same as regular /chat but with attachments)
    from app.tasks.master import process_chat_task
    task = process_chat_task.apply_async(kwargs={
        "message": message,
        "agent_id": agent_id,
        "provider_id": provider_id,
        "model": model,
        "conversation_id": conversation_id,
        "attachments": file_contents,
    })
    return {"task_id": task.id, "status": "accepted", "message": "Task dispatched"}
```

- [ ] **Step 3: Add required imports**

Add to top of `app/routers/chat.py`:
```python
from typing import List, Optional
from fastapi import File, UploadFile, Form, HTTPException, status
import base64
```

---

## Frontend Changes

### Task 3: API Method — uploadChatAttachments()

**Files:**
- Modify: `webui/src/api/client.ts`

- [ ] **Step 1: Read client.ts to find the chat: method**

Read `webui/src/api/client.ts` around line 105.

- [ ] **Step 2: Add uploadChatAttachments method**

Add after the existing `chat:` method:

```typescript
// Chat with attachments (multipart/form-data)
uploadChatAttachments: (
  files: File[],
  message: string,
  conversationId: number,
  modelOverride?: { provider_id?: number; model?: string },
  agentId?: string,
) => {
  const token = localStorage.getItem('token')
  const fd = new FormData()
  files.forEach(f => fd.append('files', f))
  fd.append('message', message)
  fd.append('conversation_id', String(conversationId))
  if (modelOverride?.provider_id) fd.append('provider_id', String(modelOverride.provider_id))
  if (modelOverride?.model) fd.append('model', modelOverride.model)
  if (agentId) fd.append('agent_id', agentId)
  return fetch(`${BASE}/chat/attachments`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: fd,
  }).then(async r => {
    if (!r.ok) throw new Error(await r.text())
    return r.json()
  })
},
```

---

### Task 4: Chat.tsx — Upload State & Preview

**Files:**
- Modify: `webui/src/pages/Chat.tsx`

- [ ] **Step 1: Add new imports**

Add to the import list (around line 4):
```tsx
import { Paperclip, X, Image as ImageIcon, FileText } from 'lucide-react'
```

- [ ] **Step 2: Add file type constant**

Add after the FALLBACK_MODELS constant (around line 50):
```typescript
const ACCEPTED_IMAGE_TYPES = ['image/png', 'image/jpeg', 'image/gif', 'image/webp']
const ACCEPTED_DOC_TYPES = [
  'application/pdf',
  'application/msword',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'text/plain',
  'text/markdown',
  'text/csv',
  'application/json',
  'application/vnd.ms-excel',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'application/vnd.ms-powerpoint',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation',
]
const MAX_FILES = 10

interface AttachmentFile {
  file: File
  previewUrl: string
}
```

- [ ] **Step 3: Add state variables**

Add after the `convSettings` state (around line 82):
```typescript
const [attachments, setAttachments] = useState<AttachmentFile[]>([])
const fileInputRef = useRef<HTMLInputElement>(null)
const [lightboxUrl, setLightboxUrl] = useState<string | null>(null)
```

- [ ] **Step 4: Add file input JSX**

Find the input area (around line 631), add before the textarea:
```tsx
<input
  ref={fileInputRef}
  type="file"
  multiple
  accept={[...ACCEPTED_IMAGE_TYPES, ...ACCEPTED_DOC_TYPES].join(',')}
  onChange={(e) => {
    const files = Array.from(e.target.files || [])
    if (files.length + attachments.length > MAX_FILES) {
      alert(`最多上传 ${MAX_FILES} 个文件`)
      return
    }
    const newAttachments = files.map(f => ({
      file: f,
      previewUrl: ACCEPTED_IMAGE_TYPES.includes(f.type)
        ? URL.createObjectURL(f)
        : '',
    }))
    setAttachments(prev => [...prev, ...newAttachments])
    e.target.value = ''
  }}
  style={{ display: 'none' }}
/>
```

- [ ] **Step 5: Add attachment preview chips**

Add after the file input, above the textarea row:
```tsx
{attachments.length > 0 && (
  <div style={{
    padding: '8px 16px',
    display: 'flex',
    flexWrap: 'wrap',
    gap: 8,
    borderTop: '1px solid var(--border)',
    background: 'var(--bg-base)',
  }}>
    {attachments.map((att, i) => (
      <div key={i} style={{
        display: 'flex',
        alignItems: 'center',
        gap: 4,
        padding: '4px 8px',
        border: '1px solid var(--accent-border)',
        background: 'var(--accent-dim)',
        fontSize: 10,
        fontFamily: 'var(--font-mono)',
        color: 'var(--text-primary)',
      }}>
        {ACCEPTED_IMAGE_TYPES.includes(att.file.type) ? (
          <ImageIcon size={10} style={{ color: 'var(--accent)' }} />
        ) : (
          <FileText size={10} style={{ color: 'var(--accent)' }} />
        )}
        <span style={{ maxWidth: 100, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {att.file.name}
        </span>
        <button
          onClick={() => {
            setAttachments(prev => prev.filter((_, idx) => idx !== i))
          }}
          style={{
            padding: 0, background: 'none', border: 'none',
            color: 'var(--text-dim)', cursor: 'pointer', display: 'flex',
          }}>
          <X size={10} />
        </button>
      </div>
    ))}
  </div>
)}
```

- [ ] **Step 6: Add upload button**

Add before the textarea (line 632 area):
```tsx
<button
  onClick={() => fileInputRef.current?.click()}
  disabled={!activeConvId || loading}
  style={{
    width: 36, height: 36, flexShrink: 0,
    border: '1px solid var(--border-bright)',
    background: 'transparent',
    color: activeConvId && !loading ? 'var(--text-muted)' : 'var(--text-dim)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    cursor: activeConvId && !loading ? 'pointer' : 'not-allowed',
    opacity: activeConvId && !loading ? 1 : 0.5,
  }}>
  <Paperclip size={14} />
</button>
```

- [ ] **Step 7: Add lightbox overlay**

Add at the bottom of the return statement (inside the main div, after the input row):
```tsx
{lightboxUrl && (
  <div
    onClick={() => setLightboxUrl(null)}
    style={{
      position: 'fixed', inset: 0, zIndex: 9999,
      background: 'rgba(0,0,0,0.9)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      cursor: 'pointer',
    }}>
    <img
      src={lightboxUrl}
      style={{ maxWidth: '90vw', maxHeight: '90vh', objectFit: 'contain' }}
      onClick={e => e.stopPropagation()}
    />
    <button
      onClick={() => setLightboxUrl(null)}
      style={{
        position: 'absolute', top: 16, right: 16,
        padding: 8, background: 'var(--bg-elevated)',
        border: '1px solid var(--border-bright)',
        color: 'var(--text-primary)', cursor: 'pointer',
        fontSize: 11, fontFamily: 'var(--font-mono)',
      }}>
      CLOSE
    </button>
  </div>
)}
```

---

### Task 5: Chat.tsx — Update send() to use attachments

**Files:**
- Modify: `webui/src/pages/Chat.tsx`

- [ ] **Step 1: Find the send() function**

Located around line 316. Replace the `send` function body to handle attachments.

- [ ] **Step 2: Update send() to branch on attachments**

Replace the `send` async function with:

```typescript
const send = async () => {
  if ((!input.trim() && attachments.length === 0) || loading) return
  if (!activeConvId) {
    alert('请先创建或选择一个会话')
    return
  }

  const userMsg: Message = {
    role: 'user',
    content: input.trim() || (attachments.length > 0 ? `[${attachments.length} 个附件]` : ''),
    created_at: new Date().toISOString(),
  }
  setMessages(prev => [...prev, userMsg])
  setInput('')
  setLoading(true)
  setPollingStatus(attachments.length > 0 ? 'UPLOADING ATTACHMENTS...' : 'DISPATCHING TASK...')

  // Show image previews in message bubbles immediately
  const attachmentPreviews = attachments.map(att => {
    if (ACCEPTED_IMAGE_TYPES.includes(att.file.type)) {
      return { type: 'image', url: att.previewUrl, name: att.file.name }
    } else {
      return { type: 'doc', name: att.file.name, size: att.file.size }
    }
  })

  try {
    const files = attachments.map(a => a.file)
    const modelOverride = getModelOverride()

    const chatResp = files.length > 0
      ? await api.uploadChatAttachments(
          files,
          input.trim(),
          activeConvId,
          Object.keys(modelOverride).length > 0 ? modelOverride : undefined,
        ) as { task_id: string; status: string; message: string }
      : await api.chat({ message: input.trim(), conversation_id: activeConvId, ...modelOverride }) as { task_id: string; status: string; message: string }

    // Clear attachments after successful send
    attachments.forEach(att => {
      if (att.previewUrl) URL.revokeObjectURL(att.previewUrl)
    })
    setAttachments([])

    const taskId = chatResp.task_id
    activeTaskIdRef.current = taskId
    localStorage.setItem('activeChatTaskId', taskId)

    if (pollIntervalRef.current) clearInterval(pollIntervalRef.current)
    let seconds = 0
    pollIntervalRef.current = setInterval(async () => {
      seconds += 2
      if (!isMountedRef.current) return
      setPollingStatus(`PROCESSING... (${seconds}s)`)
      const task = await pollForResult(taskId)
      if (!isMountedRef.current) return
      if (task?.status === 'completed' || task?.status === 'failed') {
        clearInterval(pollIntervalRef.current!)
        pollIntervalRef.current = null
        activeTaskIdRef.current = null
        localStorage.removeItem('activeChatTaskId')
        handleTaskResult(task)
        setLoading(false)
        setPollingStatus('')
      }
    }, 2000)
  } catch (e: any) {
    setMessages(prev => [...prev, { role: 'assistant', content: `⚠ SYSTEM ERROR — ${e?.message || 'TRANSMISSION FAILURE'}`, created_at: new Date().toISOString() }])
    setLoading(false)
    setPollingStatus('')
  }
}
```

- [ ] **Step 3: Update send button disabled state**

Find the send button (around line 645) and update the disabled condition:
```tsx
disabled={!activeConvId || loading || (!input.trim() && attachments.length === 0)}
```

---

### Task 6: Chat.tsx — Render Attachment Previews in Messages

**Files:**
- Modify: `webui/src/pages/Chat.tsx`

- [ ] **Step 1: Find the message rendering section**

Around line 605-619, inside the messages.map render.

- [ ] **Step 2: Add attachment display in user messages**

After the existing `div` containing the message content (before `{msg.created_at && ...}`), add:

```tsx
{/* Render attachment previews for user messages */}
{msg.role === 'user' && attachmentPreviews.length > 0 && (
  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 6 }}>
    {attachmentPreviews.map((att, i) =>
      att.type === 'image' ? (
        <div key={i} style={{ position: 'relative' }}>
          <img
            src={att.url}
            onClick={() => setLightboxUrl(att.url)}
            style={{
              width: 64, height: 64, objectFit: 'cover',
              border: '1px solid var(--accent-border)',
              cursor: 'pointer',
            }}
          />
        </div>
      ) : (
        <div key={i} style={{
          display: 'flex', alignItems: 'center', gap: 4,
          padding: '4px 8px',
          border: '1px solid var(--accent-border)',
          fontSize: 10, fontFamily: 'var(--font-mono)',
          color: 'var(--text-muted)',
        }}>
          <FileText size={10} />
          <span>{att.name}</span>
        </div>
      )
    )}
  </div>
)}
```

**Note:** `attachmentPreviews` should be a derived value from `attachments` state. Since it needs to show the current batch of attachments that were just sent, we store it in the message render. Actually, we need to store attachment metadata in the Message itself so old messages still show their attachments. Update the `Message` interface:

- [ ] **Step 3: Update Message interface to support attachments**

At the top of the file (around line 6-10):

```typescript
interface Message {
  role: 'user' | 'assistant' | 'system'
  content: string
  created_at?: string
  attachments?: Array<{
    type: 'image' | 'doc'
    url?: string   // for images
    name: string
    size?: number  // for docs
  }>
}
```

- [ ] **Step 4: Update userMsg creation in send() to include attachments**

In the send() function, update userMsg creation:

```typescript
const attachmentData = attachments.map(att => ({
  type: (ACCEPTED_IMAGE_TYPES.includes(att.file.type) ? 'image' : 'doc') as 'image' | 'doc',
  url: att.previewUrl,
  name: att.file.name,
  size: att.file.size,
}))

const userMsg: Message = {
  role: 'user',
  content: input.trim() || (attachments.length > 0 ? `[${attachments.length} 个附件]` : ''),
  created_at: new Date().toISOString(),
  attachments: attachmentData,
}
```

---

## Validation & Self-Review Checklist

- [ ] Spec coverage: All spec requirements implemented (upload button, preview chips, lightbox, 10-file limit, mixed images/docs)
- [ ] No placeholders: All code blocks are complete, no "TBD" or "TODO"
- [ ] Type consistency: `uploadChatAttachments()` method signature matches how it's called in Chat.tsx send()
- [ ] File type validation matches between frontend (`ACCEPTED_IMAGE_TYPES`, `ACCEPTED_DOC_TYPES`) and backend
- [ ] Memory cleaned: `URL.revokeObjectURL()` called on cleanup when attachments are sent or component unmounts
- [ ] Send disabled when no input and no attachments
- [ ] Lightbox closes on background click, image click stops propagation