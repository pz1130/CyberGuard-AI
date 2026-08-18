import type { ActiveView } from "../../lib/types";
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

  return (
    <aside className="sidebar" aria-label="会话与导航">
      <div className="sidebar-top">
        <Button
          variant="primary"
          size="sm"
          onClick={() => {
            create();
            onNavigate("workbench");
          }}
        >
          ＋ 新建
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
