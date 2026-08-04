import { useCallback, useEffect, useState } from "react";
import type { EvidenceItem, EvidenceVerifyResult } from "../lib/types";

type Props = {
  evidenceHint: string;
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

  const toggleExpand = (id: string) => {
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  return (
    <div className="view-pane view-enter">
      <div className="view-pane-header">
        <div>
          <h1>Evidence</h1>
          <p className="lede">
            只读证据库：注册时计算 sha256，校验时重算对比。路径可在 data_root
            外；正文不进模型上下文。状态栏：{" "}
            <span className="pill accent">{evidenceHint}</span>
          </p>
        </div>
        <div className="empty-actions">
          <button
            type="button"
            className="secondary"
            onClick={onBackToWorkbench}
          >
            Workbench
          </button>
          <button
            type="button"
            className="secondary"
            onClick={() => void refresh()}
            disabled={busy}
          >
            Refresh
          </button>
        </div>
      </div>

      <div className="settings-card evidence-register">
        <h3>Register file</h3>
        <p className="data-hint">
          选择本机文件 → sidecar 只读哈希并写入 catalog（mount: read-only）。
        </p>
        <label className="field-label">
          Note (optional)
          <input
            className="data-input"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="case / ticket / context"
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
            {busy ? "…" : "Register via file picker…"}
          </button>
        </div>
        {msg && <pre className="data-msg">{msg}</pre>}
      </div>

      <div className="settings-card mt-12">
        <h3>
          Catalog{" "}
          <span className="pill">{items.length} item{items.length === 1 ? "" : "s"}</span>
        </h3>
        {items.length === 0 ? (
          <p className="muted-copy mt-10">
            No evidence registered yet. Use the button above or agent tools.
          </p>
        ) : (
          <table className="evidence-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>sha256</th>
                <th>Size</th>
                <th>Mount</th>
                <th>Registered</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((it) => {
                const open = expanded[it.evidence_id];
                const v = verifyById[it.evidence_id];
                return (
                  <tr key={it.evidence_id}>
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
                            ? "✓ integrity OK"
                            : `✗ ${v.error || "hash mismatch"}`}
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
                          Verify
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
