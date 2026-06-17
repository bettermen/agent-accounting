"""
可视化仪表盘生成器
生成交互式HTML报告，包含：票据分析、会计分录、报表、报税、风险预警
"""

import json
from datetime import date, datetime
from typing import Optional

from core.models import (
    AccountBalance, Company, Invoice, InvoiceType, Voucher, RiskAlert,
    Direction,
)


class DashboardGenerator:
    """仪表盘HTML生成器"""

    TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI代理记账看板 - {company_name}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;background:#f0f2f5;color:#1a1a2e}}
.header{{background:linear-gradient(135deg,#1e3c72,#2a5298);color:#fff;padding:24px 32px;display:flex;justify-content:space-between;align-items:center}}
.header h1{{font-size:24px;font-weight:600}}
.header .meta{{font-size:13px;opacity:0.85}}
.container{{max-width:1400px;margin:0 auto;padding:24px}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px;margin-bottom:24px}}
.card{{background:#fff;border-radius:12px;padding:20px;box-shadow:0 2px 8px rgba(0,0,0,0.06)}}
.card .label{{font-size:12px;color:#8c8c8c;text-transform:uppercase;margin-bottom:8px}}
.card .value{{font-size:28px;font-weight:700;color:#1a1a2e}}
.card .sub{{font-size:12px;color:#52c41a;margin-top:4px}}
.card.warn .value{{color:#faad14}}
.card.danger .value{{color:#ff4d4f}}
.section{{background:#fff;border-radius:12px;padding:24px;margin-bottom:20px;box-shadow:0 2px 8px rgba(0,0,0,0.06)}}
.section h2{{font-size:18px;font-weight:600;margin-bottom:16px;padding-bottom:12px;border-bottom:2px solid #f0f2f5;display:flex;align-items:center;gap:8px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{background:#fafafa;padding:10px 12px;text-align:left;font-weight:600;color:#595959;border-bottom:1px solid #f0f0f0}}
td{{padding:8px 12px;border-bottom:1px solid #f5f5f5}}
tr:hover{{background:#fafafa}}
.badge{{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:500}}
.badge-green{{background:#f6ffed;color:#52c41a;border:1px solid #b7eb8f}}
.badge-yellow{{background:#fffbe6;color:#faad14;border:1px solid #ffe58f}}
.badge-red{{background:#fff2f0;color:#ff4d4f;border:1px solid #ffccc7}}
.badge-blue{{background:#e6f7ff;color:#1890ff;border:1px solid #91d5ff}}
.grid-2{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}
.chart-wrap{{position:relative;height:300px}}
.alerts{{margin-top:16px}}
.alert{{padding:12px 16px;border-radius:8px;margin-bottom:8px;display:flex;align-items:flex-start;gap:10px;font-size:13px}}
.alert.high{{background:#fff2f0;border-left:4px solid #ff4d4f}}
.alert.medium{{background:#fffbe6;border-left:4px solid #faad14}}
.alert.low{{background:#f6ffed;border-left:4px solid #52c41a}}
.alert .icon{{font-size:18px;flex-shrink:0}}
.flow-steps{{display:flex;gap:0;margin:24px 0;flex-wrap:wrap}}
.flow-step{{flex:1;min-width:150px;text-align:center;position:relative;padding:16px;background:#f6f8fa;border-radius:8px;margin:4px}}
.flow-step .num{{width:32px;height:32px;border-radius:50%;background:#2a5298;color:#fff;display:inline-flex;align-items:center;justify-content:center;font-weight:700;font-size:14px;margin-bottom:8px}}
.flow-step .label{{font-size:12px;color:#595959;font-weight:500}}
.flow-step .detail{{font-size:11px;color:#8c8c8c;margin-top:4px}}
.arrow{{display:flex;align-items:center;color:#d9d9d9;font-size:20px;padding:0 4px}}
@media(max-width:768px){{.grid-2{{grid-template-columns:1fr}}.flow-steps{{flex-direction:column}}}}
</style>
</head>
<body>
<div class="header">
  <div>
    <h1>🏢 AI代理记账智能看板</h1>
    <div class="meta">{company_name} | {period} | 数据更新时间：{update_time}</div>
  </div>
</div>

<div class="container">

<!-- KPI卡片 -->
<div class="cards">
  <div class="card">
    <div class="label">本月凭证</div>
    <div class="value">{total_vouchers}</div>
    <div class="sub">已审核 {reviewed_vouchers} 张</div>
  </div>
  <div class="card">
    <div class="label">本月票据</div>
    <div class="value">{total_invoices}</div>
    <div class="sub">AI自动识别</div>
  </div>
  <div class="card">
    <div class="label">税负总额</div>
    <div class="value">¥{total_tax:,.2f}</div>
    <div class="sub">增值税 + 所得税</div>
  </div>
  <div class="card {risk_card_class}">
    <div class="label">风险预警</div>
    <div class="value">{risk_count}</div>
    <div class="sub">{risk_sub}</div>
  </div>
  <div class="card">
    <div class="label">自动化率</div>
    <div class="value">{automation_rate}%</div>
    <div class="sub">AI处理比例</div>
  </div>
</div>

<!-- 自动化工作流 -->
<div class="section">
  <h2>⚡ AI自动化工作流</h2>
  <div class="flow-steps">
    {flow_steps}
  </div>
  {ocr_status_html}
</div>

<!-- 票据分析 + 分录 -->
<div class="grid-2">
  <div class="section">
    <h2>📄 票据分类统计</h2>
    <div class="chart-wrap">
      <canvas id="invoiceChart"></canvas>
    </div>
  </div>
  <div class="section">
    <h2>💰 费用构成分析</h2>
    <div class="chart-wrap">
      <canvas id="expenseChart"></canvas>
    </div>
  </div>
</div>

<!-- 票据明细表 -->
<div class="section">
  <h2>📋 票据明细</h2>
  <table>
    <thead>
      <tr><th>#</th><th>类型</th><th>发票代码/号码</th><th>日期</th><th>销售方</th><th>金额</th><th>税额</th><th>置信度</th></tr>
    </thead>
    <tbody>
      {invoice_rows}
    </tbody>
  </table>
</div>

<!-- 凭证列表 -->
<div class="section">
  <h2>📝 记账凭证</h2>
  <table>
    <thead>
      <tr><th>凭证号</th><th>日期</th><th>分录数</th><th>借方合计</th><th>贷方合计</th><th>附件</th><th>状态</th></tr>
    </thead>
    <tbody>
      {voucher_rows}
    </tbody>
  </table>
</div>

<!-- 分录详情（第一张凭证为例） -->
{voucher_detail_section}

<!-- 报表 -->
<div class="grid-2">
  <div class="section">
    <h2>📊 资产负债表（简表）</h2>
    <table>
      <thead><tr><th>科目</th><th style="text-align:right">金额</th></tr></thead>
      <tbody>
        {balance_sheet_rows}
      </tbody>
      <tfoot>
        <tr style="font-weight:700;background:#fafafa">
          <td>资产总计</td><td style="text-align:right">¥{total_assets:,.2f}</td>
        </tr>
        <tr style="font-weight:700;background:#fafafa">
          <td>负债和所有者权益总计</td><td style="text-align:right">¥{total_liab_equity:,.2f}</td>
        </tr>
      </tfoot>
    </table>
  </div>
  <div class="section">
    <h2>📈 利润表</h2>
    <table>
      {income_statement_rows}
    </table>
  </div>
</div>

<!-- 报税 -->
<div class="section">
  <h2>🧾 本月报税数据</h2>
  <table>
    <thead>
      <tr><th>税种</th><th>计税依据</th><th>税率</th><th>应纳税额</th><th>截止日期</th><th>状态</th></tr>
    </thead>
    <tbody>
      {tax_rows}
    </tbody>
  </table>
</div>

<!-- 金税四期申报 -->
{filing_section}

<!-- 风险预警 -->
<div class="section">
  <h2>⚠️ 风险预警</h2>
  {risk_alerts_html}
</div>

</div>

<script>
// 票据类型饼图
new Chart(document.getElementById('invoiceChart'), {{
  type: 'doughnut',
  data: {{
    labels: {invoice_labels},
    datasets: [{{
      data: {invoice_data},
      backgroundColor: ['#1890ff','#52c41a','#faad14','#722ed1','#eb2f96','#13c2c2','#f5222d','#fa8c16','#2f54eb','#a0d911'],
    }}]
  }},
  options: {{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{position:'bottom',labels:{{padding:20,font:{{size:11}}}}}}}}}}
}});

// 费用构成柱状图
new Chart(document.getElementById('expenseChart'), {{
  type: 'bar',
  data: {{
    labels: {expense_labels},
    datasets: [{{
      label: '金额 (¥)',
      data: {expense_data},
      backgroundColor: ['#1890ff','#52c41a','#faad14','#722ed1','#eb2f96','#13c2c2','#f5222d','#fa8c16'],
      borderRadius: 6,
    }}]
  }},
  options: {{
    responsive:true,maintainAspectRatio:false,
    plugins:{{legend:{{display:false}}}},
    scales:{{y:{{beginAtZero:true}}}}
  }}
}});
</script>
</body>
</html>"""

    @classmethod
    def generate(cls, company: Company, invoices: list[Invoice],
                 vouchers: list[Voucher], tax_data: dict,
                 income_data: dict, balance_data: dict,
                 risk_alerts: list[dict],
                 filing_result: dict = None) -> str:
        """生成完整HTML仪表盘"""

        # --- 税务申报状态 (filing_result) ---
        filing_html = ""
        ocr_status_html = ""

        # OCR状态提示
        import os as _os
        has_baidu_key = bool(_os.environ.get("BAIDU_OCR_API_KEY", ""))
        if has_baidu_key:
            ocr_status_html = '<div style="margin-top:8px;padding:8px 12px;background:#f6ffed;border-radius:6px;font-size:12px;color:#52c41a;border:1px solid #b7eb8f">✅ 百度OCR API 已配置 — 实时识别模式</div>'
        else:
            ocr_status_html = '<div style="margin-top:8px;padding:8px 12px;background:#fffbe6;border-radius:6px;font-size:12px;color:#faad14;border:1px solid #ffe58f">⚠️ 百度OCR API 未配置 — 当前使用本地规则解析（精度85%）。<br>配置方式：设置环境变量 BAIDU_OCR_API_KEY / BAIDU_OCR_SECRET_KEY</div>'

        if filing_result:
            vat_f = filing_result.get("vat", {})
            income_f = filing_result.get("income_tax", {})
            risks_f = filing_result.get("risks", [])
            risk_sum = filing_result.get("risk_summary", {})

            def status_badge(status: str) -> str:
                colors = {"已申报": "green", "待申报": "yellow", "申报异常": "red",
                          "已缴款": "blue", "申报中": "blue"}
                c = colors.get(status, "yellow")
                return f'<span class="badge badge-{c}">{status}</span>'

            serial_vat = vat_f.get("serial_no", "-")
            serial_it  = income_f.get("serial_no", "-")

            risk_rows_f = ""
            for r in risks_f[:5]:
                icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(r.get("level", "low"), "🟢")
                risk_rows_f += f'<tr><td>{icon} {r.get("title","")}</td><td style="font-size:11px;color:#8c8c8c">{r.get("suggestion","")[:60]}</td></tr>'

            filing_html = f"""
<div class="section">
  <h2>🏛️ 金税四期申报状态</h2>
  <div class="grid-2">
    <div>
      <table>
        <thead><tr><th>税种</th><th>应纳税额</th><th>附加税</th><th>申报状态</th><th>受理编号</th></tr></thead>
        <tbody>
          <tr>
            <td><strong>增值税及附加</strong></td>
            <td style="text-align:right">¥{vat_f.get('vat_payable',0):,.2f}</td>
            <td style="text-align:right">¥{vat_f.get('surcharge',0):,.2f}</td>
            <td>{status_badge(vat_f.get('status','待申报'))}</td>
            <td style="font-size:11px;color:#1890ff">{serial_vat}</td>
          </tr>
          <tr>
            <td><strong>企业所得税</strong></td>
            <td style="text-align:right">¥{income_f.get('tax_payable',0):,.2f}</td>
            <td>-</td>
            <td>{status_badge(income_f.get('status','待申报'))}</td>
            <td style="font-size:11px;color:#1890ff">{serial_it}</td>
          </tr>
        </tbody>
        <tfoot>
          <tr style="font-weight:700;background:#fff7e6">
            <td>合计应缴</td>
            <td style="text-align:right">¥{(vat_f.get('total_payable',0)+income_f.get('tax_payable',0)):,.2f}</td>
            <td colspan="3">截止 {filing_result.get('period','')}月15日</td>
          </tr>
        </tfoot>
      </table>
    </div>
    <div>
      <div style="font-size:13px;font-weight:600;margin-bottom:8px">⚠️ 金税四期风险预检（{risk_sum.get('high',0)}高/{risk_sum.get('medium',0)}中/{risk_sum.get('low',0)}低）</div>
      <table>
        <thead><tr><th>风险项</th><th>建议</th></tr></thead>
        <tbody>{risk_rows_f if risk_rows_f else '<tr><td colspan="2" style="color:#52c41a">✅ 未检测到申报风险</td></tr>'}</tbody>
      </table>
      {('<div style="padding:8px 12px;background:#fff2f0;border-radius:6px;font-size:12px;color:#ff4d4f;margin-top:8px">🚫 ' + vat_f.get("message","") + '</div>') if vat_f.get("blocked") else ''}
    </div>
  </div>
  <div style="margin-top:12px;padding:10px 16px;background:#e6f7ff;border-radius:6px;font-size:12px;color:#1890ff">
    <strong>📡 申报模式：</strong>
    本地模拟申报（XML已生成，受理编号已分配）<br>
    <strong>生产对接：</strong>设置 TAX_API_KEY / TAX_API_BASE_URL 环境变量对接高灯科技/百望云/企享云
  </div>
</div>"""
        else:
            filing_html = f"""
<div class="section">
  <h2>🏛️ 金税四期申报接口</h2>
  <div style="padding:16px;background:#f0f2f5;border-radius:8px;font-size:13px;color:#595959">
    <p>📌 金税四期申报模块已就绪，运行 <code>python main.py filing</code> 执行完整申报流程</p>
    <br>
    <p><strong>生产对接方式：</strong></p>
    <ul style="margin-top:8px;padding-left:20px;line-height:2">
      <li>高灯科技：设置 TAX_API_KEY + TAX_API_BASE_URL=https://open.gaodengtech.com</li>
      <li>百望云：设置 TAX_API_KEY + TAX_API_BASE_URL=https://api.baiwang.com</li>
      <li>企享云：设置 TAX_API_KEY + TAX_API_BASE_URL=https://api.qixiangyun.com</li>
    </ul>
  </div>
</div>"""

        # --- KPI ---
        total_vouchers = len(vouchers)
        reviewed = sum(1 for v in vouchers if v.status == "reviewed")
        total_invoices = len(invoices)
        total_tax = tax_data.get("vat_payable", 0) + income_data.get("tax_payable", 0)
        risk_count = len(risk_alerts)
        high_risks = sum(1 for a in risk_alerts if a.get("severity") == "high")

        risk_card_class = "danger" if high_risks > 0 else ("warn" if risk_count > 0 else "")
        risk_sub = f"{high_risks}个高危" if high_risks > 0 else "安全"

        # 自动化率（除人工审核外全部自动化）
        total_steps = 7
        auto_steps = 6  # OCR/分录/凭证/报表/报税/预警均为自动
        auto_rate = round(auto_steps / total_steps * 100)

        # --- 工作流 ---
        flow_steps = cls._build_flow_steps(total_invoices, total_vouchers, auto_rate)

        # --- 票据类型统计 ---
        type_counts: dict[str, int] = {}
        type_amounts: dict[str, float] = {}
        for inv in invoices:
            t = inv.invoice_type.value
            type_counts[t] = type_counts.get(t, 0) + 1
            type_amounts[t] = type_amounts.get(t, 0) + inv.total_amount

        # --- 票据明细行 ---
        invoice_rows = ""
        for i, inv in enumerate(invoices, 1):
            conf_class = "green" if inv.confidence >= 0.85 else ("yellow" if inv.confidence >= 0.6 else "red")
            invoice_rows += f"""<tr>
<td>{i}</td>
<td><span class="badge badge-blue">{inv.invoice_type.value[:8]}</span></td>
<td>{inv.invoice_code} {inv.invoice_number}</td>
<td>{inv.invoice_date.isoformat() if inv.invoice_date else '-'}</td>
<td>{inv.seller_name[:12]}</td>
<td style="text-align:right">¥{inv.amount:,.2f}</td>
<td style="text-align:right">¥{inv.tax_amount:,.2f}</td>
<td><span class="badge badge-{conf_class}">{inv.confidence:.0%}</span></td>
</tr>"""

        # --- 凭证行 ---
        voucher_rows = ""
        for v in vouchers:
            status_class = {"draft": "yellow", "reviewed": "green", "posted": "blue"}.get(v.status, "yellow")
            status_text = {"draft": "草稿", "reviewed": "已审核", "posted": "已过账"}.get(v.status, v.status)
            voucher_rows += f"""<tr>
<td>记-{v.voucher_number:04d}</td>
<td>{v.voucher_date.isoformat()}</td>
<td>{len(v.entries)}</td>
<td style="text-align:right">¥{v.total_debit:,.2f}</td>
<td style="text-align:right">¥{v.total_credit:,.2f}</td>
<td>{v.attachments}</td>
<td><span class="badge badge-{status_class}">{status_text}</span></td>
</tr>"""

        # --- 第一张凭证详情 ---
        detail_html = ""
        if vouchers:
            v0 = vouchers[0]
            entry_rows = ""
            for e in v0.entries:
                dir_symbol = "🔴借" if e.direction == Direction.DEBIT else "🟢贷"
                entry_rows += f"""<tr>
<td>{e.line_no + 1}</td>
<td>{e.account_code} {e.account_name}</td>
<td>{dir_symbol}</td>
<td style="text-align:right">¥{e.amount:,.2f}</td>
<td>{e.summary[:30]}</td>
</tr>"""
            detail_html = f"""<div class="section">
<h2>🔍 凭证样例：记-{v0.voucher_number:04d}</h2>
<table>
<thead><tr><th>行</th><th>科目</th><th>方向</th><th style="text-align:right">金额</th><th>摘要</th></tr></thead>
<tbody>{entry_rows}</tbody>
<tfoot>
<tr style="font-weight:700;background:#fafafa">
  <td colspan="3">合计</td>
  <td style="text-align:right">借方 ¥{v0.total_debit:,.2f} / 贷方 ¥{v0.total_credit:,.2f}</td>
  <td>{'✅ 借贷平衡' if abs(v0.total_debit - v0.total_credit) < 0.01 else '❌ 不平衡'}</td>
</tr>
</tfoot>
</table>
</div>"""

        # --- 资产负债表行 ---
        bs_rows = ""
        total_assets = 0
        total_liab = 0
        total_eq = 0
        for item in balance_data.get("assets", [])[:8]:
            bs_rows += f"<tr><td>{item['code']} {item['name']}</td><td style='text-align:right'>¥{item['amount']:,.2f}</td></tr>"
            total_assets += item['amount']
        bs_rows += "<tr style='color:#8c8c8c'><td colspan='2'>（其他资产科目...）</td></tr>"
        for item in balance_data.get("liabilities", [])[:5]:
            bs_rows += f"<tr><td>{item['code']} {item['name']}</td><td style='text-align:right'>¥{item['amount']:,.2f}</td></tr>"
            total_liab += item['amount']
        for item in balance_data.get("equity", [])[:5]:
            bs_rows += f"<tr><td>{item['code']} {item['name']}</td><td style='text-align:right'>¥{item['amount']:,.2f}</td></tr>"
            total_eq += item['amount']

        # --- 利润表行 ---
        is_rows = f"""
<tr><td>营业收入</td><td style="text-align:right">¥{income_data.get('revenue', 0):,.2f}</td></tr>
<tr><td>减：营业成本</td><td style="text-align:right">¥{income_data.get('cost', 0):,.2f}</td></tr>
<tr style="font-weight:600;border-top:2px solid #f0f0f0"><td>毛利</td><td style="text-align:right">¥{income_data.get('gross_profit', 0):,.2f}</td></tr>
<tr><td>减：期间费用</td><td style="text-align:right">¥{income_data.get('expense', 0):,.2f}</td></tr>
<tr style="font-weight:700;background:#f6ffed;border-top:2px solid #b7eb8f"><td>利润总额</td><td style="text-align:right">¥{income_data.get('net_profit_before_tax', 0):,.2f}</td></tr>
"""

        # --- 报税行 ---
        tax_rows = f"""
<tr><td><strong>增值税</strong></td><td>销项¥{tax_data.get('output_tax', 0):,.2f} - 进项¥{tax_data.get('input_tax', 0):,.2f}</td>
<td>{tax_data.get('taxpayer_type', '')}</td>
<td style="text-align:right"><span class="badge badge-red">¥{tax_data.get('vat_payable', 0):,.2f}</span></td>
<td>{date.today().year}-{date.today().month:02d}-15</td>
<td><span class="badge badge-{'red' if tax_data.get('vat_payable', 0) > 0 else 'green'}">{'待申报' if tax_data.get('vat_payable', 0) > 0 else '零申报'}</span></td></tr>
<tr><td><strong>企业所得税</strong></td><td>应纳税所得额 ¥{income_data.get('net_profit_before_tax', 0):,.2f}</td>
<td>{income_data.get('tax_rate', 0.25):.0%}</td>
<td style="text-align:right"><span class="badge badge-red">¥{income_data.get('tax_payable', 0):,.2f}</span></td>
<td>{date.today().year}-{date.today().month:02d}-15</td>
<td><span class="badge badge-{'red' if income_data.get('tax_payable', 0) > 0 else 'green'}">{'待申报' if income_data.get('tax_payable', 0) > 0 else '零申报'}</span></td></tr>
<tr><td>印花税</td><td style="text-align:right">-</td><td>0.03%</td><td style="text-align:right">¥0.00</td><td>{date.today().year}-{date.today().month:02d}-15</td>
<td><span class="badge badge-green">无需申报</span></td></tr>
"""

        # --- 风险预警 ---
        risk_html = ""
        if not risk_alerts:
            risk_html = '<div class="alert low"><span class="icon">✅</span><div>未检测到风险，系统运行正常</div></div>'
        else:
            for a in risk_alerts:
                sev = a.get("severity", "low")
                icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(sev, "🟢")
                risk_html += f"""<div class="alert {sev}">
<span class="icon">{icon}</span>
<div><strong>{a.get('type', '')}</strong><br>{a.get('message', '')}<br><small>{a.get('suggestion', '')}</small></div>
</div>"""

        # --- 图表数据 ---
        labels = list(type_counts.keys())
        data = list(type_counts.values())
        expense_labels = list(type_amounts.keys())[:8]
        expense_data = [round(v, 2) for v in list(type_amounts.values())[:8]]

        return cls.TEMPLATE.format(
            company_name=company.name,
            period=f"{date.today().year}年{date.today().month}月",
            update_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            total_vouchers=total_vouchers,
            reviewed_vouchers=reviewed,
            total_invoices=total_invoices,
            total_tax=total_tax,
            risk_count=risk_count,
            risk_sub=risk_sub,
            risk_card_class=risk_card_class,
            automation_rate=auto_rate,
            flow_steps=flow_steps,
            ocr_status_html=ocr_status_html,
            filing_section=filing_html,
            invoice_rows=invoice_rows,
            voucher_rows=voucher_rows,
            voucher_detail_section=detail_html,
            balance_sheet_rows=bs_rows,
            total_assets=total_assets,
            total_liab_equity=total_liab + total_eq,
            income_statement_rows=is_rows,
            tax_rows=tax_rows,
            risk_alerts_html=risk_html,
            invoice_labels=json.dumps(labels, ensure_ascii=False),
            invoice_data=json.dumps(data),
            expense_labels=json.dumps(expense_labels, ensure_ascii=False),
            expense_data=json.dumps(expense_data),
        )

    @staticmethod
    def _build_flow_steps(total_invoices: int, total_vouchers: int, auto_rate: int) -> str:
        steps = [
            ("1", "票据采集", f"{total_invoices}张已就绪"),
            ("2", "OCR识别", f"AI自动分类+结构化"),
            ("3", "分录生成", f"智能匹配科目"),
            ("4", "凭证编制", f"生成{total_vouchers}张凭证"),
            ("5", "试算平衡", "自动校验借贷"),
            ("6", "报表生成", "三大报表就绪"),
            ("7", "报税申报", f"自动化率{auto_rate}%"),
        ]
        html_parts = []
        for i, (num, label, detail) in enumerate(steps):
            html_parts.append(
                f'<div class="flow-step"><div class="num">{num}</div>'
                f'<div class="label">{label}</div><div class="detail">{detail}</div></div>'
            )
            if i < len(steps) - 1:
                html_parts.append('<div class="arrow">→</div>')
        return "".join(html_parts)
