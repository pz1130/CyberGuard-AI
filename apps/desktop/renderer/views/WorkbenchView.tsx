import "../components/workbench/WorkbenchLayout.css";
import { ContextRail } from "../components/context/ContextRail";
import { Composer } from "../components/investigation/Composer";
import { PlanPanel } from "../components/investigation/PlanPanel";
import { Timeline } from "../components/investigation/Timeline";
import type { SettingsSection } from "../lib/types";

export type WorkbenchViewProps = {
  onViewEvidence: (evidenceId?: string) => void;
  onOpenSettings: (section?: SettingsSection) => void;
};

export function WorkbenchView(props: WorkbenchViewProps) {
  return (
    <div className="wb">
      <div className="wb-main">
        <PlanPanel />
        <div className="wb-timeline">
          <Timeline onViewEvidence={props.onViewEvidence} />
        </div>
        <Composer />
      </div>
      <ContextRail
        onViewEvidence={props.onViewEvidence}
        onOpenSettings={props.onOpenSettings}
      />
    </div>
  );
}
