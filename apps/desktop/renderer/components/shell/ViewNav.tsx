import type { ActiveView } from "../../lib/types";
import { useI18n } from "../../i18n/I18nProvider";
import { ListRow } from "../../ui";

const VIEWS: Array<{ id: ActiveView; labelKey: string }> = [
  { id: "workbench", labelKey: "nav.workbench" },
  { id: "evidence", labelKey: "nav.evidence" },
  { id: "settings", labelKey: "nav.settings" },
];

export type ViewNavProps = {
  activeView: ActiveView;
  onNavigate: (v: ActiveView) => void;
};

export function ViewNav({ activeView, onNavigate }: ViewNavProps) {
  const { t } = useI18n();

  return (
    <nav className="sidebar-nav" aria-label={t("nav.main.aria")}>
      {VIEWS.map((v) => (
        <ListRow
          key={v.id}
          variant="nav"
          active={activeView === v.id}
          title={t(v.labelKey)}
          onClick={() => onNavigate(v.id)}
        />
      ))}
    </nav>
  );
}
