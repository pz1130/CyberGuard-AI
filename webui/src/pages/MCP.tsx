import { useState, useEffect } from 'react'
import { api } from '../api/client'
import {
  Trash2, Plus, Play, Square, Edit2, Loader2, Plug, Wrench,
  ChevronDown, ChevronRight, X, Server, Activity, RefreshCw,
} from 'lucide-react'

interface MCPServer {
  id?: number
  name: string
  transport_type: string
  command?: string
  args?: string[]
  url?: string
  description?: string
  is_active?: boolean
  timeout_seconds?: number
}

interface MCPTool {
  id?: number
  server_id: number
  tool_name: string
  description?: string
  category?: string
  is_active?: boolean
  use_count?: number
}

interface ServerForm {
  name: string
  transport_type: string
  command: string
  args_text: string
  url: string
  description: string
  timeout: number
  is_active: boolean
}

interface ToolForm {
  server_id: number
  tool_name: string
  description: string
  category: string
}

const TRANSPORT_TYPES = [
  { value: 'stdio', label: 'STDIO', hint: '本地子进程' },
  { value: 'sse', label: 'SSE', hint: 'Server-Sent Events' },
  { value: 'streamable_http', label: 'HTTP', hint: 'Streamable HTTP' },
]

const TOOL_CATEGORIES = [
  { value: 'threat', label: '威胁情报', tone: 'rose' },
  { value: 'log', label: '日志分析', tone: 'amber' },
  { value: 'vuln', label: '漏洞扫描', tone: 'orange' },
  { value: 'recon', label: '侦察 / OSINT', tone: 'cyan' },
  { value: 'general', label: '通用', tone: 'slate' },
] as const

const CATEGORY_TONES: Record<string, string> = {
  rose: 'bg-rose-500/15 text-rose-300 ring-rose-500/30',
  amber: 'bg-amber-500/15 text-amber-300 ring-amber-500/30',
  orange: 'bg-orange-500/15 text-orange-300 ring-orange-500/30',
  cyan: 'bg-cyan-500/15 text-cyan-300 ring-cyan-500/30',
  slate: 'bg-slate-700/40 text-slate-300 ring-slate-600/40',
}

const emptyServerForm: ServerForm = {
  name: '', transport_type: 'stdio', command: '', args_text: '', url: '',
  description: '', timeout: 30, is_active: true,
}
const emptyToolForm: ToolForm = { server_id: 0, tool_name: '', description: '', category: 'general' }

