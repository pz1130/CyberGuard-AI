export type SampleTask = {
  id: string;
  /** 空态卡片标题 */
  labelKey: string;
  /** 卡片上的一句说明 */
  blurbKey: string;
  /** 填进 composer 的完整任务描述——送模型的提示词，跟随回答语言 */
  textKey: string;
};

export const SAMPLE_TASKS: SampleTask[] = [
  {
    id: "triage",
    labelKey: "sample.triage.label",
    blurbKey: "sample.triage.blurb",
    textKey: "sample.triage.text",
  },
  {
    id: "cve",
    labelKey: "sample.cve.label",
    blurbKey: "sample.cve.blurb",
    textKey: "sample.cve.text",
  },
  {
    id: "localAlerts",
    labelKey: "sample.localAlerts.label",
    blurbKey: "sample.localAlerts.blurb",
    textKey: "sample.localAlerts.text",
  },
];
