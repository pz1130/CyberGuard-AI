import { useState, useEffect, useRef } from 'react'
import { wsBase } from '../api/client'

export default function GroupChat() {
  const [rooms, setRooms] = useState<string[]>(['general', 'agents', 'alerts'])
  const [activeRoom, setActiveRoom] = useState('general')
  const [messages, setMessages] = useState<{ role: string; user: string; content: string }[]>([])
  const [input, setInput] = useState('')
  const [connected, setConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  const connect = (room: string) => {
    if (wsRef.current) wsRef.current.close()
    const ws = new WebSocket(`${wsBase}/groupchat/${room}`)
    ws.onopen = () => setConnected(true)
    ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data)
        setMessages(m => [...m, { role: 'other', user: data.user || '匿名', content: data.content || data.message || JSON.stringify(data) }])
      } catch {
        setMessages(m => [...m, { role: 'other', user: '系统', content: e.data }])
      }
    }
    ws.onclose = () => setConnected(false)
    wsRef.current = ws
  }

  useEffect(() => {
    connect(activeRoom)
    return () => wsRef.current?.close()
  }, [activeRoom])

  useEffect(() => { bottomRef.current?.scrollIntoView() }, [messages])

  const send = () => {
    if (!input.trim() || !wsRef.current) return
    wsRef.current.send(JSON.stringify({ content: input, user: '我' }))
    setMessages(m => [...m, { role: 'self', user: '我', content: input }])
    setInput('')
  }

  const addRoom = () => {
    const name = prompt('房间名称:')
    if (name && !rooms.includes(name)) setRooms(r => [...r, name])
  }

  return (
    <div className="flex h-full gap-4">
      {/* Room list */}
      <div className="w-48 flex-shrink-0 bg-slate-900 rounded-xl p-3 flex flex-col gap-1">
        <h3 className="text-xs font-semibold text-slate-400 uppercase mb-2 px-2">房间</h3>
        {rooms.map(r => (
          <button key={r} onClick={() => setActiveRoom(r)}
            className={`text-left px-3 py-2 rounded-lg text-sm ${activeRoom === r ? 'bg-violet-500/20 text-violet-400' : 'text-slate-400 hover:bg-slate-800'}`}>
            # {r}
          </button>
        ))}
        <button onClick={addRoom} className="mt-2 text-xs text-slate-500 hover:text-white px-3 py-1">+ 新增房间</button>
      </div>

      {/* Chat */}
      <div className="flex-1 flex flex-col bg-slate-900 rounded-xl overflow-hidden">
        {/* Header */}
        <div className="px-4 py-3 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-white font-medium">#{activeRoom}</span>
            <span className={`text-xs px-2 py-0.5 rounded ${connected ? 'bg-violet-500/20 text-violet-400' : 'bg-red-500/20 text-red-400'}`}>
              {connected ? '已连接' : '未连接'}
            </span>
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {messages.length === 0 && <p className="text-slate-500 text-sm text-center mt-10">开始聊天...</p>}
          {messages.map((m, i) => (
            <div key={i} className={`flex ${m.role === 'self' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-md rounded-2xl px-4 py-2 text-sm ${m.role === 'self' ? 'bg-violet-500 text-white' : 'bg-slate-800 text-slate-100'}`}>
                <span className="text-xs opacity-60 block">{m.user}</span>
                {m.content}
              </div>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div className="p-3 border-t border-slate-800 flex gap-2">
          <input value={input} onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && send()}
            className="flex-1 bg-slate-800 rounded-xl px-4 py-2 text-sm text-white" placeholder="输入消息..." />
          <button onClick={send} className="px-5 py-2 bg-violet-500 hover:bg-violet-600 text-white rounded-xl text-sm">发送</button>
        </div>
      </div>
    </div>
  )
}
