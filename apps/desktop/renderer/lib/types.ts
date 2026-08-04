export type Tier = "readonly" | "full";

export type ThemeMode = "dark" | "light" | "system";

export type Caps = {
  tier: string;
  has_read: boolean;
  has_exec: boolean;
  has_edit: boolean;
  mock?: boolean;
  real_read?: boolean;
  real_edit?: boolean;
  real_exec?: boolean;
  sandbox_impl?: string;
  policy?: { sandbox_mode?: string };
};

export type Ev = { type: string; [k: string]: unknown };

export type SessionRow = {
  session_id: string;
  title: string;
  tier: string;
  updated_at: number;
  event_count: number;
};

export type PendingPlan = {
  plan_id: string;
  plan?: {
    summary?: string;
    steps?: string[];
    risk_level?: string;
    blast_radius?: Record<string, unknown>;
  };
  approval_type?: string;
  ui_label?: string;
  local_approve_allowed?: boolean;
  timeout_seconds?: number;
  revisedDraft?: string;
};

export type ActiveView = "workbench" | "evidence" | "settings";

declare global {
  interface Window {
    cyberguard?: {
      ping: () => Promise<Record<string, unknown> & { ok?: boolean; data_root?: string }>;
      capabilities: (tier: Tier) => Promise<Caps>;
      run: (
        task: string,
        tier: Tier,
        sessionId?: string
      ) => Promise<{ result: unknown; events: Ev[] }>;
      abort: (runId: string) => Promise<{ ok: boolean }>;
      steer: (runId: string, message: string) => Promise<{ ok: boolean }>;
      listSessions: () => Promise<{ sessions: SessionRow[] }>;
      createSession: (
        title: string,
        tier: Tier
      ) => Promise<{ session_id: string; title: string }>;
      sessionEvents: (sessionId: string) => Promise<{ events: Ev[] }>;
      planApprove?: (
        planId: string,
        revisedPlan?: string
      ) => Promise<{ ok: boolean; plan?: unknown }>;
      planReject?: (
        planId: string,
        reason?: string
      ) => Promise<{ ok: boolean }>;
      planList?: () => Promise<{ plans: unknown[] }>;
      exportEncrypted?: (passphrase: string) => Promise<{
        ok?: boolean;
        canceled?: boolean;
        method?: string;
        dest?: string;
        path?: string;
        sha256?: string;
        plaintext_sha256?: string;
        error?: string;
      }>;
      uninstallInventory?: () => Promise<{
        data_root?: string;
        will_delete?: Array<{ name: string; approx_bytes?: number }>;
        will_not_delete?: { evidence_outside_data_root?: string[] };
        manual_steps?: Array<{ item: string; action: string }>;
      }>;
      uninstallExecute?: (opts: {
        confirm: boolean;
        dryRun: boolean;
      }) => Promise<{
        ok?: boolean;
        canceled?: boolean;
        executed?: boolean;
        deleted?: string[];
        dry_run?: boolean;
      }>;
      onEvent: (handler: (ev: Ev) => void) => () => void;
      onOpenDataPanel?: (handler: () => void) => () => void;
    };
  }
}

export {};
