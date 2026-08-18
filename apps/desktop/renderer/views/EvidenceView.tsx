import { useCallback, useEffect, useState } from "react";
import type { EvidenceItem, EvidenceVerifyResult } from "../lib/types";
import { Button, Field, ListRow, Panel, Prose, Timestamp } from "../ui";

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
  const [selectedId, setSelectedId] = useState<string | null>(null);
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
    setSelectedId(highlightId);
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
        setSelectedId(r.item.evidence_id);
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

  const selected = items.find((it) => it.evidence_id === selectedId) ?? null;
  const selectedVerify = selected
    ? verifyById[selected.evidence_id]
    : undefined;

  return (
    <div className="view-pane view-enter">
      <div className="evidence-view">
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
            <Button variant="secondary" onClick={onBackToWorkbench}>
              返回调查
            </Button>
            <Button
              variant="secondary"
              onClick={() => void refresh()}
              disabled={busy}
            >
              刷新
            </Button>
          </div>
        </div>

        <Panel title="登记文件">
          <p className="evidence-hint">
            选择本机文件 → 只读哈希写入 catalog（mount: read-only）。
          </p>
          <Field label="备注（可选）">
            <input
              className="data-input"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="工单 / 案件 / 上下文"
              disabled={busy}
            />
          </Field>
          <div className="empty-actions evidence-register-actions">
            <Button
              variant="primary"
              onClick={() => void onRegister()}
              disabled={busy || !api?.evidenceRegister}
            >
              {busy ? "…" : "选择文件并登记…"}
            </Button>
          </div>
          {msg ? <pre className="evidence-msg">{msg}</pre> : null}
        </Panel>

        <Panel
          title={
            <>
              目录 <span className="pill">{items.length} 项</span>
            </>
          }
        >
          {items.length === 0 ? (
            <Prose>
              <p>
                <strong>暂无证据</strong>
              </p>
              <p>
                演示时可登记一份告警导出或 PDF；调查过程中 agent
                工具也可能写入条目。
              </p>
            </Prose>
          ) : (
            <div className="evidence-list">
              {items.map((it) => {
                const hi = highlightId === it.evidence_id;
                const active = selectedId === it.evidence_id;
                return (
                  <div
                    key={it.evidence_id}
                    id={`evidence-row-${it.evidence_id}`}
                    className={hi ? "evidence-row-hi" : undefined}
                  >
                    <ListRow
                      active={active || hi}
                      title={it.name}
                      meta={
                        <>
                          <Timestamp value={it.registered_at} />
                          {" · "}
                          <span className="evidence-mono">
                            {shortHash(it.sha256)}
                          </span>
                        </>
                      }
                      onClick={() =>
                        setSelectedId((prev) =>
                          prev === it.evidence_id ? null : it.evidence_id
                        )
                      }
                    />
                  </div>
                );
              })}
            </div>
          )}
        </Panel>

        {selected ? (
          <Panel
            title={selected.name}
            actions={
              <div className="empty-actions">
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => void onVerify(selected.evidence_id)}
                  disabled={busy}
                >
                  校验
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => void onReveal(selected.path)}
                  disabled={busy || !selected.path}
                  title="在 Finder 中显示"
                >
                  显示
                </Button>
              </div>
            }
          >
            {selected.note ? (
              <Prose>
                <p>{selected.note}</p>
              </Prose>
            ) : null}
            <dl className="evidence-detail evidence-mono">
              <div>
                <dt>id</dt>
                <dd>{selected.evidence_id}</dd>
              </div>
              <div>
                <dt>path</dt>
                <dd>{selected.path}</dd>
              </div>
              <div>
                <dt>sha256</dt>
                <dd>{selected.sha256}</dd>
              </div>
              <div>
                <dt>size</dt>
                <dd>{fmtSize(selected.size)}</dd>
              </div>
              <div>
                <dt>mount</dt>
                <dd>{selected.mount || "read-only"}</dd>
              </div>
              <div>
                <dt>trusted_dir</dt>
                <dd>{String(selected.trusted_dir ?? false)}</dd>
              </div>
              <div>
                <dt>source</dt>
                <dd>{selected.source || "—"}</dd>
              </div>
            </dl>
            {selectedVerify ? (
              <p
                className={`evidence-verify ${selectedVerify.ok ? "ok" : "bad"}`}
              >
                {selectedVerify.ok
                  ? "✓ 完整性 OK"
                  : `✗ ${selectedVerify.error || "哈希不匹配"}`}
                {!selectedVerify.ok && selectedVerify.current_sha256 ? (
                  <span className="evidence-mono">
                    {" "}
                    · now {shortHash(selectedVerify.current_sha256)}
                  </span>
                ) : null}
              </p>
            ) : null}
          </Panel>
        ) : null}
      </div>
    </div>
  );
}
