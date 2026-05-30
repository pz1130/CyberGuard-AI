import { useEffect, useState } from 'react'
import { Plus, Edit2, Trash2, X, Save, Copy, Check } from 'lucide-react'
import { api } from '../api/client'

type Category = 'system' | 'intent_parser' | 'summarizer' | 'general'

interface PromptTemplate {
  id: number
  name: string
  description: string | null
  content: string
  category: Category
  is_active: boolean
  created_at: string
  updated_at: string
}

const CATEGORY_LABELS: Record<Category, string> = {
  system: 'SYSTEM',
  intent_parser: 'INTENT PARSER',
  summarizer: 'SUMMARIZER',
  general: 'GENERAL',
}

const CATEGORY_COLORS: Record<Category, string> = {
  system: 'var(--accent)',
  intent_parser: 'var(--amber, #ffb000)',
  summarizer: 'var(--cyan, #00bcd4)',
  general: 'var(--text-muted)',
}

interface EditState {
  id: number | null
  name: string
  description: string
  content: string
  category: Category
  is_active: boolean
}

const EMPTY_EDIT: EditState = {
  id: null,
  name: '',
  description: '',
  content: '',
  category: 'system',
  is_active: true,
}

export default function Prompts() {
  const [items, setItems] = useState<PromptTemplate[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<'all' | Category>('all')
  const [editorOpen, setEditorOpen] = useState(false)
  const [edit, setEdit] = useState<EditState>(EMPTY_EDIT)
  const [copiedId, setCopiedId] = useState<number | null>(null)
  const [saving, setSaving] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const data = await api.getPromptTemplates() as PromptTemplate[]
      setItems(data || [])
    } catch (e: any) {
      alert(e.message || 'Failed to load prompt templates')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const openCreate = () => {
    setEdit(EMPTY_EDIT)
    setEditorOpen(true)
  }

  const openEdit = (item: PromptTemplate) => {
    setEdit({
      id: item.id,
      name: item.name,
      description: item.description || '',
      content: item.content,
      category: item.category,
      is_active: item.is_active,
    })
    setEditorOpen(true)
  }

  const save = async () => {
    if (!edit.name.trim() || !edit.content.trim()) {
      alert('Name and content are required')
      return
    }
    setSaving(true)
    try {
      const payload = {
        name: edit.name.trim(),
        description: edit.description.trim() || undefined,
        content: edit.content,
        category: edit.category,
        is_active: edit.is_active,
      }
      if (edit.id == null) {
        await api.createPromptTemplate(payload)
      } else {
        await api.updatePromptTemplate(edit.id, payload)
      }
      setEditorOpen(false)
      await load()
    } catch (e: any) {
      alert(e.message || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const remove = async (item: PromptTemplate) => {
    if (!confirm(`Delete prompt template "${item.name}"?`)) return
    try {
      await api.deletePromptTemplate(item.id)
      setItems(prev => prev.filter(i => i.id !== item.id))
    } catch (e: any) {
      alert(e.message || 'Delete failed')
    }
  }

  const copyContent = async (item: PromptTemplate) => {
    try {
      await navigator.clipboard.writeText(item.content)
      setCopiedId(item.id)
      setTimeout(() => setCopiedId(c => c === item.id ? null : c), 1500)
    } catch (e) { console.error('Failed to copy:', e) }
  }

  const filtered = filter === 'all' ? items : items.filter(i => i.category === filter)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <div style={{ fontSize: 20, letterSpacing: '0.06em', color: 'var(--text-primary)' }}>PROMPT TEMPLATES</div>
          <div style={{ fontSize: 12, letterSpacing: '0.1em', color: 'var(--text-dim)', marginTop: 4 }}>
            预定义可复用的 system prompt，会话中可一键填入
          </div>
        </div>
        <button onClick={openCreate} style={{
          padding: '8px 16px', fontSize: 13, letterSpacing: '0.06em',
          background: 'var(--accent)', border: '1px solid var(--accent-border)',
          color: '#000', cursor: 'pointer', fontFamily: 'var(--font-mono)', fontWeight: 700,
          display: 'flex', alignItems: 'center', gap: 6,
        }}>
          <Plus size={12} /> NEW TEMPLATE
        </button>
      </div>

      {/* Filter */}
      <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
        <span style={{ fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-dim)', marginRight: 4 }}>FILTER</span>
        {(['all', 'system', 'intent_parser', 'summarizer', 'general'] as const).map(f => {
          const active = filter === f
          return (
            <button key={f} onClick={() => setFilter(f)} style={{
              padding: '4px 10px', fontSize: 12, letterSpacing: '0.1em',
              background: active ? 'var(--accent-dim)' : 'transparent',
              border: `1px solid ${active ? 'var(--accent-border)' : 'var(--border-bright)'}`,
              color: active ? 'var(--accent)' : 'var(--text-muted)',
              cursor: 'pointer', fontFamily: 'var(--font-mono)',
            }}>
              {f === 'all' ? 'ALL' : CATEGORY_LABELS[f as Category]}
            </button>
          )
        })}
      </div>

      {/* List */}
      {loading ? (
        <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-dim)', fontSize: 13, letterSpacing: '0.06em' }}>
          LOADING...
        </div>
      ) : filtered.length === 0 ? (
        <div style={{
          padding: 40, textAlign: 'center', color: 'var(--text-dim)', fontSize: 13, letterSpacing: '0.06em',
          border: '1px dashed var(--border-bright)', background: 'var(--bg-surface)',
        }}>
          NO TEMPLATES — CLICK "NEW TEMPLATE" TO CREATE ONE
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))', gap: 12 }}>
          {filtered.map(item => (
            <div key={item.id} style={{
              border: '1px solid var(--border)', background: 'var(--bg-surface)',
              padding: 14, display: 'flex', flexDirection: 'column', gap: 8,
              opacity: item.is_active ? 1 : 0.5,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1, minWidth: 0 }}>
                  <span style={{
                    fontSize: 11, letterSpacing: '0.12em', padding: '2px 6px',
                    border: `1px solid ${CATEGORY_COLORS[item.category]}`,
                    color: CATEGORY_COLORS[item.category],
                  }}>
                    {CATEGORY_LABELS[item.category]}
                  </span>
                  <span style={{
                    fontSize: 15, color: 'var(--text-primary)', fontWeight: 600,
                    whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                  }}>{item.name}</span>
                </div>
                <div style={{ display: 'flex', gap: 4 }}>
                  <button onClick={() => copyContent(item)} title="Copy content"
                    style={{ padding: 4, background: 'none', border: 'none', color: 'var(--text-dim)', cursor: 'pointer' }}>
                    {copiedId === item.id ? <Check size={12} style={{ color: 'var(--accent)' }} /> : <Copy size={12} />}
                  </button>
                  <button onClick={() => openEdit(item)} title="Edit"
                    style={{ padding: 4, background: 'none', border: 'none', color: 'var(--text-dim)', cursor: 'pointer' }}>
                    <Edit2 size={12} />
                  </button>
                  <button onClick={() => remove(item)} title="Delete"
                    style={{ padding: 4, background: 'none', border: 'none', color: 'var(--red)', cursor: 'pointer' }}>
                    <Trash2 size={12} />
                  </button>
                </div>
              </div>
              {item.description && (
                <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5 }}>{item.description}</div>
              )}
              <div style={{
                fontSize: 13, color: 'var(--text-muted)', lineHeight: 1.5,
                fontFamily: 'var(--font-mono)', background: 'var(--bg-base)',
                border: '1px solid var(--border)', padding: '8px 10px',
                maxHeight: 96, overflow: 'hidden',
                whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                position: 'relative',
              }}>
                {item.content.length > 280 ? item.content.slice(0, 280) + '\n…' : item.content}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Editor modal */}
      {editorOpen && (
        <div onClick={() => !saving && setEditorOpen(false)} style={{
          position: 'fixed', inset: 0, zIndex: 9999,
          background: 'rgba(0,0,0,0.75)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          padding: 20,
        }}>
          <div onClick={e => e.stopPropagation()} style={{
            width: '100%', maxWidth: 720, maxHeight: '90vh',
            background: 'var(--bg-surface)', border: '1px solid var(--border-bright)',
            display: 'flex', flexDirection: 'column',
          }}>
            <div style={{
              padding: '14px 18px', borderBottom: '1px solid var(--border)',
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            }}>
              <span style={{ fontSize: 14, letterSpacing: '0.06em', color: 'var(--accent)' }}>
                {edit.id == null ? '+ NEW PROMPT TEMPLATE' : '◆ EDIT PROMPT TEMPLATE'}
              </span>
              <button onClick={() => !saving && setEditorOpen(false)} disabled={saving}
                style={{ padding: 4, background: 'none', border: 'none', color: 'var(--text-dim)', cursor: 'pointer' }}>
                <X size={14} />
              </button>
            </div>
            <div style={{ padding: 18, display: 'flex', flexDirection: 'column', gap: 14, overflowY: 'auto' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 12 }}>
                <div>
                  <div style={{ fontSize: 12, letterSpacing: '0.1em', color: 'var(--text-muted)', marginBottom: 6 }}>NAME</div>
                  <input value={edit.name} onChange={e => setEdit(s => ({ ...s, name: e.target.value }))}
                    placeholder="e.g. Security Auditor"
                    style={inputStyle}
                  />
                </div>
                <div>
                  <div style={{ fontSize: 12, letterSpacing: '0.1em', color: 'var(--text-muted)', marginBottom: 6 }}>CATEGORY</div>
                  <select value={edit.category} onChange={e => setEdit(s => ({ ...s, category: e.target.value as Category }))} style={inputStyle}>
                    <option value="system">System Prompt</option>
                    <option value="intent_parser">Intent Parser</option>
                    <option value="summarizer">Summarizer</option>
                    <option value="general">General</option>
                  </select>
                </div>
              </div>
              <div>
                <div style={{ fontSize: 12, letterSpacing: '0.1em', color: 'var(--text-muted)', marginBottom: 6 }}>DESCRIPTION (OPTIONAL)</div>
                <input value={edit.description} onChange={e => setEdit(s => ({ ...s, description: e.target.value }))}
                  placeholder="Short note shown next to the name"
                  style={inputStyle}
                />
              </div>
              <div>
                <div style={{ fontSize: 12, letterSpacing: '0.1em', color: 'var(--text-muted)', marginBottom: 6 }}>CONTENT</div>
                <textarea value={edit.content} onChange={e => setEdit(s => ({ ...s, content: e.target.value }))}
                  rows={14}
                  placeholder="The full prompt text. Will be applied verbatim."
                  style={{ ...inputStyle, height: 'auto', minHeight: 280, resize: 'vertical', lineHeight: 1.6 }}
                />
              </div>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: 'var(--text-muted)', cursor: 'pointer' }}>
                <input type="checkbox" checked={edit.is_active} onChange={e => setEdit(s => ({ ...s, is_active: e.target.checked }))} />
                <span style={{ letterSpacing: '0.1em' }}>ACTIVE (shown in Chat picker)</span>
              </label>
            </div>
            <div style={{
              padding: '12px 18px', borderTop: '1px solid var(--border)',
              display: 'flex', justifyContent: 'flex-end', gap: 8,
            }}>
              <button onClick={() => setEditorOpen(false)} disabled={saving}
                style={{
                  padding: '8px 16px', fontSize: 13, letterSpacing: '0.1em',
                  border: '1px solid var(--border-bright)', background: 'transparent',
                  color: 'var(--text-muted)', cursor: saving ? 'not-allowed' : 'pointer',
                  fontFamily: 'var(--font-mono)',
                }}>
                CANCEL
              </button>
              <button onClick={save} disabled={saving}
                style={{
                  padding: '8px 16px', fontSize: 13, letterSpacing: '0.1em',
                  background: 'var(--accent)', border: '1px solid var(--accent-border)',
                  color: '#000', cursor: saving ? 'not-allowed' : 'pointer',
                  fontFamily: 'var(--font-mono)', fontWeight: 700,
                  display: 'flex', alignItems: 'center', gap: 6,
                  opacity: saving ? 0.6 : 1,
                }}>
                <Save size={12} /> {saving ? 'SAVING...' : 'SAVE'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

const inputStyle: React.CSSProperties = {
  width: '100%', height: 32, padding: '0 10px',
  background: 'var(--bg-base)', border: '1px solid var(--border-bright)',
  color: 'var(--text-primary)', fontSize: 14, fontFamily: 'var(--font-mono)',
  outline: 'none',
}
