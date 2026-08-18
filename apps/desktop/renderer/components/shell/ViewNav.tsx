import type { ActiveView } from "../../lib/types";
import { ListRow } from "../../ui";

const VIEWS: Array<{ id: ActiveView; label: string }> = [
  { id: "workbench", label: "调查" },
  { id: "evidence", label: "证据" },
  { id: "settings", label: "设置" },
];

export type ViewNavProps = {
  activeView: ActiveView;
  onNavigate: (v: ActiveView) => void;
};

export function ViewNav({ activeView, onNavigate }: ViewNavProps) {
  return (
    <nav className="sidebar-nav" aria-label="主导航">
      {VIEWS.map((v) => (
        <ListRow
          key={v.id}
          variant="nav"
          active={activeView === v.id}
          title={v.label}
          onClick={() => onNavigate(v.id)}
        />
      ))}
    </nav>
  );
}
