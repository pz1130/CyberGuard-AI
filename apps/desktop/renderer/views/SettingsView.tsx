import { SettingsShell, type SettingsViewProps } from "./settings/SettingsShell";

export type { SettingsViewProps };

export function SettingsView(props: SettingsViewProps) {
  return <SettingsShell {...props} />;
}
