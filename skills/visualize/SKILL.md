---
{
  "name": "visualize",
  "description": "将已执行结果显示为表格、柱状图、折线图或指标卡。",
  "metadata": {
    "xiaoma-display-name": "查询结果可视化",
    "xiaoma-required-tools": "execute_readonly_sql render_chart"
  }
}
---

只能使用本轮 execute_readonly_sql 返回的 result_id。
提交 view、字段名与标题，工具按实际结果生成数据；
不要自行重新编造rows。
分类比较用bar，按时间趋势用line，单项数值用metrics，明细用table。
分类图的SQL结果只含各分类，不将合计行作为一个分类柱；合计数在自然语言中说明。
空结果、截断、统计范围和样本限制需要保留。
