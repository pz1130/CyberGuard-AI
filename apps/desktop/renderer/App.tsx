import { useCallback, useMemo, useState } from "react";
import { PlanPanel } from "./components/PlanPanel";
import { AppChrome } from "./components/shell/AppChrome";
import { DegradationStrip } from "./components/shell/DegradationStrip";
import { useHotkeys } from "./hooks/useHotkeys";
import { useUiPrefs } from "./hooks/useUiPrefs";
import type { ActiveView, SettingsSection } from "./lib/types";
import {
  RuntimeProvider,
  useEnvironment,
  usePlan,
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
  const { pendingPlan, planEdit, setPlanEdit, approve, reject } = usePlan();

  const openEvidence = useCallback((evidenceId?: string) => {
    setHighlightEvidenceId(evidenceId);
    setActiveView("evidence");
  }, []);

  const openSettings = useCallback((section: SettingsSection = "hub") => {
    setSettingsSection(section);
    setActiveView("settings");
  }, []);

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
        if (activeView === "workbench") void run.run();
      },
      onEscape: () => {
        if (document.activeElement instanceof HTMLElement) {
          document.activeElement.blur();
        }
      },
    }),
    [activeView, openSettings, sessions.create, run.run]
  );
  useHotkeys(hotkeyHandlers);

  return (
    <DataLifecycleProvider
      onUninstalled={() => {
        sessions.clearAll();
      }}
    >
      <div className="app">
        <AppChrome
          activeView={activeView}
          onNavigate={setActiveView}
          themeLabel={resolved === "dark" ? "Dark" : "Light"}
          onCycleTheme={cycleTheme}
          devTitle={DEV_TITLE}
        />
        <DegradationStrip />

        {pendingPlan && activeView === "workbench" && (
          <PlanPanel
            pendingPlan={pendingPlan}
            planEdit={planEdit}
            onPlanEdit={setPlanEdit}
            onApprove={() => void approve()}
            onReject={() => void reject()}
          />
        )}

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
      </div>
    </DataLifecycleProvider>
  );
}
