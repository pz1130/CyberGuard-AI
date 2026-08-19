import { useState } from "react";
import { useI18n } from "../../i18n/I18nProvider";
import type { SessionRow } from "../../lib/types";
import { useSessions } from "../../state";
import { Button, ListRow, Timestamp } from "../../ui";
import "./SessionRail.css";

// 示例任务已移至 lib/sampleTasks.ts，由中间栏空态 TimelineEmpty 消费

const UNDO_MS = 5000;

export function SessionRail() {
  const { t } = useI18n();
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
          if (!ok) setDeleteError(t("session.deleteFailed"));
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
          <p className="sessionrail-empty-hint">{t("session.empty")}</p>
        </div>
      ) : (
        <>
          <div className="sessionrail-list">
            {visible.map((s) => (
              <ListRow
                key={s.session_id}
                variant="nav"
                active={s.session_id === sessionId}
                title={s.title || t("session.untitled")}
                meta={<Timestamp value={s.updated_at} />}
                onClick={() => void select(s.session_id)}
                actions={
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-label={t("session.deleteAria", {
                      title: s.title || t("session.untitled"),
                    })}
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
              <span>{t("session.deletedUndo")}</span>
              <Button size="sm" variant="ghost" onClick={undoDelete}>
                {t("session.undo")}
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
