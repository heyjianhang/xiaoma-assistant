import type { QuerySample, ReviewPresentation } from "@/features/chat/presentation-types";
import type { DocumentExcerpt } from "./review-evidence-dialog";
import snapshots from "./fixtures/review-walkthrough.json";

export type ReviewScenario = {
  id: string;
  label: string;
  question: string;
  title: string;
  evidence: { label: string; value: string; detail: string }[];
  scope: { label: string; value: string }[];
  steps: string[];
  sources: DocumentExcerpt[];
  query?: QuerySample;
  review?: ReviewPresentation;
};

const evidence = snapshots.sources;
const conflict = snapshots.queries.conflict.rows[0];
const small = snapshots.queries.small.rows[0];
const version = snapshots.queries.version.rows[0];
const missing = snapshots.queries.missing.rows[0];
const gap = Number(conflict.refund_rate_percent) - snapshots.reported_rate;
const review = (kind: ReviewPresentation["kind"], title: string, verdict: ReviewPresentation["verdict"], summary: string, checks: string[], limitations: string[]): ReviewPresentation => ({
  type: "evidence_review", kind, title, verdict, summary, facts: [], checks, limitations, sources: [],
});

export const reviewScenarios: ReviewScenario[] = [
  {
    id: "conflict", label: "月报冲突", question: snapshots.questions.A06, title: "先确认口径一致，再标记事实冲突",
    evidence: [
      { label: "文档 · 运营月报", value: `${snapshots.reported_rate}%`, detail: "REP-T1 / REP-2.1：华东生鲜果蔬订单退款率。" },
      { label: "数据库 · 去重订单", value: `${conflict.refund_rate_percent}%`, detail: `${conflict.refunded_orders} 个成功退款订单 / ${conflict.paid_orders} 个支付订单。` },
    ],
    scope: [{ label: "支付范围", value: "2026 年 9 月，左闭右开" }, { label: "退款截止", value: "10 月 1 日前，不含该时刻" }, { label: "地区 / 品类", value: "华东 / 生鲜果蔬成交快照" }, { label: "粒度 / 单位", value: "订单去重 / 百分比" }],
    steps: ["同时读取月报、指标定义与实际数据，核对时间和业务范围。", `数据库有 ${conflict.refund_sheets} 张成功退款单，但只对应 ${conflict.refunded_orders} 个去重退款订单。`, `同口径仍相差 ${gap} 个百分点，保留双方依据，原因需进一步核实。`],
    sources: [evidence.monthly, evidence.metrics], query: snapshots.queries.conflict,
    review: review("conflict", "月报与业务数据存在差异", "存在差异", `月报为 ${snapshots.reported_rate}%，实际数据为 ${conflict.refund_rate_percent}%，相差 ${gap} 个百分点。`, ["支付队列、退款截止、地区与品类快照一致。", "分子与分母均按订单去重，不用退款单数代替。", "同时保留月报条款和已执行 SQL，便于复核。"], ["目前只能确认数值不一致；不能无证据断言录入错误、延迟或某一来源必然正确。"]),
  },
  {
    id: "version", label: "版本适用", question: snapshots.questions.A12, title: "跨生效日完成，仍按申请时间选版本",
    evidence: [
      { label: "文档 · 旧版电子钱包", value: "48 自然小时", detail: "旧版适用于 2026-09-01 前提交的申请。" },
      { label: "数据库 · 实际到账时长", value: `${version.elapsed_hours} 小时`, detail: "验收后到成功到账的时长，等于旧版上限。" },
    ],
    scope: [{ label: "版本依据", value: "applied_at 申请时间" }, { label: "新版生效", value: "2026-09-01 00:00，北京时间" }, { label: "计时起点", value: "accepted_at 验收通过" }, { label: "边界规则", value: "等于期限按时，大于才超时" }],
    steps: [`申请于 ${version.applied_at} 提交，属于旧版 1.0 的受理范围。`, "验收、完成发生在新版生效后，不改变提交时适用版本。", `实际 ${version.elapsed_hours} 小时等于旧版上限，不能回溯套用新版 24 小时。`],
    sources: [evidence.old_policy, evidence.new_policy], query: snapshots.queries.version,
  },
  {
    id: "missing", label: "缺失字段", question: snapshots.questions.A04, title: "关键时间为空，就保留无法判定的边界",
    evidence: [
      { label: "文档 · 计时依据", value: "验收 → 到账", detail: "AS2-3.1 / AS2-3.3：不允许用其他业务时间替代验收。" },
      { label: "数据库 · accepted_at", value: "NULL", detail: `订单 ${missing.order_id} 已退款成功，但缺少验收时间。` },
    ],
    scope: [{ label: "申请时间", value: String(missing.applied_at) }, { label: "验收时间", value: "NULL，原始缺失" }, { label: "成功到账", value: String(missing.completed_at) }, { label: "时间单位", value: "北京时间 / 自然小时" }],
    steps: ["确认申请属于新版、渠道为电子钱包，适用验收后 24 自然小时。", "检查实际记录：验收时间为空，因此实际到账时长也为 NULL。", "保留缺失记录，要求依据原始凭证补录，不能从现有时间猜测。"],
    sources: [evidence.new_policy], query: snapshots.queries.missing,
    review: review("execution_deviation", "缺少验收时间，无法判断是否超时", "不可直接比较", "渠道时限已明确，但缺少计时起点，不能与实际到账耗时比较。", ["退款成功状态与到账时间存在。", "验收时间 accepted_at 为 NULL。", "当前缺少按制度核验时长所需的完整时间。"], ["申请到到账的 72 小时不是验收到到账时长，不能据此判超时或判按时。"]),
  },
  {
    id: "small", label: "样本边界", question: snapshots.questions.A07, title: "比例可以是真实的，结论仍需受样本约束",
    evidence: [
      { label: "文档 · 解读纪律", value: "分子 + 分母", detail: "MET-T1：比例展示必须保留样本量与解读边界。" },
      { label: "数据库 · 西北滋补礼盒", value: `${small.refund_rate_percent}%`, detail: `${small.refunded_orders} 个成功退款订单 / ${small.paid_orders} 个支付订单。` },
    ],
    scope: [{ label: "支付范围", value: "2026 年 9 月" }, { label: "观察范围", value: "西北 / 滋补礼盒" }, { label: "统计粒度", value: "支付与退款订单均去重" }, { label: "样本量", value: `只有 ${small.paid_orders} 个支付订单` }],
    steps: ["实际查询分子、分母，同时展示比例。", "将高比例与样本量一起解释，不把 3 单推广为全品类结论。", "需要扩大观察范围，并补充批次、品质与供应商证据再作判断。"],
    sources: [evidence.metrics, evidence.display], query: snapshots.queries.small,
    review: review("small_sample", "100% 来自 3 个订单，样本不足", "样本不足", "这 3 个支付订单均发生成功退款，但不足以证明该品类普遍存在问题。", ["查询保留 3 / 3 = 100% 的分子、分母。", "地区、品类和时间范围保持明确。", "比例事实与品质、因果判断分别说明。"], ["不能据此直接给出全品类品质结论或判定供应商责任。"]),
  },
  {
    id: "clarify", label: "口径澄清", question: snapshots.questions.A05, title: "指标尚未定义，先澄清再计算",
    evidence: [
      { label: "文档 · 当前指标说明", value: "未定义", detail: "MET-4.2 未定义“售后异常率”，不能自行拼接公式。" },
      { label: "需要确认", value: "事件与分母", detail: "异常是什么、统计哪些对象、怎样去重，以及时间范围。" },
    ],
    scope: [{ label: "异常事件", value: "需要用户确认" }, { label: "分母范围", value: "需要用户确认" }, { label: "已知范围", value: "2026 年 9 月" }, { label: "当前动作", value: "不命名、不计算未知指标" }],
    steps: ["先查指标说明，确认用户所说的指标有没有现成定义。", "列出缺失的定义，提供已有指标作为明确标注的候选。", "等待用户选择或补充定义，再开展相应查询。"],
    sources: [evidence.boundaries],
  },
];

export const zeroDenominatorQuery: QuerySample = snapshots.queries.zero;
export const zeroDenominatorSources: DocumentExcerpt[] = [evidence.metrics];
