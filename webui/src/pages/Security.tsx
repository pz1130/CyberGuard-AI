import { useState } from 'react'
import { Shield, Key, Lock, AlertTriangle } from 'lucide-react'

export default function Security() {
  const [settings, setSettings] = useState({
    encryption_enabled: true,
    audit_logging: true,
    rbac_enabled: true,
    api_key_rotation_days: 90,
    max_login_attempts: 5,
    session_timeout_minutes: 30,
    require_mfa: false,
  })

  const update = (key: string, value: any) => setSettings(s => ({ ...s, [key]: value }))

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold flex items-center gap-2"><Shield size={20} /> 安全设置</h2>
          <p className="text-xs text-slate-500 mt-1">管理加密、审计、访问控制等安全策略</p>
        </div>
      </div>

      <div className="space-y-6">
        {/* Encryption */}
        <div className="bg-slate-900 rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <Key size={18} className="text-violet-400" />
              <div>
                <h3 className="font-medium text-white">AES-256 加密</h3>
                <p className="text-xs text-slate-400">对敏感数据进行静态加密</p>
              </div>
            </div>
            <button onClick={() => update('encryption_enabled', !settings.encryption_enabled)}
              className={`w-12 h-6 rounded-full transition-colors ${settings.encryption_enabled ? 'bg-violet-500' : 'bg-slate-600'}`}>
              <div className={`w-5 h-5 bg-white rounded-full shadow transition-transform ${settings.encryption_enabled ? 'translate-x-6' : 'translate-x-0.5'}`} />
            </button>
          </div>
        </div>

        {/* RBAC */}
        <div className="bg-slate-900 rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <Lock size={18} className="text-blue-400" />
              <div>
                <h3 className="font-medium text-white">RBAC 访问控制</h3>
                <p className="text-xs text-slate-400">基于角色的权限管理</p>
              </div>
            </div>
            <button onClick={() => update('rbac_enabled', !settings.rbac_enabled)}
              className={`w-12 h-6 rounded-full transition-colors ${settings.rbac_enabled ? 'bg-violet-500' : 'bg-slate-600'}`}>
              <div className={`w-5 h-5 bg-white rounded-full shadow transition-transform ${settings.rbac_enabled ? 'translate-x-6' : 'translate-x-0.5'}`} />
            </button>
          </div>
        </div>

        {/* Audit Logging */}
        <div className="bg-slate-900 rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <AlertTriangle size={18} className="text-yellow-400" />
              <div>
                <h3 className="font-medium text-white">审计日志</h3>
                <p className="text-xs text-slate-400">记录所有操作行为，支持 SIEM 导出</p>
              </div>
            </div>
            <button onClick={() => update('audit_logging', !settings.audit_logging)}
              className={`w-12 h-6 rounded-full transition-colors ${settings.audit_logging ? 'bg-violet-500' : 'bg-slate-600'}`}>
              <div className={`w-5 h-5 bg-white rounded-full shadow transition-transform ${settings.audit_logging ? 'translate-x-6' : 'translate-x-0.5'}`} />
            </button>
          </div>
        </div>

        {/* Numeric settings */}
        <div className="bg-slate-900 rounded-xl p-5 space-y-4">
          <h3 className="font-medium text-white">阈值配置</h3>
          {[
            { key: 'max_login_attempts', label: '最大登录尝试次数', min: 3, max: 20 },
            { key: 'session_timeout_minutes', label: '会话超时（分钟）', min: 5, max: 480 },
            { key: 'api_key_rotation_days', label: 'API Key 轮换周期（天）', min: 7, max: 365 },
          ].map(({ key, label, min, max }) => (
            <div key={key} className="flex items-center justify-between">
              <span className="text-sm text-slate-300">{label}</span>
              <input type="number" min={min} max={max}
                value={(settings as any)[key]}
                onChange={e => update(key, parseInt(e.target.value))}
                className="w-24 bg-slate-800 rounded-lg px-3 py-1.5 text-sm text-white text-right" />
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
