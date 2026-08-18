import { useState } from "react";
import type { SessionRow } from "../../lib/types";
import { useSessions } from "../../state";
import { Button, ListRow, Timestamp } from "../../ui";
import "./SessionRail.css";

// 示例任务已移至 lib/sampleTasks.ts，由中间栏空态 TimelineEmpty 消费

const UNDO_MS = 5000;

export function SessionRail() {
  const { sessions, sessionId, select, remove } = useSessions();
  const [pendingDelete, setPendingDelete] = useState<{
    row: SessionRow;
    timeoutId: ReturnType<typeof setTimeout>;
  } | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const hiddenId = pendingDelete?.row.session_id;
  const visible = hiddenId
    ? sessions.filter((s) => s.session_id !== hiddenId)
    : sessions;

  const requestDelete = (row: SessionRow) => {
    setDeleteError(null);
    setPendingDelete((prev) => {
      if (prev) clearTimeout(prev.timeoutId);
      const timeoutId = setTimeout(() => {
        setPendingDelete(null);
        void remove(row.session_id).then((ok) => {
          if (!ok) setDeleteError("删除失败");
        });
      }, UNDO_MS);
      return { row, timeoutId };
    });
  };

  const undoDelete = () => {
    setPendingDelete((prev) => {
      if (prev) clearTimeout(prev.timeoutId);
      return null;
    });
    setDeleteError(null);
  };

  return (
    <div className="sessionrail">
      {sessions.length === 0 ? (
        <div className="sessionrail-empty">
          {/* 示例任务在中间栏空态里，那儿有横向空间放完整描述；这里不重复 */}
          <p className="sessionrail-empty-hint">
            还没有调查记录。跑完一次后会出现在这里，可随时回看或续查。
          </p>
        </div>
      ) : (
        <>
          <div className="sessionrail-list">
            {visible.map((s) => (
              <ListRow
                key={s.session_id}
                variant="nav"
                active={s.session_id === sessionId}
                title={s.title || "未命名调查"}
                meta={<Timestamp value={s.updated_at} />}
                onClick={() => void select(s.session_id)}
                actions={
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-label={`删除 ${s.title}`}
                    onClick={() => requestDelete(s)}
                  >
                    ✕
                  </Button>
                }
              />
            ))}
          </div>
          {pendingDelete ? (
            <div className="sessionrail-undo" role="status">
              <span>已删除 · 撤销</span>
              <Button size="sm" variant="ghost" onClick={undoDelete}>
                撤销
              </Button>
            </div>
          ) : null}
          {deleteError ? (
            <p className="sessionrail-error" role="alert">
              {deleteError}
            </p>
          ) : null}
        </>
      )}
    </div>
  );
}