export default function MCP() {
  const [servers, setServers] = useState<MCPServer[]>([])
  const [tools, setTools] = useState<MCPTool[]>([])
  const [tab, setTab] = useState<'servers' | 'tools'>('servers')
  const [serverTools, setServerTools] = useState<Record<number, MCPTool[]>>({})
  const [expandedServer, setExpandedServer] = useState<number | null>(null)

  const [showServerForm, setShowServerForm] = useState(false)
  const [showToolForm, setShowToolForm] = useState(false)
  const [editingServer, setEditingServer] = useState<MCPServer | null>(null)
  const [editingTool, setEditingTool] = useState<MCPTool | null>(null)
  const [serverForm, setServerForm] = useState<ServerForm>(emptyServerForm)
  const [toolForm, setToolForm] = useState<ToolForm>(emptyToolForm)
  const [busy, setBusy] = useState<{ kind: 'start' | 'stop' | 'discover'; id: number } | null>(null)

  // ---- Loaders ----
  const loadServers = async () => {
    try {
      const data = await api.getMCPServers() as { servers: MCPServer[] }
      setServers(data?.servers || [])
    } catch { setServers([]) }
  }

  const loadTools = async (currentServers: MCPServer[]) => {
    const all: MCPTool[] = []
    const map: Record<number, MCPTool[]> = {}
    for (const s of currentServers) {
      if (!s.id) continue
      try {
        const data = await api.getMCPServerTools(s.id) as { tools: MCPTool[] }
        if (data?.tools) {
          all.push(...data.tools)
          map[s.id] = data.tools
        }
      } catch { /* ignore */ }
    }
    setTools(all)
    setServerTools(map)
  }

  useEffect(() => { loadServers() }, [])
  useEffect(() => { if (servers.length) loadTools(servers) }, [servers.length])

  // ---- Server CRUD ----
  const submitServer = async () => {
    if (!serverForm.name) return
    const args = serverForm.args_text.trim()
      ? serverForm.args_text.split('\n').map(s => s.trim()).filter(Boolean)
      : undefined
    const payload = {
      name: serverForm.name,
      transport_type: serverForm.transport_type,
      command: serverForm.command || undefined,
      args,
      url: serverForm.url || undefined,
      description: serverForm.description || undefined,
      timeout: serverForm.timeout,
      is_active: serverForm.is_active,
    }
    try {
      if (editingServer?.id) await api.updateMCPServer(editingServer.id, payload)
      else await api.createMCPServer(payload)
      setShowServerForm(false); setEditingServer(null); setServerForm(emptyServerForm)
      loadServers()
    } catch (e: any) { alert(e.message) }
  }

  const submitTool = async () => {
    if (!toolForm.tool_name || !toolForm.server_id) return
    try {
      if (editingTool?.id) await api.updateMCPTool(editingTool.id, toolForm)
      else await api.createMCPTool(toolForm)
      setShowToolForm(false); setEditingTool(null); setToolForm(emptyToolForm)
      loadServers()
    } catch (e: any) { alert(e.message) }
  }

  const delServer = async (id: number) => {
    if (!confirm('删除此 MCP 服务器？')) return
    try { await api.deleteMCPServer(id); loadServers() } catch (e: any) { alert(e.message) }
  }

  const delTool = async (id: number) => {
    if (!confirm('删除此工具？')) return
    try { await api.deleteMCPTool(id); loadServers() } catch (e: any) { alert(e.message) }
  }

  const startServer = async (id: number) => {
    setBusy({ kind: 'start', id })
    try { await api.startMCPServer(id); loadServers() } catch (e: any) { alert(e.message) }
    finally { setBusy(null) }
  }

  const stopServer = async (id: number) => {
    setBusy({ kind: 'stop', id })
    try { await api.stopMCPServer(id); loadServers() } catch (e: any) { alert(e.message) }
    finally { setBusy(null) }
  }

  const discoverTools = async (id: number) => {
    setBusy({ kind: 'discover', id })
    try {
      const res = await fetch(`/api/v1/mcp/servers/${id}/tools?refresh=true`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` },
      })
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      setServerTools(prev => ({ ...prev, [id]: data.tools || [] }))
      loadTools(servers)
    } catch (e: any) { alert(`发现工具失败: ${e.message}`) }
    finally { setBusy(null) }
  }

  const openEditServer = (s: MCPServer) => {
    setEditingServer(s)
    setServerForm({
      name: s.name,
      transport_type: s.transport_type,
      command: s.command || '',
      args_text: (s.args || []).join('\n'),
      url: s.url || '',
      description: s.description || '',
      timeout: s.timeout_seconds || 30,
      is_active: s.is_active ?? true,
    })
    setShowServerForm(true)
  }

  const openEditTool = (t: MCPTool) => {
    setEditingTool(t)
    setToolForm({
      server_id: t.server_id,
      tool_name: t.tool_name,
      description: t.description || '',
      category: t.category || 'general',
    })
    setShowToolForm(true)
  }

  const toggleExpand = (id: number) => setExpandedServer(expandedServer === id ? null : id)

  return (
    <div className="max-w-6xl mx-auto">
      {/* Page header */}
      <div className="mb-8">
        <div className="flex items-end justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-slate-100 tracking-tight">MCP</h1>
            <p className="text-sm text-slate-400 mt-1">
              管理 Model Context Protocol 服务器与工具，扩展 Agent 能力。
            </p>
          </div>
          {tab === 'servers' ? (
            <button
              onClick={() => { setEditingServer(null); setServerForm(emptyServerForm); setShowServerForm(true) }}
              className="flex items-center gap-1.5 px-3.5 py-2 bg-violet-500 hover:bg-violet-400 active:bg-violet-600 text-white rounded-lg text-sm font-medium shadow-lg shadow-violet-500/20 transition-colors"
            >
              <Plus size={15} /> 新增服务器
            </button>
          ) : (
            <button
              onClick={() => { setEditingTool(null); setToolForm({ ...emptyToolForm, server_id: servers[0]?.id || 0 }); setShowToolForm(true) }}
              disabled={!servers.length}
              className="flex items-center gap-1.5 px-3.5 py-2 bg-violet-500 hover:bg-violet-400 active:bg-violet-600 disabled:opacity-40 text-white rounded-lg text-sm font-medium shadow-lg shadow-violet-500/20 transition-colors"
            >
              <Plus size={15} /> 新增工具
            </button>
          )}
        </div>

        {/* Segmented tabs */}
        <div className="mt-5 inline-flex p-1 bg-slate-900/60 ring-1 ring-slate-800/80 rounded-xl">
          <SegBtn active={tab === 'servers'} onClick={() => setTab('servers')} icon={<Server size={14} />}>
            服务器 <span className="ml-1.5 text-[11px] text-slate-500">{servers.length}</span>
          </SegBtn>
          <SegBtn active={tab === 'tools'} onClick={() => setTab('tools')} icon={<Wrench size={14} />}>
            工具 <span className="ml-1.5 text-[11px] text-slate-500">{tools.length}</span>
          </SegBtn>
        </div>
      </div>

      {/* Server Form */}
      {showServerForm && tab === 'servers' && (
        <FormCard
          title={editingServer ? '编辑服务器' : '新增 MCP 服务器'}
          onClose={() => { setShowServerForm(false); setEditingServer(null) }}
          onSubmit={submitServer}
          submitLabel={editingServer ? '保存' : '创建'}
        >
          <div className="grid grid-cols-2 gap-4">
            <Field label="名称" required>
              <input value={serverForm.name} disabled={!!editingServer}
                onChange={e => setServerForm(f => ({ ...f, name: e.target.value }))}
                className={inputCls + ' disabled:opacity-50'} placeholder="my-mcp-server" />
            </Field>
            <Field label="传输类型">
              <select value={serverForm.transport_type}
                onChange={e => setServerForm(f => ({ ...f, transport_type: e.target.value }))}
                className={inputCls}>
                {TRANSPORT_TYPES.map(t => (
                  <option key={t.value} value={t.value}>{t.label} — {t.hint}</option>
                ))}
              </select>
            </Field>

            {serverForm.transport_type === 'stdio' ? (
              <>
                <Field label="可执行命令">
                  <input value={serverForm.command}
                    onChange={e => setServerForm(f => ({ ...f, command: e.target.value }))}
                    className={inputCls + ' font-mono'} placeholder="npx" />
                </Field>
                <Field label="超时（秒）">
                  <input type="number" value={serverForm.timeout}
                    onChange={e => setServerForm(f => ({ ...f, timeout: parseInt(e.target.value) || 30 }))}
                    className={inputCls} />
                </Field>
                <Field label="命令行参数（每行一个）" full>
                  <textarea value={serverForm.args_text}
                    onChange={e => setServerForm(f => ({ ...f, args_text: e.target.value }))}
                    rows={3}
                    className={inputCls + ' font-mono'}
                    placeholder={'@modelcontextprotocol/server-filesystem\n/path/to/dir'} />
                </Field>
              </>
            ) : (
              <Field label="HTTP Endpoint URL" full>
                <input value={serverForm.url}
                  onChange={e => setServerForm(f => ({ ...f, url: e.target.value }))}
                  className={inputCls + ' font-mono'}
                  placeholder="https://mcp.example.com" />
              </Field>
            )}

            <Field label="描述" full>
              <input value={serverForm.description}
                onChange={e => setServerForm(f => ({ ...f, description: e.target.value }))}
                className={inputCls} />
            </Field>

            <label className="flex items-center gap-2 col-span-2 text-sm text-slate-300 select-none cursor-pointer">
              <input type="checkbox" checked={serverForm.is_active}
                onChange={e => setServerForm(f => ({ ...f, is_active: e.target.checked }))}
                className="accent-violet-500 w-4 h-4" />
              启用此服务器
            </label>
          </div>
        </FormCard>
      )}

      {/* Tool Form */}
      {showToolForm && tab === 'tools' && (
        <FormCard
          title={editingTool ? '编辑工具' : '新增 MCP 工具'}
          onClose={() => { setShowToolForm(false); setEditingTool(null) }}
          onSubmit={submitTool}
          submitLabel={editingTool ? '保存' : '创建'}
        >
          <div className="grid grid-cols-2 gap-4">
            <Field label="所属服务器" required>
              <select value={toolForm.server_id}
                onChange={e => setToolForm(f => ({ ...f, server_id: Number(e.target.value) }))}
                className={inputCls}>
                <option value={0}>选择服务器…</option>
                {servers.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </Field>
            <Field label="工具名称" required>
              <input value={toolForm.tool_name}
                onChange={e => setToolForm(f => ({ ...f, tool_name: e.target.value }))}
                className={inputCls + ' font-mono'} placeholder="lookup_ioc" />
            </Field>
            <Field label="分类">
              <select value={toolForm.category}
                onChange={e => setToolForm(f => ({ ...f, category: e.target.value }))}
                className={inputCls}>
                {TOOL_CATEGORIES.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
              </select>
            </Field>
            <Field label="描述" full>
              <input value={toolForm.description}
                onChange={e => setToolForm(f => ({ ...f, description: e.target.value }))}
                className={inputCls} />
            </Field>
          </div>
        </FormCard>
      )}

      {/* Servers tab content */}
      {tab === 'servers' && (
        servers.length === 0 ? (
          <EmptyState
            icon={<Plug size={28} />}
            title="还没有 MCP 服务器"
            hint="MCP 服务器用于扩展 Agent 工具能力。点击右上角添加一个开始。"
          />
        ) : (
          <div className="space-y-3">
            {servers.map(s => {
              const sTools = (s.id && serverTools[s.id]) || []
              const expanded = expandedServer === s.id
              return (
                <div key={s.id} className="bg-slate-900/60 ring-1 ring-slate-800/80 rounded-xl overflow-hidden hover:ring-slate-700/80 transition-colors">
                  <div className="px-4 py-3 flex items-center gap-3">
                    <button
                      onClick={() => s.id && toggleExpand(s.id)}
                      className="text-slate-500 hover:text-slate-300 transition-colors"
                    >
                      {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                    </button>

                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-medium text-slate-100">{s.name}</span>
                        <Badge tone="indigo">{s.transport_type}</Badge>
                        <Badge tone={s.is_active ? 'emerald' : 'slate'}>
                          <span className={`h-1.5 w-1.5 rounded-full ${s.is_active ? 'bg-violet-400' : 'bg-slate-500'} mr-1.5`} />
                          {s.is_active ? '启用' : '禁用'}
                        </Badge>
                        <span className="text-[11px] text-slate-500">{sTools.length} 个工具</span>
                      </div>
                      {(s.command || s.url) && (
                        <p className="text-xs text-slate-500 font-mono mt-1 truncate">
                          {s.command ? `${s.command} ${(s.args || []).join(' ')}` : s.url}
                        </p>
                      )}
                      {s.description && <p className="text-xs text-slate-400 mt-0.5">{s.description}</p>}
                    </div>

                    <div className="flex items-center gap-0.5">
                      {s.transport_type === 'stdio' && s.is_active && (
                        <>
                          <IconBtn onClick={() => s.id && startServer(s.id)} title="启动" tone="emerald"
                            loading={busy?.kind === 'start' && busy.id === s.id}>
                            <Play size={14} />
                          </IconBtn>
                          <IconBtn onClick={() => s.id && stopServer(s.id)} title="停止" tone="amber"
                            loading={busy?.kind === 'stop' && busy.id === s.id}>
                            <Square size={14} />
                          </IconBtn>
                        </>
                      )}
                      <IconBtn onClick={() => s.id && discoverTools(s.id)} title="发现工具"
                        loading={busy?.kind === 'discover' && busy.id === s.id}>
                        <RefreshCw size={14} />
                      </IconBtn>
                      <IconBtn onClick={() => openEditServer(s)} title="编辑">
                        <Edit2 size={14} />
                      </IconBtn>
                      <IconBtn onClick={() => s.id && delServer(s.id)} title="删除" tone="rose">
                        <Trash2 size={14} />
                      </IconBtn>
                    </div>
                  </div>

                  {expanded && (
                    <div className="border-t border-slate-800/80 bg-slate-950/40 px-4 py-3">
                      <div className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold mb-2">
                        工具
                      </div>
                      {sTools.length === 0 ? (
                        <p className="text-xs text-slate-500 py-2">暂无工具。点击 ↻ 从服务器自动发现。</p>
                      ) : (
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                          {sTools.map(t => (
                            <ToolRow key={t.id} tool={t} onEdit={() => openEditTool(t)} onDelete={() => t.id && delTool(t.id)} />
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )
      )}

      {/* Tools tab content */}
      {tab === 'tools' && (
        tools.length === 0 ? (
          <EmptyState
            icon={<Wrench size={28} />}
            title="还没有 MCP 工具"
            hint="先在「服务器」tab 注册并启动一个 server，然后点击 ↻ 自动发现工具。"
          />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {tools.map(t => (
              <ToolCard
                key={t.id}
                tool={t}
                serverName={servers.find(s => s.id === t.server_id)?.name || `Server #${t.server_id}`}
                onEdit={() => openEditTool(t)}
                onDelete={() => t.id && delTool(t.id)}
              />
            ))}
          </div>
        )
      )}
    </div>
  )
}

