import "../components/workbench/WorkbenchLayout.css";
import { ContextRail } from "../components/context/ContextRail";
import { Composer } from "../components/investigation/Composer";
import { InvestigationHeader } from "../components/investigation/InvestigationHeader";
import { PlanPanel } from "../components/investigation/PlanPanel";
import { Timeline } from "../components/investigation/Timeline";
import { SessionRail } from "../components/session/SessionRail";
import type { SettingsSection } from "../lib/types";
import { useRun, useSessions } from "../state";

export type WorkbenchViewProps = {
  onViewEvidence: (evidenceId?: string) => void;
  onOpenSettings: (section?: SettingsSection) => void;
};

export function WorkbenchView(props: WorkbenchViewProps) {
  const { sessions, sessionId } = useSessions();
  const { lastSubmitted } = useRun();

  const current = sessions.find((s) => s.session_id === sessionId);
  const title = current?.title || lastSubmitted || "新调查";

  return (
    <div className="wb">
      <SessionRail />
      <div className="wb-main">
        <InvestigationHeader title={title} />
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
