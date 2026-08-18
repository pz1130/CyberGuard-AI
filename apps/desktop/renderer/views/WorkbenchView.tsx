import "../components/workbench/WorkbenchLayout.css";
import { ContextRail } from "../components/context/ContextRail";
import { Composer } from "../components/investigation/Composer";
import { PlanPanel } from "../components/investigation/PlanPanel";
import { Timeline } from "../components/investigation/Timeline";
import type { SettingsSection } from "../lib/types";
import { useUiPrefsCtx } from "../state";

export type WorkbenchViewProps = {
  onViewEvidence: (evidenceId?: string) => void;
  onOpenSettings: (section?: SettingsSection) => void;
};

export function WorkbenchView(props: WorkbenchViewProps) {
  const { railCollapsed } = useUiPrefsCtx();

  return (
    <div className={`wb${railCollapsed ? " wb--norail" : ""}`}>
      <div className="wb-main">
        <PlanPanel />
        <div className="wb-timeline">
          <Timeline onViewEvidence={props.onViewEvidence} />
        </div>
        <Composer />
      </div>
      {!railCollapsed && (
        <ContextRail
          onViewEvidence={props.onViewEvidence}
          onOpenSettings={props.onOpenSettings}
        />
      )}
    </div>
  );
}
