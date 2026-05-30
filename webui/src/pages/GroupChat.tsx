import { useState, useEffect, useRef } from 'react'
import { api } from '../api/client'
import { Radio, Users, Play, Square, ChevronRight, Bot, User } from 'lucide-react'

// ─── Multi-Agent Chat ─────────────────────────────────────────────────────────

interface GCAgent {
  id: number
  agent_name: string
  backend_type?: string
  endpoint_url?: string
}

interface GCMessage {
  role: string
  content: string
  agent_id?: number
  agent_name?: string
  timestamp: string
}

interface GCSession {
  session_id: string
  user_id: number
  agent_ids: number[]
  status: string
  current_round: number
  max_rounds: number
  messages: GCMessage[]
  created_at: string
}

function MultiAgentChat() {
  const [agents, setAgents] = useState<GCAgent[]>([])
  const [selectedAgentIds, setSelectedAgentIds] = useState<number[]>([])
  const [initialMessage, setInitialMessage] = useState('')
  const [maxRounds, setMaxRounds] = useState(3)
  const [session, setSession] = useState<GCSession | null>(null)
  const [running, setRunning] = useState(false)
  const [runningRound, setRunningRound] = useState(false)
  const [loadError, setLoadError] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    api.getAgents().then((data: any) => {
      const list = Array.isArray(data) ? data : data?.agents || []
      setAgents(list.filter((a: any) => (a.kind || 'external') !== 'internal'))
    }).catch(() => {})
  }, [])

  useEffect(() => { bottomRef.current?.scrollIntoView() }, [session?.messages])

  const toggleAgent = (id: number) => {
    setSelectedAgentIds(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id])
  }

  const createAndRun = async () => {
    if (!initialMessage.trim() || selectedAgentIds.length === 0) return
    setRunning(true); setLoadError('')
    try {
      const result: any = await api.createGroupChatSession({
        agent_ids: selectedAgentIds,
        initial_message: initialMessage,
        max_rounds: maxRounds,
      })
      setSession(result)
      // Auto-run first round
      await api.runGroupChatRound(result.session_id)
      refreshSession(result.session_id)
    } catch (e: any) { setLoadError(e.message) }
    finally { setRunning(false) }
  }

  const runRound = async () => {
    if (!session) return
    setRunningRound(true)
    try {
      await api.runGroupChatRound(session.session_id)
      await refreshSession(session.session_id)
    } catch (e: any) { setLoadError(e.message) }
    finally { setRunningRound(false) }
  }

  const runToComplete = async () => {
    if (!session) return
    setRunningRound(true)
    try {
      const result: any = await api.runGroupChatComplete(session.session_id)
      setSession(result)
    } catch (e: any) { setLoadError(e.message) }
    finally { setRunningRound(false) }
  }

  const cancelSession = async () => {
    if (!session) return
    await api.cancelGroupChatSession(session.session_id)
    setSession(null)
  }

  const refreshSession = async (id: string) => {
    const result: any = await api.getGroupChatSession(id)
    setSession(result)
  }

  const roleColor = (role: string) => {
    if (role === 'user') return 'var(--accent)'
    if (role === 'agent') return 'var(--cyan)'
    return 'var(--text-muted)'
  }

  return (
    <div style={{ display: 'flex', flex: 1, gap: 16, minHeight: 0 }}>
      {/* Agent selector sidebar */}
      <div style={{
        width: 220, flexShrink: 0,
        background: 'var(--bg-surface)', border: '1px solid var(--border-bright)',
        display: 'flex', flexDirection: 'column', padding: 12,
      }}>
        <div style={{ fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-dim)', marginBottom: 12, paddingBottom: 8, borderBottom: '1px solid var(--border)' }}>SELECT AGENTS</div>
        {agents.length === 0 && (
          <div style={{ fontSize: 12, color: 'var(--text-dim)', padding: '8px 0' }}>No agents configured</div>
        )}
        {agents.map(a => (
          <label key={a.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 4px', cursor: session ? 'not-allowed' : 'pointer' }}>
            <input type="checkbox" checked={selectedAgentIds.includes(a.id)} onChange={() => toggleAgent(a.id)}
              disabled={!!session} style={{ width: 14, height: 14, accentColor: 'var(--accent)' }} />
            <span style={{ fontSize: 13, color: 'var(--text-primary)', fontFamily: 'var(--font-mono)', letterSpacing: '0.03em', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {a.agent_name}
            </span>
          </label>
        ))}

        {session && (
          <div style={{ marginTop: 16, padding: '10px', background: 'var(--bg-base)', border: '1px solid var(--border)', fontSize: 12, color: 'var(--text-dim)', lineHeight: 1.8 }}>
            <div style={{ color: 'var(--text-muted)', letterSpacing: '0.1em', marginBottom: 4 }}>SESSION</div>
            <div style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>Round {session.current_round}/{session.max_rounds}</div>
            <div style={{ color: session.status === 'active' ? 'var(--green)' : 'var(--text-dim)' }}>{session.status.toUpperCase()}</div>
          </div>
        )}
      </div>

      {/* Chat area */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: 'var(--bg-surface)', border: '1px solid var(--border-bright)', minHeight: 0 }}>
        {/* Chat header */}
        <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '0.1em' }}>MULTI-AGENT DISCUSSION</span>
          {session && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 12, color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>
                ROUND {session.current_round}/{session.max_rounds}
              </span>
              <span style={{ fontSize: 12, padding: '2px 8px', border: '1px solid var(--green)', color: 'var(--green)' }}>
                {session.status.toUpperCase()}
              </span>
            </div>
          )}
        </div>

        {/* Messages */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '16px', display: 'flex', flexDirection: 'column', gap: 12 }}>
          {!session && (
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 10 }}>
              <Users size={28} style={{ color: 'var(--text-dim)' }} />
              <div style={{ fontSize: 13, color: 'var(--text-dim)', letterSpacing: '0.1em', textAlign: 'center', lineHeight: 1.8 }}>
                Select agents → Write a prompt → Launch discussion
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-dim)', maxWidth: 300, textAlign: 'center', lineHeight: 1.6 }}>
                Each agent will respond in sequence. Results are streamed back as agents reply.
              </div>
            </div>
          )}

          {session?.messages.map((m, i) => (
            <div key={i} style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 4 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '0 4px' }}>
                {m.role === 'agent' ? (
                  <Bot size={10} style={{ color: 'var(--cyan)' }} />
                ) : (
                  <User size={10} style={{ color: 'var(--accent)' }} />
                )}
                <span style={{ fontSize: 11, color: roleColor(m.role), letterSpacing: '0.1em', fontWeight: 600 }}>
                  {m.role === 'agent' ? (m.agent_name || `AGENT-${m.agent_id}`).toUpperCase() : 'USER'}
                </span>
                <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>
                  {new Date(m.timestamp).toLocaleTimeString()}
                </span>
              </div>
              <div style={{
                maxWidth: '80%', padding: '10px 14px',
                background: m.role === 'user' ? 'var(--accent-dim)' : 'var(--bg-elevated)',
                border: `1px solid ${m.role === 'user' ? 'var(--accent-border)' : 'var(--border-bright)'}`,
                borderLeft: `2px solid ${roleColor(m.role)}`,
                fontSize: 14, color: 'var(--text-primary)', letterSpacing: '0.02em', lineHeight: 1.6,
                whiteSpace: 'pre-wrap',
              }}>
                {m.content}
              </div>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>

        {/* Input / Controls */}
        <div style={{ padding: '12px 16px', borderTop: '1px solid var(--border)', display: 'flex', flexDirection: 'column', gap: 10 }}>
          {!session ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <textarea
                value={initialMessage}
                onChange={e => setInitialMessage(e.target.value)}
                placeholder="Initial prompt for the group discussion..."
                rows={3}
                style={{ width: '100%', padding: '8px 12px', background: 'var(--bg-base)', border: '1px solid var(--border-bright)', color: 'var(--text-primary)', fontSize: 13, letterSpacing: '0.05em', fontFamily: 'var(--font-mono)', resize: 'none' }}
              />
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontSize: 11, color: 'var(--text-dim)', letterSpacing: '0.1em' }}>MAX ROUNDS</span>
                  <input type="number" value={maxRounds} onChange={e => setMaxRounds(Number(e.target.value))} min={1} max={20}
                    style={{ width: 50, height: 28, padding: '0 8px', background: 'var(--bg-base)', border: '1px solid var(--border-bright)', color: 'var(--text-primary)', fontSize: 13, fontFamily: 'var(--font-mono)', textAlign: 'center' }} />
                </div>
                <button onClick={createAndRun} disabled={running || selectedAgentIds.length === 0 || !initialMessage.trim()}
                  style={{ height: 34, padding: '0 18px', background: running ? 'var(--bg-elevated)' : 'var(--accent)', border: '1px solid var(--accent-border)', color: '#000', fontWeight: 700, fontSize: 13, letterSpacing: '0.06em', cursor: running ? 'not-allowed' : 'pointer', fontFamily: 'var(--font-mono)', display: 'flex', alignItems: 'center', gap: 6 }}>
                  {running ? 'STARTING...' : <><Play size={11} /> START DISCUSSION</>}
                </button>
              </div>
            </div>
          ) : (
            <div style={{ display: 'flex', gap: 8 }}>
              {session.status === 'active' && (
                <>
                  <button onClick={runRound} disabled={runningRound}
                    style={{ flex: 1, height: 36, border: '1px solid var(--accent-border)', background: runningRound ? 'var(--bg-elevated)' : 'var(--accent)', color: '#000', fontWeight: 700, fontSize: 13, letterSpacing: '0.1em', cursor: runningRound ? 'not-allowed' : 'pointer', fontFamily: 'var(--font-mono)', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
                    {runningRound ? 'RUNNING...' : <><ChevronRight size={11} /> NEXT ROUND</>}
                  </button>
                  <button onClick={runToComplete} disabled={runningRound}
                    style={{ height: 36, padding: '0 16px', border: '1px solid var(--border-bright)', background: 'transparent', color: 'var(--text-muted)', fontSize: 13, letterSpacing: '0.1em', cursor: runningRound ? 'not-allowed' : 'pointer', fontFamily: 'var(--font-mono)', display: 'flex', alignItems: 'center', gap: 6 }}>
                    AUTO
                  </button>
                </>
              )}
              <button onClick={cancelSession}
                style={{ height: 36, padding: '0 14px', border: '1px solid var(--red)', background: 'transparent', color: 'var(--red)', fontSize: 13, letterSpacing: '0.1em', cursor: 'pointer', fontFamily: 'var(--font-mono)', display: 'flex', alignItems: 'center', gap: 6 }}>
                <Square size={11} /> END
              </button>
            </div>
          )}
          {loadError && (
            <div style={{ padding: '6px 10px', background: 'rgba(255,0,0,0.1)', border: '1px solid var(--red)', fontSize: 12, color: 'var(--red)', fontFamily: 'var(--font-mono)' }}>
              {loadError}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function GroupChat() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - var(--header-height) - 48px)' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16, paddingBottom: 16, borderBottom: '1px solid var(--border)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ width: 36, height: 36, border: '1px solid var(--border-bright)', background: 'var(--bg-surface)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--cyan)' }}>
            <Radio size={15} />
          </div>
          <div>
            <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '0.1em' }}>GROUP CHAT</div>
            <div style={{ fontSize: 11, color: 'var(--text-dim)', letterSpacing: '0.1em' }}>MULTI-AGENT PANEL DISCUSSION</div>
          </div>
        </div>
      </div>

      <MultiAgentChat />
    </div>
  )
}
