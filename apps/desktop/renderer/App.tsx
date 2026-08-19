import { useCallback, useEffect, useMemo, useState } from "react";
import { StatusBar } from "./components/context/StatusBar";
import { AppChrome } from "./components/shell/AppChrome";
import { DegradationStrip } from "./components/shell/DegradationStrip";
import { Sidebar } from "./components/shell/Sidebar";
import "./components/shell/AppShell.css";
import { useHotkeys } from "./hooks/useHotkeys";
import { I18nProvider, useI18n } from "./i18n/I18nProvider";
import type { ActiveView, SettingsSection } from "./lib/types";
import {
  RuntimeProvider,
  UiPrefsProvider,
  useEnvironment,
  useRun,
  useSessions,
  useUiPrefsCtx,
} from "./state";
import { DataLifecycleProvider } from "./state/useDataLifecycle";
import { TooltipProvider } from "./ui";
import { EvidenceView } from "./views/EvidenceView";
import { SettingsView } from "./views/SettingsView";
import { WorkbenchView } from "./views/WorkbenchView";

export function App() {
  return (
    <TooltipProvider>
      <I18nProvider>
        <UiPrefsProvider>
          <RuntimeProvider>
            <AppInner />
          </RuntimeProvider>
        </UiPrefsProvider>
      </I18nProvider>
    </TooltipProvider>
  );
}

function AppInner() {
  const { t } = useI18n();
  const {
    sidebarCollapsed,
    setSidebarCollapsed,
    railCollapsed,
    setRailCollapsed,
  } = useUiPrefsCtx();
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

  const title =
    sessions.sessions.find((s) => s.session_id === sessions.sessionId)?.title ||
    run.lastSubmitted ||
    t("app.newInvestigation");

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
      onToggleSidebar: () => setSidebarCollapsed(!sidebarCollapsed),
    }),
    [
      activeView,
      env.pingOk,
      openSettings,
      sessions.create,
      run.run,
      setSidebarCollapsed,
      sidebarCollapsed,
    ]
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
          title={title}
          devTitle={t("app.devTitle")}
          onToggleSidebar={() => setSidebarCollapsed(!sidebarCollapsed)}
          onToggleRail={() => setRailCollapsed(!railCollapsed)}
        />
        <DegradationStrip />

        <div className="app-body">
          {!sidebarCollapsed && (
            <Sidebar activeView={activeView} onNavigate={setActiveView} />
          )}
          <div className="app-main">
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
                focusSection={settingsSection}
                onProviderSaved={(mode) => {
                  env.setProviderMode(mode);
                  void env.refreshProvider();
                }}
              />
            )}
          </div>
        </div>
        <StatusBar onOpenSettings={openSettings} />
      </div>
    </DataLifecycleProvider>
  );
}
