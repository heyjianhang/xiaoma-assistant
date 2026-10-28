---
{
  "name": "evidence-review",
  "description": "对齐文档与查询的口径、时间和版本，输出冲突、缺失、小样本或执行偏差。",
  "metadata": {
    "xiaoma-display-name": "跨来源核对与异常解释",
    "xiaoma-required-tools": "search_knowledge execute_readonly_sql present_evidence_review"
  }
}
---

先取得双方真实证据，区分规范要求与事实陈述。
核对时间窗口、地区、品类、支付订单cohort、退款截止、粒度、去重、单位和政策版本；
存在未对齐项就写不可直接比较。
政策时限与实际超时是执行偏差，不能称政策与数据自相矛盾。
事实同口径不同才是conflict，原因未知要说明。
未定义指标应澄清，不能偷换成已有退款率。
小样本同时展示分子分母和比例，不能给稳定排名。
使用 present_evidence_review，引用本轮实际证据ID和result_id；
不能另造数值。
最后仍须给出自然语言回答。
