import type { ReactElement } from "react";
import { DataPanel } from "../../components/DataPanel";
import { useEnvironment } from "../../state";
import { useDataLifecycle } from "../../state/useDataLifecycle";
import { Card, Disclosure } from "../../ui";

export function DataSection(): ReactElement {
  const { dataRoot } = useEnvironment();
  const data = useDataLifecycle();

  return (
    <div className="settings-detail">
      <Card>
        <h3 className="settings-card-title">数据与安全</h3>
        <p className="settings-hint">
          data_root:{" "}
          <code className="mono mono-sm">{dataRoot || "—"}</code>
        </p>
        <Disclosure summary="导出 / 卸载" defaultOpen>
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
        </Disclosure>
      </Card>
    </div>
  );
}
