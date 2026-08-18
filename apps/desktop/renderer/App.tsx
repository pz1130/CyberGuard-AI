import { useCallback, useEffect, useMemo, useState } from "react";
import { StatusBar } from "./components/context/StatusBar";
import { AppChrome } from "./components/shell/AppChrome";
import { DegradationStrip } from "./components/shell/DegradationStrip";
import "./components/shell/AppShell.css";
import { useHotkeys } from "./hooks/useHotkeys";
import { useUiPrefs } from "./hooks/useUiPrefs";
import type { ActiveView, SettingsSection } from "./lib/types";
import {
  RuntimeProvider,
  useEnvironment,
  useRun,
  useSessions,
} from "./state";
import { DataLifecycleProvider } from "./state/useDataLifecycle";
import { TooltipProvider } from "./ui";
import { EvidenceView } from "./views/EvidenceView";
import { SettingsView } from "./views/SettingsView";
import { WorkbenchView } from "./views/WorkbenchView";

const DEV_TITLE =
  "Development build · not notarized · not for distribution. Plan Mode = 自批准 (approval_type=self), timeout=reject. Local hash chain ≠ WORM.";

export function App() {
  return (
    <TooltipProvider>
      <RuntimeProvider>
        <AppInner />
      </RuntimeProvider>
    </TooltipProvider>
  );
}

function AppInner() {
  const { theme, setTheme, cycleTheme, resolved, fontSize, setFontSize } =
    useUiPrefs();
  const [activeView, setActiveView] = useState<ActiveView>("workbench");
  const [settingsSection, setSettingsSection] = useState<
    SettingsSection | undefined
  >(undefined);
  const [highlightEvidenceId, setHighlightEvidenceId] = useState<
    string | undefined
  >(undefined);

  const run = useRun();
  const sessions = useSessions();
  const env = useEnvironment();

  const openEvidence = useCallback((evidenceId?: string) => {
    setHighlightEvidenceId(evidenceId);
    setActiveView("evidence");
  }, []);

  const openSettings = useCallback((section: SettingsSection = "hub") => {
    setSettingsSection(section);
    setActiveView("settings");
  }, []);

  useEffect(() => {
    const api = typeof window !== "undefined" ? window.cyberguard : undefined;
    if (!api?.onOpenDataPanel) return;
    return api.onOpenDataPanel(() => openSettings("data"));
  }, [openSettings]);

  const hotkeyHandlers = useMemo(
    () => ({
      onNewSession: () => {
        sessions.create();
        setActiveView("workbench");
      },
      onSettings: () => openSettings(),
      onWorkbench: () => setActiveView("workbench"),
      onEvidence: () => setActiveView("evidence"),
      onRun: () => {
        // Composer 在 sidecar 离线时禁用运行（INV-25）；全局 ⌘↵ 必须同一闸
        if (activeView === "workbench" && env.pingOk !== false) void run.run();
      },
      onEscape: () => {
        if (document.activeElement instanceof HTMLElement) {
          document.activeElement.blur();
        }
      },
    }),
    [activeView, env.pingOk, openSettings, sessions.create, run.run]
  );
  useHotkeys(hotkeyHandlers);

  return (
    <DataLifecycleProvider
      onUninstalled={() => {
        sessions.clearAll();
      }}
    >
      <div className="app-shell">
        <AppChrome
          activeView={activeView}
          onNavigate={setActiveView}
          themeLabel={resolved === "dark" ? "Dark" : "Light"}
          onCycleTheme={cycleTheme}
          devTitle={DEV_TITLE}
        />
        <DegradationStrip />

        {activeView === "workbench" && (
          <WorkbenchView
            onViewEvidence={openEvidence}
            onOpenSettings={openSettings}
          />
        )}

        {activeView === "evidence" && (
          <EvidenceView
            evidenceHint={
              env.evidenceCount ? `evidence: ${env.evidenceCount}` : ""
            }
            highlightId={highlightEvidenceId}
            onBackToWorkbench={() => setActiveView("workbench")}
            onCountChange={(n) => env.setEvidenceCount(n)}
          />
        )}

        {activeView === "settings" && (
          <SettingsView
            theme={theme}
            resolved={resolved}
            fontSize={fontSize}
            providerMode={env.providerMode}
            dataRoot={env.dataRoot}
            onCycleTheme={cycleTheme}
            onSetTheme={setTheme}
            onSetFontSize={setFontSize}
            focusSection={settingsSection}
            onProviderSaved={(mode) => {
              env.setProviderMode(mode);
              void env.refreshProvider();
            }}
          />
        )}
        <StatusBar onOpenSettings={openSettings} />
      </div>
    </DataLifecycleProvider>
  );
}
