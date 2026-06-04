import { useEffect, useState, useContext } from 'react'
import { useTranslation } from 'react-i18next'
import { Plus, Edit2, Trash2, Save, Copy, Check } from 'lucide-react'
import { api } from '../api/client'
import { SearchContext } from '../context/SearchContext'
import Modal from '../components/Modal'

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
  const { t } = useTranslation()
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

  const { searchTarget, setSearchTarget } = useContext(SearchContext)
  useEffect(() => {
    if (!searchTarget || searchTarget.tab !== 'prompts') return
    const el = document.querySelector(`[data-item-id="${searchTarget.id}"]`)
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' })
      el.classList.add('search-highlight')
    }
    const t = setTimeout(() => setSearchTarget(null), 2000)
    return () => clearTimeout(t)
  }, [searchTarget, setSearchTarget])

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
          <div style={{ fontSize: 20, letterSpacing: '0.06em', color: 'var(--text-primary)' }}>{t('prompts.title').toUpperCase()}</div>
          <div style={{ fontSize: 12, letterSpacing: '0.1em', color: 'var(--text-dim)', marginTop: 4 }}>
            预定义可复用的 system prompt，会话中可一键填入
          </div>
        </div>
        <button onClick={openCreate} style={{
          padding: '8px 16px', fontSize: 13, letterSpacing: '0.06em',
          background: 'var(--accent)', border: '1px solid var(--accent-border)',
          color: '#000', cursor: 'pointer', fontWeight: 700,
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
              cursor: 'pointer',             }}>
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
            <div key={item.id} data-item-id={item.id} style={{
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
                background: 'var(--bg-base)',
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
        <Modal
          width={720}
          title={edit.id == null ? 'NEW PROMPT TEMPLATE' : 'EDIT PROMPT TEMPLATE'}
          onClose={() => { if (!saving) setEditorOpen(false) }}
          footer={(
            <>
              <button onClick={() => setEditorOpen(false)} disabled={saving} className="btn btn-secondary">
                CANCEL
              </button>
              <button onClick={save} disabled={saving} className="btn btn-primary" style={{ opacity: saving ? 0.6 : 1 }}>
                <Save size={12} /> {saving ? 'SAVING...' : 'SAVE'}
              </button>
            </>
          )}
        >
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 12 }}>
            <div>
              <label className="form-label">NAME</label>
              <input value={edit.name} onChange={e => setEdit(s => ({ ...s, name: e.target.value }))}
                placeholder="e.g. Security Auditor"
                className="form-input"
              />
            </div>
            <div>
              <label className="form-label">CATEGORY</label>
              <select value={edit.category} onChange={e => setEdit(s => ({ ...s, category: e.target.value as Category }))} className="form-input">
                <option value="system">System Prompt</option>
                <option value="intent_parser">Intent Parser</option>
                <option value="summarizer">Summarizer</option>
                <option value="general">General</option>
              </select>
            </div>
          </div>
          <div>
            <label className="form-label">DESCRIPTION (OPTIONAL)</label>
            <input value={edit.description} onChange={e => setEdit(s => ({ ...s, description: e.target.value }))}
              placeholder="Short note shown next to the name"
              className="form-input"
            />
          </div>
          <div>
            <label className="form-label">CONTENT</label>
            <textarea value={edit.content} onChange={e => setEdit(s => ({ ...s, content: e.target.value }))}
              rows={14}
              placeholder="The full prompt text. Will be applied verbatim."
              className="form-textarea"
              style={{ minHeight: 280, lineHeight: 1.6 }}
            />
          </div>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: 'var(--text-muted)', cursor: 'pointer' }}>
            <input type="checkbox" checked={edit.is_active} onChange={e => setEdit(s => ({ ...s, is_active: e.target.checked }))} />
            <span style={{ letterSpacing: '0.1em' }}>ACTIVE (shown in Chat picker)</span>
          </label>
        </Modal>
      )}
    </div>
  )
}
