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

/**
 * approval_type → 词条。取值集合的事实源在 sidecar/plan_mode.py，
 * tests/test_desktop_approval_types.py 钉住它，新增类型时那条测试会红。
 */
const APPROVAL_LABEL_KEYS: Record<string, string> = {
  self: "plan.selfApprove",
  segregation: "plan.segregationApprove",
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
        const approvalType = String(ev.approval_type || "self");
        const labelKey = APPROVAL_LABEL_KEYS[approvalType];
        // 未知类型才回落 sidecar 的成品文案（恒中文）。**不回落到自批准** ——
        // 把未知审批类型标成自批准是 INV-06 意义上的错标，宁可显示中性的「计划待批」。
        const base = labelKey
          ? t(labelKey)
          : String(ev.ui_label || t("plan.pending"));
        // dev 期日志用英文：no-hardcoded.test.ts 扫非注释行的中文字面量
        if (!labelKey && import.meta.env?.DEV) {
          console.warn(
            `[plan] unknown approval_type: ${approvalType} — sidecar added a new ` +
              "type; sync APPROVAL_LABEL_KEYS and both locale files " +
              "(11-OPEN-QUESTIONS section K.1)"
          );
        }
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
