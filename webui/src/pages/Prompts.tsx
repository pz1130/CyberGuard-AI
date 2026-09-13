import { useEffect, useState, useContext, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { Plus, Edit2, Trash2, Save, Copy, Check } from 'lucide-react'
import PageHeader from '../components/PageHeader'
import { api } from '../api/client'
import { SearchContext } from '../context/search'
import { errorMessage } from '../lib/errorMessage'
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

const CATEGORY_KEYS: Record<Category, string> = {
  system: 'prompts.system',
  intent_parser: 'prompts.intentParser',
  summarizer: 'prompts.summarizer',
  general: 'prompts.general',
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

  const load = useCallback(async () => {
    try {
      const data = await api.getPromptTemplates() as PromptTemplate[]
      setItems(data || [])
    } catch (e: unknown) {
      alert(errorMessage(e) || t('prompts.loadFailed'))
    } finally {
      setLoading(false)
    }
  }, [t])

  useEffect(() => { void Promise.resolve().then(() => load()) }, [load])

  const { searchTarget, setSearchTarget } = useContext(SearchContext)
  useEffect(() => {
    if (!searchTarget || searchTarget.tab !== 'prompts') return
    const el = document.querySelector(`[data-item-id="${searchTarget.id}"]`)
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' })
      el.classList.add('search-highlight')
    }
    const timer = setTimeout(() => setSearchTarget(null), 2000)
    return () => clearTimeout(timer)
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
      alert(t('prompts.required'))
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
    } catch (e: unknown) {
      alert(errorMessage(e) || t('prompts.saveFailed'))
    } finally {
      setSaving(false)
    }
  }

  const remove = async (item: PromptTemplate) => {
    if (!confirm(t('prompts.deleteConfirm', { name: item.name }))) return
    try {
      await api.deletePromptTemplate(item.id)
      setItems(prev => prev.filter(i => i.id !== item.id))
    } catch (e: unknown) {
      alert(errorMessage(e) || t('prompts.deleteFailed'))
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
  const categoryLabel = (category: Category) => t(CATEGORY_KEYS[category]).toUpperCase()

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <PageHeader
        eyebrow={t('prompts.eyebrow').toUpperCase()}
        title={t('prompts.title').toUpperCase()}
        description={t('prompts.description')}
        actions={
          <button onClick={openCreate} className="btn btn-primary" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <Plus size={12} /> {t('prompts.newTemplate').toUpperCase()}
          </button>
        }
      />

      {/* Filter */}
      <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
        <span style={{ fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-dim)', marginRight: 4 }}>
          {t('prompts.filter').toUpperCase()}
        </span>
        {(['all', 'system', 'intent_parser', 'summarizer', 'general'] as const).map(f => {
          const active = filter === f
          return (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className="btn btn-sm"
              style={{
                background: active ? 'var(--accent-dim)' : 'transparent',
                borderColor: active ? 'var(--accent-border)' : 'var(--border-bright)',
                color: active ? 'var(--accent)' : 'var(--text-muted)',
                height: 28,
              }}
            >
              {f === 'all' ? t('prompts.all').toUpperCase() : categoryLabel(f)}
            </button>
          )
        })}
      </div>

      {/* List */}
      {loading ? (
        <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-dim)', fontSize: 13, letterSpacing: '0.06em' }}>
          {t('prompts.loading').toUpperCase()}
        </div>
      ) : filtered.length === 0 ? (
        <div style={{
          padding: 40, textAlign: 'center', color: 'var(--text-dim)', fontSize: 13, letterSpacing: '0.06em',
          border: '1px dashed var(--border-bright)', background: 'var(--bg-surface)',
        }}>
          {t('prompts.emptyHint').toUpperCase()}
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: 12 }}>
          {filtered.map(item => (
            <div
              key={item.id}
              data-item-id={item.id}
              className="item-card"
              style={{ opacity: item.is_active ? 1 : 0.55, padding: '14px 16px', gap: 10 }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1, minWidth: 0 }}>
                  <span
                    className="item-card-badge"
                    style={{ borderColor: CATEGORY_COLORS[item.category], color: CATEGORY_COLORS[item.category] }}
                  >
                    {categoryLabel(item.category)}
                  </span>
                  <span className="item-card-title" style={{ fontSize: 14 }}>{item.name}</span>
                </div>
                <div style={{ display: 'flex', gap: 2 }}>
                  <button onClick={() => copyContent(item)} title={t('prompts.copyContent')} className="item-card-icon-btn">
                    {copiedId === item.id ? <Check size={12} style={{ color: 'var(--accent)' }} /> : <Copy size={12} />}
                  </button>
                  <button onClick={() => openEdit(item)} title={t('prompts.edit')} className="item-card-icon-btn">
                    <Edit2 size={12} />
                  </button>
                  <button onClick={() => remove(item)} title={t('prompts.delete')} className="item-card-icon-btn danger">
                    <Trash2 size={12} />
                  </button>
                </div>
              </div>

              {item.description && (
                <div className="item-card-desc">{item.description}</div>
              )}

              <div style={{
                fontSize: 12,
                color: 'var(--text-dim)',
                lineHeight: 1.45,
                background: 'var(--bg-base)',
                border: '1px solid var(--border)',
                padding: '8px 10px',
                maxHeight: 88,
                overflow: 'hidden',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                borderRadius: 'var(--radius-sm)',
              }}>
                {item.content.length > 260 ? item.content.slice(0, 260) + ' …' : item.content}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Editor modal */}
      {editorOpen && (
        <Modal
          width={720}
          title={t(edit.id == null ? 'prompts.newTitle' : 'prompts.editTitle').toUpperCase()}
          onClose={() => { if (!saving) setEditorOpen(false) }}
          footer={(
            <>
              <button onClick={() => setEditorOpen(false)} disabled={saving} className="btn btn-secondary">
                {t('prompts.cancel').toUpperCase()}
              </button>
              <button onClick={save} disabled={saving} className="btn btn-primary" style={{ opacity: saving ? 0.6 : 1 }}>
                <Save size={12} /> {t(saving ? 'prompts.saving' : 'prompts.save').toUpperCase()}
              </button>
            </>
          )}
        >
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 12 }}>
            <div>
              <label className="form-label">{t('prompts.name').toUpperCase()}</label>
              <input value={edit.name} onChange={e => setEdit(s => ({ ...s, name: e.target.value }))}
                placeholder={t('prompts.namePlaceholder')}
                className="form-input"
              />
            </div>
            <div>
              <label className="form-label">{t('prompts.category').toUpperCase()}</label>
              <select value={edit.category} onChange={e => setEdit(s => ({ ...s, category: e.target.value as Category }))} className="form-input">
                <option value="system">{t('prompts.systemPrompt')}</option>
                <option value="intent_parser">{t('prompts.intentParser')}</option>
                <option value="summarizer">{t('prompts.summarizer')}</option>
                <option value="general">{t('prompts.general')}</option>
              </select>
            </div>
          </div>
          <div>
            <label className="form-label">{t('prompts.descriptionOptional').toUpperCase()}</label>
            <input value={edit.description} onChange={e => setEdit(s => ({ ...s, description: e.target.value }))}
              placeholder={t('prompts.descriptionPlaceholder')}
              className="form-input"
            />
          </div>
          <div>
            <label className="form-label">{t('prompts.content').toUpperCase()}</label>
            <textarea value={edit.content} onChange={e => setEdit(s => ({ ...s, content: e.target.value }))}
              rows={14}
              placeholder={t('prompts.contentPlaceholder')}
              className="form-textarea"
              style={{ minHeight: 280, lineHeight: 1.6 }}
            />
          </div>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: 'var(--text-muted)', cursor: 'pointer' }}>
            <input type="checkbox" checked={edit.is_active} onChange={e => setEdit(s => ({ ...s, is_active: e.target.checked }))} />
            <span style={{ letterSpacing: '0.1em' }}>{t('prompts.activeInChat').toUpperCase()}</span>
          </label>
        </Modal>
      )}
    </div>
  )
}
