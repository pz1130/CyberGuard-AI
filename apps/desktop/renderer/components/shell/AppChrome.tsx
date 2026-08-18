import { Button } from "../../ui";
import { useUiPrefsCtx } from "../../state";
import "./AppChrome.css";

export type AppChromeProps = {
  title: string;
  devTitle: string;
  onToggleSidebar: () => void;
  onToggleRail: () => void;
};

export function AppChrome({
  title,
  devTitle,
  onToggleSidebar,
  onToggleRail,
}: AppChromeProps) {
  const { cycleTheme, resolved } = useUiPrefsCtx();

  return (
    <header className="chrome" role="banner">
      <Button size="icon" variant="ghost" aria-label="切换侧栏" onClick={onToggleSidebar}>
        ☰
      </Button>
      <h1 className="chrome-title">{title}</h1>
      <div className="chrome-right">
        <span className="chrome-dev" title={devTitle}>DEV</span>
        <Button size="icon" variant="ghost" aria-label="切换主题" onClick={cycleTheme}>
          {resolved === "dark" ? "◐" : "◑"}
        </Button>
        <Button size="icon" variant="ghost" aria-label="切换侧板" onClick={onToggleRail}>
          ⌄
        </Button>
      </div>
    </header>
  );
}