// =====================================================================
// Sub-components
// =====================================================================
const inputCls =
  'w-full bg-slate-950/80 ring-1 ring-slate-800 focus:ring-violet-500/60 focus:bg-slate-950 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder:text-slate-600 outline-none transition-shadow'

function SegBtn({ active, onClick, icon, children }: {
  active: boolean; onClick: () => void; icon: React.ReactNode; children: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      className={[
        'flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-sm font-medium transition-all',
        active
          ? 'bg-slate-800 text-slate-100 shadow-sm'
          : 'text-slate-400 hover:text-slate-200',
      ].join(' ')}
    >
      {icon}
      {children}
    </button>
  )
}

function Field({ label, required, full, children }: {
  label: string; required?: boolean; full?: boolean; children: React.ReactNode
}) {
  return (
    <div className={full ? 'col-span-2' : ''}>
      <label className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold mb-1.5 block">
        {label} {required && <span className="text-rose-400">*</span>}
      </label>
      {children}
    </div>
  )
}

function FormCard({ title, onClose, onSubmit, submitLabel, children }: {
  title: string; onClose: () => void; onSubmit: () => void; submitLabel: string; children: React.ReactNode
}) {
  return (
    <div className="bg-slate-900/70 ring-1 ring-slate-800 rounded-xl p-5 mb-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-slate-100">{title}</h3>
        <button onClick={onClose} className="text-slate-500 hover:text-slate-300"><X size={16} /></button>
      </div>
      {children}
      <div className="flex gap-2 justify-end mt-5">
        <button onClick={onClose} className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg text-sm transition-colors">
          取消
        </button>
        <button onClick={onSubmit} className="px-4 py-2 bg-violet-500 hover:bg-violet-400 text-white rounded-lg text-sm font-medium shadow-lg shadow-violet-500/20 transition-colors">
          {submitLabel}
        </button>
      </div>
    </div>
  )
}

