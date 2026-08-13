import type { ActiveView } from "../../lib/types";
import { Button } from "../../ui";
import "./AppChrome.css";

const TABS: Array<{ id: ActiveView; label: string }> = [
  { id: "workbench", label: "调查" },
  { id: "evidence", label: "证据" },
  { id: "settings", label: "设置" },
];

export type AppChromeProps = {
  activeView: ActiveView;
  onNavigate: (v: ActiveView) => void;
  themeLabel: string;
  onCycleTheme: () => void;
  devTitle: string;
};

export function AppChrome({
  activeView,
  onNavigate,
  themeLabel,
  onCycleTheme,
  devTitle,
}: AppChromeProps) {
  return (
    <header className="chrome2">
      <div className="chrome2-brand">
        <span className="chrome2-mark" aria-hidden />
        <span className="chrome2-name">CyberGuard</span>
      </div>
      <nav className="chrome2-nav" aria-label="主导航">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            className={`chrome2-tab${activeView === t.id ? " is-active" : ""}`}
            aria-current={activeView === t.id || undefined}
            onClick={() => onNavigate(t.id)}
          >
            {t.label}
          </button>
        ))}
      </nav>
      <div className="chrome2-right">
        <span className="chrome2-dev" title={devTitle}>
          DEV
        </span>
        <Button variant="ghost" size="sm" onClick={onCycleTheme}>
          {themeLabel}
        </Button>
      </div>
    </header>
  );
}
