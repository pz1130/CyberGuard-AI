export type SampleTask = {
  id: string;
  label: string;
  /** 填进 composer 的完整任务描述 */
  text: string;
  /** 空态卡片上的一句说明 */
  blurb: string;
};

export const SAMPLE_TASKS: SampleTask[] = [
  {
    id: "triage",
    label: "告警分诊",
    text: "分诊当前 high/critical 告警，给出优先级与建议动作",
    blurb: "拉取告警、按影响面排序、给出处置建议",
  },
  {
    id: "cve",
    label: "CVE 影响面",
    text: "评估 CVE-2024-3094 在本机环境的影响面与缓解措施",
    blurb: "对照本机组件版本，判断是否受影响",
  },
  {
    id: "alerts",
    label: "读本地告警",
    text: "读取本地告警数据源，总结最近 24 小时的异常模式",
    blurb: "从已接入的数据源汇总近期异常",
  },
];
