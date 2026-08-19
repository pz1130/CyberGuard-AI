import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useI18n } from "../i18n/I18nProvider";
import type { Ev, PendingPlan } from "../lib/types";

export type PlanContextValue = {
  pendingPlan: PendingPlan | null;
  planEdit: string;
  setPlanEdit: (v: string) => void;
  approve: () => Promise<void>;
  reject: () => Promise<void>;
  ingest: (ev: Ev) => void;
};

const PlanContext = createContext<PlanContextValue | null>(null);

export type PlanProviderProps = {
  children: ReactNode;
  /** 审批调用失败时把错误交回 run 域的时间线 */
  onError: (message: string) => void;
};

export function PlanProvider({ children, onError }: PlanProviderProps) {
  const { t } = useI18n();
  const [pendingPlan, setPendingPlan] = useState<PendingPlan | null>(null);
  const [planEdit, setPlanEdit] = useState("");
  const api = typeof window !== "undefined" ? window.cyberguard : undefined;

  const ingest = useCallback(
    (ev: Ev) => {
      if (
        (ev.type === "plan_ready" || ev.type === "privilege_required") &&
        typeof ev.plan_id === "string"
      ) {
        const plan = (ev.plan || {}) as PendingPlan["plan"];
        // approval_type 必须原样透传：standalone 下为 self，不得与职责分离审批混同（INV-06 / INV-38）
        // 标题从 approval_type 映射；sidecar ui_label 恒为中文，仅作未知类型兜底
        const approvalType = String(ev.approval_type || "self");
        const base =
          approvalType === "self"
            ? t("plan.selfApprove")
            : String(ev.ui_label || t("plan.selfApprove"));
        setPendingPlan({
          plan_id: String(ev.plan_id),
          plan,
          approval_type: approvalType,
          ui_label:
            ev.type === "privilege_required"
              ? t("plan.privilegeLabel", { base })
              : base,
          local_approve_allowed: ev.local_approve_allowed !== false,
          timeout_seconds:
            typeof ev.timeout_seconds === "number"
              ? ev.timeout_seconds
              : undefined,
        });
        setPlanEdit(String(plan?.summary || ""));
        return;
      }
      if (
        ev.type === "plan_approved" ||
        ev.type === "plan_rejected" ||
        ev.type === "privilege_decided"
      ) {
        setPendingPlan(null);
      }
    },
    [t]
  );

  const approve = useCallback(async () => {
    if (!api?.planApprove || !pendingPlan) return;
    if (!pendingPlan.local_approve_allowed) return;
    const trimmed = planEdit.trim();
    const revised =
      trimmed && trimmed !== (pendingPlan.plan?.summary || "")
        ? trimmed
        : undefined;
    try {
      await api.planApprove(pendingPlan.plan_id, revised);
    } catch (e) {
      onError(`plan approve failed: ${e}`);
    }
  }, [api, pendingPlan, planEdit, onError]);

  const reject = useCallback(async () => {
    if (!api?.planReject || !pendingPlan) return;
    try {
      await api.planReject(pendingPlan.plan_id, "rejected_by_user");
    } catch (e) {
      onError(`plan reject failed: ${e}`);
    }
  }, [api, pendingPlan, onError]);

  const value = useMemo<PlanContextValue>(
    () => ({ pendingPlan, planEdit, setPlanEdit, approve, reject, ingest }),
    [pendingPlan, planEdit, approve, reject, ingest]
  );

  return <PlanContext.Provider value={value}>{children}</PlanContext.Provider>;
}

export function usePlan(): PlanContextValue {
  const ctx = useContext(PlanContext);
  if (!ctx) throw new Error("usePlan must be used within PlanProvider");
  return ctx;
}
