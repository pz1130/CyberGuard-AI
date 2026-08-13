import { createContext, useContext, useMemo, type ReactNode } from "react";
import { useExport, type ExportSlice } from "./useExport";
import { useUninstall, type UninstallSlice } from "./useUninstall";

/**
 * 数据生命周期域 —— 只被设置页消费，调查页不感知其存在。
 *
 * 导出与卸载是两件独立的事，各自的状态机在 useExport / useUninstall 里，
 * 本文件只负责把它们合成一个 context。
 */
export type DataLifecycleValue = ExportSlice & UninstallSlice;

const DataLifecycleContext = createContext<DataLifecycleValue | null>(null);

export function DataLifecycleProvider({
  children,
  onUninstalled,
}: {
  children: ReactNode;
  /** 真实卸载执行成功后清空会话状态 */
  onUninstalled?: () => void;
}) {
  const exportSlice = useExport();
  const uninstallSlice = useUninstall(onUninstalled);

  const value = useMemo<DataLifecycleValue>(
    () => ({ ...exportSlice, ...uninstallSlice }),
    [exportSlice, uninstallSlice]
  );

  return (
    <DataLifecycleContext.Provider value={value}>
      {children}
    </DataLifecycleContext.Provider>
  );
}

export function useDataLifecycle(): DataLifecycleValue {
  const ctx = useContext(DataLifecycleContext);
  if (!ctx)
    throw new Error(
      "useDataLifecycle must be used within DataLifecycleProvider"
    );
  return ctx;
}
