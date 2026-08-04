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

  return (
    <div className="app">
      <header className="chrome">
        <div className="chrome-left">
          <div className="chrome-brand">
            <span className="chrome-mark" aria-hidden />
            <div className="chrome-brand-meta">
              <span className="chrome-brand-name">CyberGuard</span>
              <span className="chrome-brand-sub">Desktop · ops</span>
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
          <span className="pill warn" title="Development build — not for distribution">
            DEV
          </span>
          <button
            type="button"
            className="chrome-icon-btn"
            onClick={cycleTheme}
            title={`Theme: ${theme} (${resolved})`}
          >
            {resolved === "dark" ? "◐ Dark" : "☀ Light"}
            {theme === "system" ? " · Auto" : ""}
          </button>
        </div>
      </header>

      <div className="banner">
        <strong>Development build (not notarized)</strong> — not for
        distribution. Plan Mode uses <em>自批准</em> (approval_type=self) — not
        segregation-of-duties. Timeout = reject. LLM:{" "}
        <code>{rt.providerMode}</code>. Local hash chain ≠ WORM.
      </div>

      {rt.pendingPlan && activeView === "workbench" && (
        <PlanPanel
          pendingPlan={rt.pendingPlan}
          planEdit={rt.planEdit}
          onPlanEdit={rt.setPlanEdit}
          onApprove={() => void rt.onPlanApprove()}
          onReject={() => void rt.onPlanReject()}
        />
      )}

      {rt.fvWarning && (
        <div className="banner banner-danger">
          <strong>FileVault:</strong> {rt.fvWarning}
        </div>
      )}
      {rt.tccWarning && (
        <div className="banner banner-warn">
          <strong>TCC:</strong> {rt.tccWarning}
          {rt.tccGuidance ? (
            <div className="banner-sub">{rt.tccGuidance}</div>
          ) : null}
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

      {rt.providerMode === "mock" && (
        <div className="banner banner-warn">
          <strong>LLM is mock</strong> — live key missing or not loaded. Open{" "}
          <button
            type="button"
            className="linkish"
            onClick={() => openSettings("llm")}
          >
            Settings → LLM
          </button>
          , paste API key, Save, then Test. (Keys stay in secrets store, never
          re-shown.)
        </div>
      )}

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

      <div className="footer">
        CyberGuard Desktop · not notarized · not for distribution · ⌘1 Workbench
        · ⌘2 Evidence · ⌘, Settings · ⌘N New · ⌘Enter Run
      </div>
    </div>
  );
}
