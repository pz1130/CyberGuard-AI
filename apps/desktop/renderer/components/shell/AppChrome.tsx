import { useI18n } from "../../i18n/I18nProvider";
import { useUiPrefsCtx } from "../../state";
import { Button } from "../../ui";
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
  const { t } = useI18n();
  const { cycleTheme, resolved } = useUiPrefsCtx();

  return (
    <header className="chrome" role="banner">
      <Button
        size="icon"
        variant="ghost"
        aria-label={t("chrome.toggleSidebar")}
        onClick={onToggleSidebar}
      >
        ☰
      </Button>
      <h1 className="chrome-title">{title}</h1>
      <div className="chrome-right">
        <span className="chrome-dev" title={devTitle}>
          DEV
        </span>
        <Button
          size="icon"
          variant="ghost"
          aria-label={t("chrome.toggleTheme")}
          onClick={cycleTheme}
        >
          {resolved === "dark" ? "◐" : "◑"}
        </Button>
        <Button
          size="icon"
          variant="ghost"
          aria-label={t("chrome.toggleRail")}
          onClick={onToggleRail}
        >
          ⌄
        </Button>
      </div>
    </header>
  );
}
