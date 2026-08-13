import "../components/workbench/WorkbenchLayout.css";
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
        {/* 时间线与 composer 在 Task 14 / 15 填入 */}
      </div>
      <div className="wb-rail">
        {/* 右栏在 Task 13 填入 */}
      </div>
    </div>
  );
}
