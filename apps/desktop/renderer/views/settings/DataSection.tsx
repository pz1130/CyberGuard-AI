import type { ReactElement } from "react";
import { DataPanel } from "../../components/DataPanel";
import { useI18n } from "../../i18n/I18nProvider";
import { useEnvironment } from "../../state";
import { useDataLifecycle } from "../../state/useDataLifecycle";
import { Card, Disclosure } from "../../ui";

export function DataSection(): ReactElement {
  const { t } = useI18n();
  const { dataRoot } = useEnvironment();
  const data = useDataLifecycle();

  return (
    <div className="settings-detail">
      <Card>
        <h3 className="settings-card-title">{t("settings.data.title")}</h3>
        <p className="settings-hint">
          data_root:{" "}
          <code className="mono mono-sm">{dataRoot || "—"}</code>
        </p>
        <Disclosure summary={t("settings.data.exportUninstall")} defaultOpen>
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