function Badge({ tone = 'slate', children }: { tone?: 'slate' | 'indigo' | 'emerald'; children: React.ReactNode }) {
  const tones = {
    slate: 'bg-slate-700/40 text-slate-400 ring-slate-600/40',
    indigo: 'bg-indigo-500/15 text-indigo-300 ring-indigo-500/30',
    emerald: 'bg-violet-500/15 text-violet-300 ring-violet-500/30',
  }
  return (
    <span className={`inline-flex items-center text-[11px] px-2 py-0.5 rounded-md ring-1 ${tones[tone]}`}>
      {children}
    </span>
  )
}

function IconBtn({ onClick, title, tone, loading, children }: {
  onClick: () => void; title: string; tone?: 'emerald' | 'amber' | 'rose'; loading?: boolean; children: React.ReactNode
}) {
  const tones: Record<string, string> = {
    emerald: 'text-slate-400 hover:bg-violet-500/10 hover:text-violet-300',
    amber:   'text-slate-400 hover:bg-amber-500/10 hover:text-amber-300',
    rose:    'text-slate-400 hover:bg-rose-500/10 hover:text-rose-400',
  }
  const cls = tone ? tones[tone] : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
  return (
    <button onClick={onClick} title={title} disabled={loading}
      className={`p-2 rounded-lg transition-colors ${cls} disabled:opacity-50`}>
      {loading ? <Loader2 size={14} className="animate-spin" /> : children}
    </button>
  )
}

