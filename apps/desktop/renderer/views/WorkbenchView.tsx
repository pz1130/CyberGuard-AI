import "../components/workbench/WorkbenchLayout.css";
import { ContextRail } from "../components/context/ContextRail";
import { Timeline } from "../components/investigation/Timeline";
import { SessionRail } from "../components/session/SessionRail";
import type { SettingsSection } from "../lib/types";

export type WorkbenchViewProps = {
  onViewEvidence: (evidenceId?: string) => void;
  onOpenSettings: (section?: SettingsSection) => void;
};

export function WorkbenchView(props: WorkbenchViewProps) {
  return (
    <div className="wb">
      <SessionRail />
      <div className="wb-main">
        <div className="wb-timeline">
          <Timeline onViewEvidence={props.onViewEvidence} />
        </div>
      </div>
      <ContextRail
        onViewEvidence={props.onViewEvidence}
        onOpenSettings={props.onOpenSettings}
      />
    </div>
  );
}
