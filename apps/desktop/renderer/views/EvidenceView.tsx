import { useCallback, useEffect, useState } from "react";
import type { EvidenceItem, EvidenceVerifyResult } from "../lib/types";

type Props = {
  evidenceHint: string;
  highlightId?: string;
  onBackToWorkbench: () => void;
  onCountChange?: (count: number) => void;
};

function fmtSize(n: number): string {
  if (!Number.isFinite(n) || n < 0) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}

function fmtTime(ts: number): string {
  if (!ts) return "—";
  try {
    return new Date(ts * 1000).toLocaleString();
  } catch {
    return String(ts);
  }
}

function shortHash(h: string): string {
  if (!h || h.length < 16) return h || "—";
  return `${h.slice(0, 10)}…${h.slice(-8)}`;
}

export function EvidenceView({
  evidenceHint,
  highlightId,
  onBackToWorkbench,
  onCountChange,
}: Props) {
  const api = typeof window !== "undefined" ? window.cyberguard : undefined;
  const [items, setItems] = useState<EvidenceItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [verifyById, setVerifyById] = useState<
    Record<string, EvidenceVerifyResult>
  >({});

  const refresh = useCallback(async () => {
    if (!api?.evidenceList) {
      setMsg("evidence API unavailable (open via Electron)");
      return;
    }
    setBusy(true);
    setMsg(null);
    try {
      const r = await api.evidenceList(200);
      const list = [...(r.evidence || [])].reverse();
      setItems(list);
      onCountChange?.(list.length);
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(false);
    }
  }, [api, onCountChange]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!highlightId) return;
    // expand + scroll to linked evidence from Workbench
    setExpanded((prev) => ({ ...prev, [highlightId]: true }));
    requestAnimationFrame(() => {
      document
        .getElementById(`evidence-row-${highlightId}`)
        ?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  }, [highlightId, items]);

  const onRegister = async () => {
    if (!api?.pickFile || !api?.evidenceRegister) {
      setMsg("register requires Electron file picker + evidence RPC");
      return;
    }
    setBusy(true);
    setMsg(null);
    try {
      const picked = await api.pickFile({
        title: "Register evidence file (read-only catalog)",
      });
      if (!picked?.path || picked.canceled) {
        setMsg("register canceled");
        return;
      }
      const r = await api.evidenceRegister(picked.path, note.trim() || undefined);
      if (r?.ok && r.item) {
        setMsg(
          `Registered ${r.item.name} · sha256 ${shortHash(r.item.sha256)} · mount read-only`
        );
        setNote("");
        await refresh();
      } else {
        setMsg("register failed");
      }
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(false);
    }
  };

  const onVerify = async (id: string) => {
    if (!api?.evidenceVerify) return;
    setBusy(true);
    try {
      const r = await api.evidenceVerify(id);
      setVerifyById((prev) => ({ ...prev, [id]: r }));
    } catch (e) {
      setVerifyById((prev) => ({
        ...prev,
        [id]: { ok: false, evidence_id: id, error: String(e) },
      }));
    } finally {
      setBusy(false);
    }
  };

  const onReveal = async (filePath: string) => {
    if (!api?.showItemInFolder) {
      setMsg("Reveal requires Electron shell");
      return;
    }
    setBusy(true);
    try {
      const r = await api.showItemInFolder(filePath);
      if (!r?.ok) setMsg(String(r?.error || "reveal failed"));
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(false);
    }
  };

  const toggleExpand = (id: string) => {
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  return (
    <div className="view-pane view-enter">
      <div className="view-pane-header">
        <div>
          <h1>证据</h1>
          <p className="lede">
            只读证据库：注册时算 sha256，校验时重算对比。正文不进模型上下文。
            {" · "}
            <span className="pill accent">{evidenceHint}</span>
          </p>
        </div>
        <div className="empty-actions">
          <button
            type="button"
            className="secondary"
            onClick={onBackToWorkbench}
          >
            返回调查
          </button>
          <button
            type="button"
            className="secondary"
            onClick={() => void refresh()}
            disabled={busy}
          >
            刷新
          </button>
        </div>
      </div>

      <div className="settings-card evidence-register">
        <h3>登记文件</h3>
        <p className="data-hint">
          选择本机文件 → 只读哈希写入 catalog（mount: read-only）。
        </p>
        <label className="field-label">
          备注（可选）
          <input
            className="data-input"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="工单 / 案件 / 上下文"
            disabled={busy}
          />
        </label>
        <div className="empty-actions mt-10">
          <button
            type="button"
            className="primary"
            onClick={() => void onRegister()}
            disabled={busy || !api?.evidenceRegister}
          >
            {busy ? "…" : "选择文件并登记…"}
          </button>
        </div>
        {msg && <pre className="data-msg">{msg}</pre>}
      </div>

      <div className="settings-card mt-12">
        <h3>
          目录{" "}
          <span className="pill">
            {items.length} 项
          </span>
        </h3>
        {items.length === 0 ? (
          <div className="evidence-empty">
            <p className="evidence-empty-title">暂无证据</p>
            <p className="muted-copy">
              演示时可登记一份告警导出或 PDF；调查过程中 agent
              工具也可能写入条目。
            </p>
          </div>
        ) : (
          <table className="evidence-table">
            <thead>
              <tr>
                <th>名称</th>
                <th>sha256</th>
                <th>大小</th>
                <th>挂载</th>
                <th>登记时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {items.map((it) => {
                const open = expanded[it.evidence_id];
                const v = verifyById[it.evidence_id];
                const hi = highlightId === it.evidence_id;
                return (
                  <tr
                    key={it.evidence_id}
                    id={`evidence-row-${it.evidence_id}`}
                    className={hi ? "evidence-row-hi" : undefined}
                  >
                    <td>
                      <div className="evidence-name">{it.name}</div>
                      {it.note ? (
                        <div className="muted-copy">{it.note}</div>
                      ) : null}
                      {open ? (
                        <div className="evidence-detail mono-xs">
                          <div>id: {it.evidence_id}</div>
                          <div>path: {it.path}</div>
                          <div>sha256: {it.sha256}</div>
                          <div>
                            trusted_dir: {String(it.trusted_dir ?? false)} ·
                            source: {it.source || "—"}
                          </div>
                        </div>
                      ) : null}
                      {v ? (
                        <div
                          className={`verify-result ${v.ok ? "ok" : "bad"}`}
                        >
                          {v.ok
                            ? "✓ 完整性 OK"
                            : `✗ ${v.error || "哈希不匹配"}`}
                          {!v.ok && v.current_sha256 ? (
                            <div className="mono-xs">
                              now {shortHash(v.current_sha256)}
                            </div>
                          ) : null}
                        </div>
                      ) : null}
                    </td>
                    <td>
                      <button
                        type="button"
                        className="hash-btn mono-xs"
                        onClick={() => toggleExpand(it.evidence_id)}
                        title={it.sha256}
                      >
                        {open ? it.sha256 : shortHash(it.sha256)}
                      </button>
                    </td>
                    <td>{fmtSize(it.size)}</td>
                    <td>
                      <span className="pill ok">
                        {it.mount || "read-only"}
                      </span>
                    </td>
                    <td className="mono-xs">{fmtTime(it.registered_at)}</td>
                    <td>
                      <div className="empty-actions">
                        <button
                          type="button"
                          className="secondary"
                          onClick={() => void onVerify(it.evidence_id)}
                          disabled={busy}
                        >
                          校验
                        </button>
                        <button
                          type="button"
                          className="secondary"
                          onClick={() => void onReveal(it.path)}
                          disabled={busy || !it.path}
                          title="在 Finder 中显示"
                        >
                          显示
                        </button>
                        <button
                          type="button"
                          className="secondary"
                          onClick={() => toggleExpand(it.evidence_id)}
                        >
                          {open ? "Collapse" : "Expand"}
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