function ToolRow({ tool, onEdit, onDelete }: { tool: MCPTool; onEdit: () => void; onDelete: () => void }) {
  const cat = TOOL_CATEGORIES.find(c => c.value === tool.category)
  const tone = CATEGORY_TONES[cat?.tone || 'slate']
  return (
    <div className="bg-slate-900/60 ring-1 ring-slate-800 rounded-lg px-3 py-2 flex items-center gap-2">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-mono text-sm text-slate-100">{tool.tool_name}</span>
          <span className={`text-[10px] px-1.5 py-0.5 rounded ring-1 ${tone}`}>{cat?.label || tool.category}</span>
        </div>
        {tool.description && <p className="text-xs text-slate-500 truncate mt-0.5">{tool.description}</p>}
      </div>
      <button onClick={onEdit} className="p-1 text-slate-500 hover:text-slate-200"><Edit2 size={12} /></button>
      <button onClick={onDelete} className="p-1 text-slate-500 hover:text-rose-400"><Trash2 size={12} /></button>
    </div>
  )
}

function ToolCard({ tool, serverName, onEdit, onDelete }: {
  tool: MCPTool; serverName: string; onEdit: () => void; onDelete: () => void
}) {
  const cat = TOOL_CATEGORIES.find(c => c.value === tool.category)
  const tone = CATEGORY_TONES[cat?.tone || 'slate']
  return (
    <div className="bg-slate-900/60 ring-1 ring-slate-800 hover:ring-slate-700 rounded-xl p-4 transition-colors">
      <div className="flex items-start justify-between mb-3">
        <div className="min-w-0">
          <div className="font-mono text-sm text-slate-100 truncate">{tool.tool_name}</div>
          <div className="text-[11px] text-slate-500 mt-0.5">{serverName}</div>
        </div>
        <div className="flex gap-0.5">
          <IconBtn onClick={onEdit} title="编辑"><Edit2 size={13} /></IconBtn>
          <IconBtn onClick={onDelete} title="删除" tone="rose"><Trash2 size={13} /></IconBtn>
        </div>
      </div>
      {tool.description && <p className="text-xs text-slate-400 line-clamp-2 mb-3">{tool.description}</p>}
      <div className="flex items-center justify-between gap-2 text-[11px]">
        <span className={`inline-flex items-center px-1.5 py-0.5 rounded ring-1 ${tone}`}>
          {cat?.label || tool.category}
        </span>
        <span className="text-slate-500 inline-flex items-center gap-1">
          <Activity size={11} /> {tool.use_count ?? 0} 次调用
        </span>
      </div>
    </div>
  )
}

function EmptyState({ icon, title, hint }: { icon: React.ReactNode; title: string; hint: string }) {
  return (
    <div className="text-center py-20 bg-slate-900/40 ring-1 ring-slate-800/60 rounded-xl">
      <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-slate-800/60 text-slate-400 mb-4">
        {icon}
      </div>
      <h3 className="text-slate-200 font-medium">{title}</h3>
      <p className="text-sm text-slate-500 mt-1.5 max-w-md mx-auto">{hint}</p>
    </div>
  )
}
