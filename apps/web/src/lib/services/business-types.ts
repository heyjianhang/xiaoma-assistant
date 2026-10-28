export type BusinessValue = string | number | boolean | null | undefined;
export type BusinessRow = Record<string, BusinessValue>;

export interface BusinessColumn {
  name: string;
  label: string;
  type: string;
  description: string;
  constraints: string;
}

export interface BusinessTablePreview {
  name: string;
  title: string;
  description: string;
  primaryKey: string;
  rowCount: number;
  columns: BusinessColumn[];
  previewColumns: string[];
  rows: BusinessRow[];
}

const labels: Record<string, string> = {
  created: "待支付", cancelled: "已取消", paid: "待发货", shipped: "已发货", fulfilled: "已签收",
  requested: "待验收", accepted: "待到账", completed: "退款成功", rejected: "已驳回",
  wallet: "电子钱包", bank: "银行卡", individual: "个人", business: "企业采购",
  approved: "已准入", reviewing: "审核中", refund_only: "仅退款", return_and_refund: "退货退款",
  quality: "品质问题", damage: "破损", wrong_item: "错发", customer_choice: "客户意愿",
};
const currency = new Intl.NumberFormat("zh-CN", { style: "currency", currency: "CNY" });
const datetime = new Intl.DateTimeFormat("zh-CN", {
  timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit",
  hour: "2-digit", minute: "2-digit", hourCycle: "h23",
});

export function formatBusinessValue(column: BusinessColumn, value: BusinessValue): string {
  if (value === null || value === undefined) return "—";
  if (column.type === "boolean") return value ? "是" : "否";
  if (column.type.startsWith("numeric")) return currency.format(Number(value));
  if (column.type === "timestamptz") return datetime.format(new Date(String(value)));
  return labels[String(value)] ?? String(value);
}
