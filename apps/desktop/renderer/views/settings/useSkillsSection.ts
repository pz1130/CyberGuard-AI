import { useCallback, useEffect, useState } from "react";
import type { SkillPublic } from "../../lib/types";

export function useSkillsSection() {
  const api = typeof window !== "undefined" ? window.cyberguard : undefined;

  const [skills, setSkills] = useState<SkillPublic[]>([]);
  const [skillDrafts, setSkillDrafts] = useState<SkillPublic[]>([]);
  const [skillDirs, setSkillDirs] = useState<{
    approved?: string;
    drafts?: string;
    builtin?: string;
  }>({});
  const [skillMsg, setSkillMsg] = useState<string | null>(null);
  const [skillBusy, setSkillBusy] = useState(false);
  const [skillName, setSkillName] = useState("");
  const [skillDesc, setSkillDesc] = useState("");
  const [skillBody, setSkillBody] = useState("");
  const [skillVersion, setSkillVersion] = useState("1.0.0");
  const [skillMode, setSkillMode] = useState("both");
  const [skillEditSource, setSkillEditSource] = useState<
    "new" | "draft" | "approved" | "builtin"
  >("new");
  const [skillSelected, setSkillSelected] = useState<string | null>(null);

  const loadSkills = useCallback(async () => {
    if (!api?.skillsList) return;
    try {
      const r = await api.skillsList();
      setSkills(r.skills || []);
      setSkillDrafts(r.drafts || []);
      setSkillDirs(r.dirs || {});
    } catch {
      setSkills([]);
      setSkillDrafts([]);
    }
  }, [api]);

  const resetSkillEditor = useCallback(() => {
    setSkillName("");
    setSkillDesc("");
    setSkillBody(
      "# SOP · my_skill\n\n1. Step one\n2. Step two\n\nConstraints:\n- Prefer read-only investigation.\n"
    );
    setSkillVersion("1.0.0");
    setSkillMode("both");
    setSkillEditSource("new");
    setSkillSelected(null);
    setSkillMsg(null);
  }, []);

  useEffect(() => {
    void loadSkills();
  }, [loadSkills]);

  const openSkill = useCallback(
    async (name: string, source?: string) => {
      if (!api?.skillsGet) {
        setSkillMsg("skills API unavailable");
        return;
      }
      setSkillBusy(true);
      setSkillMsg(null);
      try {
        const r = await api.skillsGet(name, source);
        if (!r.ok || !r.skill) {
          setSkillMsg(r.error || "load failed");
          return;
        }
        const s = r.skill;
        setSkillName(s.name);
        setSkillDesc(s.description || "");
        setSkillBody(s.body || "");
        setSkillVersion(s.version || "1.0.0");
        setSkillMode(s.mode || "both");
        setSkillEditSource(
          (s.source as "draft" | "approved" | "builtin") || "draft"
        );
        setSkillSelected(s.name);
      } catch (e) {
        setSkillMsg(String(e));
      } finally {
        setSkillBusy(false);
      }
    },
    [api]
  );

  const onSaveSkillDraft = async () => {
    if (!api?.skillsSaveDraft) {
      setSkillMsg("skills save unavailable");
      return;
    }
    if (!skillName.trim() || !skillBody.trim()) {
      setSkillMsg("name 与 body 必填");
      return;
    }
    setSkillBusy(true);
    setSkillMsg(null);
    try {
      const r = await api.skillsSaveDraft({
        name: skillName.trim(),
        description: skillDesc.trim(),
        body: skillBody,
        version: skillVersion.trim() || "1.0.0",
        mode: skillMode,
      });
      if (!r.ok) {
        setSkillMsg(r.error || "save failed");
        return;
      }
      setSkillEditSource("draft");
      setSkillSelected(r.skill?.name || skillName.trim());
      setSkillMsg(
        `草稿已保存 · ${r.skill?.name}` +
          (r.warning ? ` · ⚠ ${r.warning}` : " · 批准后才会进 agent catalog")
      );
      await loadSkills();
    } catch (e) {
      setSkillMsg(String(e));
    } finally {
      setSkillBusy(false);
    }
  };

  const onApproveSkill = async () => {
    if (!api?.skillsApprove || !skillName.trim()) return;
    setSkillBusy(true);
    setSkillMsg(null);
    try {
      // Ensure latest editor content is in drafts first
      if (skillEditSource === "new" || skillEditSource === "draft") {
        const saved = await api.skillsSaveDraft?.({
          name: skillName.trim(),
          description: skillDesc.trim(),
          body: skillBody,
          version: skillVersion.trim() || "1.0.0",
          mode: skillMode,
        });
        if (saved && saved.ok === false) {
          setSkillMsg(saved.error || "save draft failed");
          return;
        }
      }
      const r = await api.skillsApprove(skillName.trim());
      if (!r.ok) {
        setSkillMsg(r.error || "approve failed");
        return;
      }
      setSkillEditSource("approved");
      setSkillMsg(r.message || `已批准 · ${skillName}`);
      await loadSkills();
    } catch (e) {
      setSkillMsg(String(e));
    } finally {
      setSkillBusy(false);
    }
  };

  const onDeleteSkill = async () => {
    if (!api?.skillsDelete || !skillName.trim()) return;
    const src =
      skillEditSource === "approved"
        ? "approved"
        : skillEditSource === "draft"
          ? "draft"
          : null;
    if (!src) {
      setSkillMsg("内置技能不可删除");
      return;
    }
    if (!window.confirm(`删除 ${src} skill「${skillName}」？`)) return;
    setSkillBusy(true);
    setSkillMsg(null);
    try {
      const r = await api.skillsDelete(skillName.trim(), src);
      if (!r.ok) {
        setSkillMsg(r.error || "delete failed");
        return;
      }
      setSkillMsg(`已删除 · ${skillName} (${src})`);
      resetSkillEditor();
      await loadSkills();
    } catch (e) {
      setSkillMsg(String(e));
    } finally {
      setSkillBusy(false);
    }
  };

  const onImportSkill = async () => {
    if (!api?.skillsImport || !api.pickFile) {
      setSkillMsg("import / file picker unavailable");
      return;
    }
    setSkillBusy(true);
    setSkillMsg(null);
    try {
      const picked = await api.pickFile({
        title: "Import skill Markdown",
        properties: ["openFile"],
      });
      if (!picked?.path || picked.canceled) {
        setSkillMsg("canceled");
        return;
      }
      const r = await api.skillsImport({ path: picked.path });
      if (!r.ok || !r.skill) {
        setSkillMsg(r.error || "import failed");
        return;
      }
      setSkillName(r.skill.name);
      setSkillDesc(r.skill.description || "");
      setSkillBody(r.skill.body || "");
      setSkillVersion(r.skill.version || "1.0.0");
      setSkillMode(r.skill.mode || "both");
      setSkillEditSource("draft");
      setSkillSelected(r.skill.name);
      setSkillMsg(
        `已导入为草稿 · ${r.skill.name}` +
          (r.warning ? ` · ⚠ ${r.warning}` : " · 请检查后批准")
      );
      await loadSkills();
    } catch (e) {
      setSkillMsg(String(e));
    } finally {
      setSkillBusy(false);
    }
  };

  const onForkSkill = async () => {
    if (!api?.skillsFork || !skillName.trim()) return;
    setSkillBusy(true);
    setSkillMsg(null);
    try {
      const r = await api.skillsFork(skillName.trim());
      if (!r.ok || !r.skill) {
        setSkillMsg(r.error || "fork failed");
        return;
      }
      setSkillName(r.skill.name);
      setSkillDesc(r.skill.description || "");
      setSkillBody(r.skill.body || "");
      setSkillVersion(r.skill.version || "1.0.0");
      setSkillMode(r.skill.mode || "both");
      setSkillEditSource("draft");
      setSkillSelected(r.skill.name);
      setSkillMsg(
        `已复制到草稿 · ${r.skill.name}` +
          (r.warning ? ` · ⚠ ${r.warning}` : " · 改名后批准可覆盖流程")
      );
      await loadSkills();
    } catch (e) {
      setSkillMsg(String(e));
    } finally {
      setSkillBusy(false);
    }
  };

  const onRevealSkillDir = async (which: "approved" | "drafts") => {
    const p = which === "approved" ? skillDirs.approved : skillDirs.drafts;
    if (!p || !api?.showItemInFolder) {
      setSkillMsg("path unavailable");
      return;
    }
    try {
      await api.showItemInFolder(p);
    } catch (e) {
      setSkillMsg(String(e));
    }
  };

  return {
    skills,
    skillDrafts,
    skillMsg,
    skillBusy,
    skillName,
    setSkillName,
    skillDesc,
    setSkillDesc,
    skillBody,
    setSkillBody,
    skillVersion,
    setSkillVersion,
    skillMode,
    setSkillMode,
    skillEditSource,
    skillSelected,
    resetSkillEditor,
    openSkill,
    onSaveSkillDraft,
    onApproveSkill,
    onDeleteSkill,
    onImportSkill,
    onForkSkill,
    onRevealSkillDir,
  };
}
