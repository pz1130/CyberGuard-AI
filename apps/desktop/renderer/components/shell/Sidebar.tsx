import type { ActiveView } from "../../lib/types";
import { useI18n } from "../../i18n/I18nProvider";
import { useSessions } from "../../state";
import { Button } from "../../ui";
import { SessionRail } from "../session/SessionRail";
import { ViewNav } from "./ViewNav";
import "./Sidebar.css";

export type SidebarProps = {
  activeView: ActiveView;
  onNavigate: (v: ActiveView) => void;
};

export function Sidebar({ activeView, onNavigate }: SidebarProps) {
  const { create } = useSessions();
  const { t } = useI18n();

  return (
    <aside className="sidebar" aria-label={t("nav.sidebar.aria")}>
      <div className="sidebar-top">
        <Button
          variant="primary"
          size="sm"
          onClick={() => {
            create();
            onNavigate("workbench");
          }}
        >
          {t("nav.sidebar.new")}
        </Button>
      </div>
      <div className="sidebar-sessions">
        <SessionRail />
      </div>
      <div className="sidebar-foot">
        <ViewNav activeView={activeView} onNavigate={onNavigate} />
      </div>
    </aside>
  );
}
