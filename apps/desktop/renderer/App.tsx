import { useCallback, useMemo, useState } from "react";
import { PlanPanel } from "./components/PlanPanel";
import { StatusBar } from "./components/StatusBar";
import { useDesktopRuntime } from "./hooks/useDesktopRuntime";
import { useHotkeys } from "./hooks/useHotkeys";
import { useUiPrefs } from "./hooks/useUiPrefs";
import type { ActiveView, SettingsSection } from "./lib/types";
import "./lib/types";
import { EvidenceView } from "./views/EvidenceView";
import { SettingsView } from "./views/SettingsView";
import { WorkbenchView } from "./views/WorkbenchView";

const DEV_TITLE =
  "Development build · not notarized · not for distribution. Plan Mode = 自批准 (approval_type=self), timeout=reject. Local hash chain ≠ WORM.";

export function App() {
  const { theme, setTheme, cycleTheme, resolved, fontSize, setFontSize } =
    useUiPrefs();
  const [activeView, setActiveView] = useState<ActiveView>("workbench");
  const [settingsSection, setSettingsSection] = useState<
    SettingsSection | undefined
  >(undefined);
  const [highlightEvidenceId, setHighlightEvidenceId] = useState<
    string | undefined
  >(undefined);
  const [bannerOpen, setBannerOpen] = useState(false);
  const rt = useDesktopRuntime();

  const openEvidence = useCallback((evidenceId?: string) => {
    setHighlightEvidenceId(evidenceId);
    setActiveView("evidence");
  }, []);

  const openSettings = useCallback((section?: SettingsSection) => {
    setSettingsSection(section);
    setActiveView("settings");
  }, []);

  const hotkeyHandlers = useMemo(
    () => ({
      onNewSession: () => {
        setActiveView("workbench");
        rt.onNewInvestigation();
      },
      onSettings: () => openSettings(),
      onWorkbench: () => setActiveView("workbench"),
      onEvidence: () => setActiveView("evidence"),
      onRun: () => {
        if (activeView === "workbench") void rt.onRun();
      },
      onEscape: () => {
        if (document.activeElement instanceof HTMLElement) {
          document.activeElement.blur();
        }
      },
    }),
    [activeView, openSettings, rt.onNewInvestigation, rt.onRun]
  );
  useHotkeys(hotkeyHandlers);

  const showMockChip = rt.providerMode === "mock";
  const showCritical = Boolean(rt.fvWarning || rt.tccWarning || showMockChip);

  return (
    <div className="app">
      <header className="chrome">
        <div className="chrome-left">
          <div className="chrome-brand">
            <span className="chrome-mark" aria-hidden />
            <div className="chrome-brand-meta">
              <span className="chrome-brand-name">CyberGuard</span>
              <span className="chrome-brand-sub">Desktop</span>
            </div>
          </div>
          <nav className="chrome-nav" aria-label="Primary">
            <button
              type="button"
              className={`nav-tab${activeView === "workbench" ? " active" : ""}`}
              onClick={() => setActiveView("workbench")}
            >
              Workbench
            </button>
            <button
              type="button"
              className={`nav-tab${activeView === "evidence" ? " active" : ""}`}
              onClick={() => setActiveView("evidence")}
            >
              Evidence
            </button>
            <button
              type="button"
              className={`nav-tab${activeView === "settings" ? " active" : ""}`}
              onClick={() => openSettings()}
            >
              Settings
            </button>
          </nav>
        </div>
        <div className="chrome-right">
          <button
            type="button"
            className="pill warn chrome-dev-btn"
            title={DEV_TITLE}
            onClick={() => setBannerOpen((v) => !v)}
          >
            DEV
          </button>
          <button
            type="button"
            className="chrome-icon-btn"
            onClick={cycleTheme}
            title={`Theme: ${theme} (${resolved})`}
          >
            {resolved === "dark" ? "Dark" : "Light"}
          </button>
        </div>
      </header>

      {bannerOpen && (
        <div className="banner banner-compact">
          <span>{DEV_TITLE}</span>
          <button
            type="button"
            className="banner-dismiss"
            onClick={() => setBannerOpen(false)}
          >
            收起
          </button>
        </div>
      )}

      {rt.pendingPlan && activeView === "workbench" && (
        <PlanPanel
          pendingPlan={rt.pendingPlan}
          planEdit={rt.planEdit}
          onPlanEdit={rt.setPlanEdit}
          onApprove={() => void rt.onPlanApprove()}
          onReject={() => void rt.onPlanReject()}
        />
      )}

      {showCritical && (
        <div className="alert-strip">
          {rt.fvWarning && (
            <span className="alert-chip danger" title={rt.fvWarning}>
              FileVault: {rt.fvWarning}
            </span>
          )}
          {rt.tccWarning && (
            <span
              className="alert-chip warn"
              title={rt.tccGuidance || rt.tccWarning}
            >
              TCC: {rt.tccWarning}
            </span>
          )}
          {showMockChip && (
            <button
              type="button"
              className="alert-chip warn alert-chip-btn"
              onClick={() => openSettings("llm")}
            >
              LLM 为 mock · 点此配置 key
            </button>
          )}
        </div>
      )}

      <StatusBar
        statusLabel={rt.statusLabel}
        pingOk={rt.pingOk}
        sandboxImpl={rt.sandboxImpl}
        sandboxMode={rt.sandboxMode}
        tccSummary={rt.tccSummary}
        tccGuidance={rt.tccGuidance}
        tccWarning={rt.tccWarning}
        providerMode={rt.providerMode}
        tier={rt.tier}
        runStatus={rt.runStatus}
        pausedRunId={rt.pausedRunId}
        evidenceHint={rt.evidenceHint}
      />

      {activeView === "workbench" && (
        <WorkbenchView
          sessions={rt.sessions}
          sessionId={rt.sessionId}
          onSelectSession={(id) => void rt.onSelectSession(id)}
          onNewInvestigation={rt.onNewInvestigation}
          onDeleteSession={(id) => void rt.onDeleteSession(id)}
          events={rt.events}
          streamText={rt.streamText}
          streaming={rt.streaming}
          lastSubmitted={rt.lastSubmitted}
          task={rt.task}
          onTaskChange={rt.setTask}
          onRun={() => void rt.onRun()}
          onAbort={() => void rt.onAbort()}
          onResume={() => void rt.onResume()}
          running={rt.running}
          runId={rt.runId}
          pausedRunId={rt.pausedRunId}
          runStatus={rt.runStatus}
          tier={rt.tier}
          onTierChange={rt.setTier}
          steerText={rt.steerText}
          onSteerTextChange={rt.setSteerText}
          onSteer={() => void rt.onSteer()}
          caps={rt.caps}
          dataRoot={rt.dataRoot}
          mcpTools={rt.mcpTools}
          hasApi={Boolean(rt.api)}
          providerMode={rt.providerMode}
          onOpenSettingsLlm={() => openSettings("llm")}
          onOpenSettingsMcp={() => openSettings("mcp")}
          onViewEvidence={openEvidence}
          showDataPanel={rt.showDataPanel}
          onToggleDataPanel={() => rt.setShowDataPanel((v) => !v)}
          exportPass={rt.exportPass}
          onExportPass={rt.setExportPass}
          exportBusy={rt.exportBusy}
          exportMsg={rt.exportMsg}
          onExport={() => void rt.onExport()}
          exportAvailable={Boolean(rt.api?.exportEncrypted)}
          uninstallBusy={rt.uninstallBusy}
          uninstallPreview={rt.uninstallPreview}
          onUninstallInventory={() => void rt.onUninstallInventory()}
          onUninstallDryRun={() => void rt.onUninstallDryRun()}
          onUninstallExecute={() => void rt.onUninstallExecute()}
        />
      )}

      {activeView === "evidence" && (
        <EvidenceView
          evidenceHint={rt.evidenceHint}
          highlightId={highlightEvidenceId}
          onBackToWorkbench={() => setActiveView("workbench")}
          onCountChange={(n) => rt.setEvidenceHint(`evidence: ${n}`)}
        />
      )}

      {activeView === "settings" && (
        <SettingsView
          theme={theme}
          resolved={resolved}
          fontSize={fontSize}
          providerMode={rt.providerMode}
          dataRoot={rt.dataRoot}
          onCycleTheme={cycleTheme}
          onSetTheme={setTheme}
          onSetFontSize={setFontSize}
          focusSection={settingsSection}
          onProviderSaved={(mode) => {
            rt.setProviderMode(mode);
            void rt.refreshProviderStatus();
          }}
          showDataPanel={rt.showDataPanel}
          onToggleDataPanel={() => rt.setShowDataPanel((v) => !v)}
          exportPass={rt.exportPass}
          onExportPass={rt.setExportPass}
          exportBusy={rt.exportBusy}
          exportMsg={rt.exportMsg}
          onExport={() => void rt.onExport()}
          exportAvailable={Boolean(rt.api?.exportEncrypted)}
          uninstallBusy={rt.uninstallBusy}
          uninstallPreview={rt.uninstallPreview}
          onUninstallInventory={() => void rt.onUninstallInventory()}
          onUninstallDryRun={() => void rt.onUninstallDryRun()}
          onUninstallExecute={() => void rt.onUninstallExecute()}
        />
      )}
    </div>
  );
}
