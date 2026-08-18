import type { ReactElement } from "react";
import { DataPanel } from "../../components/DataPanel";
import { useDataLifecycle } from "../../state/useDataLifecycle";

export type DataSectionProps = {
  dataRoot: string;
};

export function DataSection({ dataRoot }: DataSectionProps): ReactElement {
  const data = useDataLifecycle();

  return (
    <div className="settings-detail">
      <div className="settings-card">
        <h3>数据与安全</h3>
        <p className="data-hint">
          data_root:{" "}
          <code className="mono mono-sm">{dataRoot || "—"}</code>
        </p>
        <DataPanel
          open={true}
          onToggle={() => {}}
          exportPass={data.exportPass}
          onExportPass={data.setExportPass}
          exportBusy={data.exportBusy}
          exportMsg={data.exportMsg}
          onExport={() => void data.runExport()}
          exportAvailable={data.exportAvailable}
          uninstallBusy={data.uninstallBusy}
          uninstallPreview={data.uninstallPreview}
          onInventory={() => void data.inventory()}
          onDryRun={() => void data.dryRun()}
          onExecute={() => void data.execute()}
        />
      </div>
    </div>
  );
}
