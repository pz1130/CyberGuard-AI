/**
 * electron-builder afterSign hook (M7).
 *
 * Behaviour:
 * - If APPLE_ID + APPLE_APP_SPECIFIC_PASSWORD + APPLE_TEAM_ID are set and
 *   CSC_IDENTITY / signed app exists → submit via notarytool (when available).
 * - Otherwise → **dry-run**: log what would be notarized and exit 0.
 *
 * Never pretends notarization succeeded when credentials are missing (INV-38).
 */
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { execFileSync } = require("node:child_process");

/**
 * @param {{ appOutDir: string, packager: { appInfo: { productFilename: string } } }} context
 */
exports.default = async function notarizeHook(context) {
  const { electronPlatformName, appOutDir } = context;
  if (electronPlatformName !== "darwin") {
    console.log("[notarize] skip non-mac platform");
    return;
  }

  const appName = context.packager.appInfo.productFilename;
  const appPath = path.join(appOutDir, `${appName}.app`);
  const hasApp = fs.existsSync(appPath);

  const appleId = process.env.APPLE_ID || "";
  const applePass = process.env.APPLE_APP_SPECIFIC_PASSWORD || "";
  const teamId = process.env.APPLE_TEAM_ID || "";
  const forceDry = process.env.CYBERGUARD_NOTARIZE_DRY_RUN === "1";
  const ready = Boolean(appleId && applePass && teamId) && !forceDry;

  console.log("[notarize] appPath=", appPath, "exists=", hasApp);
  console.log(
    "[notarize] credentials:",
    ready ? "present" : "missing or dry-run forced"
  );

  if (!ready) {
    console.log(
      "[notarize] DRY-RUN — not submitting to Apple. " +
        "Set APPLE_ID, APPLE_APP_SPECIFIC_PASSWORD, APPLE_TEAM_ID for real notarization. " +
        "This build is NOT notarized (INV-38: do not claim otherwise)."
    );
    return;
  }

  if (!hasApp) {
    throw new Error(`[notarize] app not found at ${appPath}`);
  }

  // Prefer notarytool (Xcode 13+)
  try {
    execFileSync("xcrun", ["notarytool", "--help"], { stdio: "ignore" });
  } catch {
    console.warn(
      "[notarize] xcrun notarytool unavailable — dry-run fallback (credentials present but tool missing)"
    );
    return;
  }

  const zipPath = `${appPath}.zip`;
  console.log("[notarize] zipping for submit…");
  execFileSync("ditto", ["-c", "-k", "--keepParent", appPath, zipPath], {
    stdio: "inherit",
  });

  console.log("[notarize] submitting…");
  execFileSync(
    "xcrun",
    [
      "notarytool",
      "submit",
      zipPath,
      "--apple-id",
      appleId,
      "--password",
      applePass,
      "--team-id",
      teamId,
      "--wait",
    ],
    { stdio: "inherit" }
  );

  console.log("[notarize] stapling…");
  execFileSync("xcrun", ["stapler", "staple", appPath], { stdio: "inherit" });
  console.log("[notarize] done");
};
