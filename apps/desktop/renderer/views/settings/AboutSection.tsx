import type { ReactElement } from "react";

export function AboutSection(): ReactElement {
  return (
    <div className="settings-detail">
      <div className="settings-card">
        <h3>关于</h3>
        <p>
          CyberGuard Desktop · development build ·{" "}
          <strong>not notarized · not for distribution</strong>.
        </p>
        <p className="muted-copy mt-10">
          Plan Mode 为自批准（approval_type=self），超时=拒绝。本地哈希链 ≠
          WORM。单兵工具，不做 Web 21 Tab 后台。
        </p>
      </div>
    </div>
  );
}
