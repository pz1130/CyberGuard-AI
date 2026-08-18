import type { ReactElement } from "react";
import { useEnvironment } from "../../state";
import { Card } from "../../ui";

export function AboutSection(): ReactElement {
  const { providerMode, dataRoot } = useEnvironment();

  return (
    <div className="settings-detail">
      <Card>
        <h3 className="settings-card-title">关于</h3>
        <p className="settings-hint">
          CyberGuard Desktop · development build ·{" "}
          <strong>not notarized · not for distribution</strong>.
        </p>
        <p className="settings-hint">
          LLM 模式：<strong>{providerMode || "—"}</strong>
          {" · "}
          data_root：
          <code className="mono mono-sm">{dataRoot || "—"}</code>
        </p>
        <p className="settings-hint">
          Plan Mode 为自批准（approval_type=self），超时=拒绝。本地哈希链 ≠
          WORM。单兵工具，不做 Web 21 Tab 后台。
        </p>
      </Card>
    </div>
  );
}
