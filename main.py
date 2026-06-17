"""
AI代理记账系统 - CLI入口
Usage: python main.py [demo|ocr|vouchers|reports|tax|risk|baidu_ocr|filing|full]
"""

import sys

from core.models import Company, InvoiceType
from core.ocr import InvoiceOCR
from core.engine import AccountingEngine
from core.reports import ReportGenerator
from core.tax import TaxHelper, RiskEngine
from core.baidu_ocr import BaiduOCRClient
from core.golden_tax import FilingOrchestrator, GoldenTaxRiskChecker, TaxReturnBuilder


def cmd_demo():
    """运行完整演示"""
    from scripts.generate_demo import run_full_demo
    run_full_demo()


def cmd_ocr_test():
    """测试OCR票据识别"""
    test_texts = [
        "增值税电子发票 代码044002200111 号码12345678 销售方:得力办公用品有限公司 购买方:星辰科技有限公司 不含税金额850.00 税额110.50 价税合计960.50",
        "火车票 北京南-上海虹桥 G123次 二等座 545.00元 日期2026年6月10日",
        "银行付款回单 收款方:万科物业有限公司 金额:15000.00 用途:办公室租金 2026年6月5日",
        "航空运输电子客票行程单 北京-深圳 CA1234 票价2180.00 日期2026年6月15日",
        "通用定额发票 伍拾元整 盖章有效",
        "滴滴出行 行程单 金额128.00 2026年6月14日 北京朝阳-海淀",
    ]

    ocr = InvoiceOCR()
    print("=" * 60)
    print("  OCR票据识别测试")
    print("=" * 60)

    for i, text in enumerate(test_texts, 1):
        inv = ocr.parse_text_to_invoice(text)
        print(f"\n📄 票据 #{i}")
        print(f"   类型: {inv.invoice_type.value}")
        print(f"   金额: ¥{inv.amount:,.2f} | 税额: ¥{inv.tax_amount:,.2f}")
        print(f"   销售方: {inv.seller_name}")
        print(f"   日期: {inv.invoice_date}")
        print(f"   置信度: {inv.confidence:.0%}")

        # 显示科目映射
        mapping = ocr.get_account_mapping(inv.invoice_type)
        print(f"   科目映射: 借:{mapping.get('debit','')} / 贷:{mapping.get('credit','')}")


def cmd_vouchers():
    """查看凭证"""
    from scripts.generate_demo import generate_demo_company, generate_demo_invoices
    company = generate_demo_company()
    invoices = generate_demo_invoices()
    engine = AccountingEngine()
    vouchers = engine.batch_create_vouchers(invoices, company)

    print("=" * 60)
    print(f"  记账凭证列表 - {company.name}")
    print("=" * 60)

    for v in vouchers:
        ok, msg = engine.validate_voucher(v)
        status = "✅" if ok else "❌"
        print(f"\n{status} 记-{v.voucher_number:04d} | {v.voucher_date} | {len(v.entries)}行分录")
        print(f"   借方合计: ¥{v.total_debit:,.2f} | 贷方合计: ¥{v.total_credit:,.2f}")
        print(f"   状态: {v.status} | 附件: {v.attachments}张")
        for e in v.entries:
            dir_sym = "借" if e.direction.value == "借" else "贷"
            print(f"     {e.line_no+1}. {dir_sym} {e.account_code} {e.account_name} ¥{e.amount:,.2f}")


def cmd_reports():
    """查看报表"""
    from scripts.generate_demo import (
        generate_demo_company, generate_demo_invoices,
        generate_demo_account_balances,
    )
    from core.engine import AccountingEngine, AccountCategory

    company = generate_demo_company()
    invoices = generate_demo_invoices()
    engine = AccountingEngine()
    vouchers = engine.batch_create_vouchers(invoices, company)
    balances = generate_demo_account_balances(company)

    # 凭证汇总
    summary = ReportGenerator.generate_voucher_summary(vouchers)
    print("=" * 60)
    print("  凭证汇总")
    print("=" * 60)
    print(f"  总计: {summary['total_vouchers']}张凭证, ¥{summary['total_amount']:,.2f}")
    print(f"  状态: 草稿{summary['status_summary']['draft']} | 已审核{summary['status_summary']['reviewed']} | 已过账{summary['status_summary']['posted']}")

    # 利润表
    revenue = [b for b in balances if b.category == AccountCategory.REVENUE]
    expense = [b for b in balances if b.category == AccountCategory.EXPENSE]
    cost = [b for b in balances if b.category == AccountCategory.COST]
    income = ReportGenerator.generate_income_statement(revenue, expense, cost)

    print(f"\n{'='*60}")
    print(f"  利润表")
    print(f"{'='*60}")
    print(f"  营业收入: ¥{income['revenue']:,.2f}")
    print(f"  减:营业成本: ¥{income['cost']:,.2f}")
    print(f"  毛利: ¥{income['gross_profit']:,.2f}")
    print(f"  减:期间费用: ¥{income['expense']:,.2f}")
    print(f"  利润总额: ¥{income['net_profit_before_tax']:,.2f}")


def cmd_tax():
    """报税数据"""
    from scripts.generate_demo import (
        generate_demo_company, generate_demo_invoices,
        generate_demo_account_balances,
    )
    from core.engine import AccountingEngine, AccountCategory

    company = generate_demo_company()
    invoices = generate_demo_invoices()
    balances = generate_demo_account_balances(company)

    revenue = sum(abs(b.credit_amount - b.debit_amount) for b in balances if b.category == AccountCategory.REVENUE)
    cost = sum(abs(b.debit_amount - b.credit_amount) for b in balances if b.category == AccountCategory.COST)
    expense = sum(abs(b.debit_amount - b.credit_amount) for b in balances if b.category == AccountCategory.EXPENSE)

    output_inv = [inv for inv in invoices if inv.invoice_type in {InvoiceType.VAT_SPECIAL, InvoiceType.VAT_ELECTRONIC}]

    # VAT
    vat = TaxHelper.compute_vat(company, output_inv, invoices)
    # Income tax
    income_tax = TaxHelper.compute_income_tax(company, revenue, cost, expense)

    print("=" * 60)
    print(f"  报税数据 - {company.name}")
    print("=" * 60)
    print(f"\n🧾 增值税")
    print(f"   销项税额: ¥{vat['output_tax']:,.2f}")
    print(f"   进项税额: ¥{vat['input_tax']:,.2f}")
    print(f"   差旅可抵扣: ¥{vat['travel_deduct']:,.2f}")
    print(f"   应纳增值税: ¥{vat['vat_payable']:,.2f}")

    print(f"\n🧾 企业所得税")
    print(f"   营业收入: ¥{income_tax['total_revenue']:,.2f}")
    print(f"   应纳税所得额: ¥{income_tax['taxable_income']:,.2f}")
    print(f"   适用税率: {income_tax['tax_rate']:.0%}")
    print(f"   应纳所得税: ¥{income_tax['tax_payable']:,.2f}")

    # 报税日历
    print(f"\n📅 本月报税日历")
    for item in TaxHelper.generate_tax_calendar(company):
        print(f"   {item['tax_type']}: 截止 {item['deadline']} [{item['priority']}]")


def cmd_risk():
    """风险检测"""
    from scripts.generate_demo import generate_demo_company, generate_demo_invoices
    company = generate_demo_company()
    invoices = generate_demo_invoices()

    print("=" * 60)
    print(f"  风险检测 - {company.name}")
    print("=" * 60)

    # 零申报风险
    zero = TaxHelper.check_zero_declaration_risk(company, 4)
    print(f"\n零申报风险: [{zero['risk']}] {zero['message']}")

    # 发票过期
    expiry = RiskEngine.check_invoice_expiry(invoices)
    for e in expiry:
        print(f"发票过期风险: [{e['severity']}] {e['message']}")

    # 税负
    burden = RiskEngine.check_tax_burden_anomaly(0, 150000)
    print(f"税负风险: [{burden['severity']}] {burden['message']}")


def cmd_baidu_ocr_test():
    """测试百度OCR API连接状态"""
    client = BaiduOCRClient()
    result = client.test_connection()

    print("=" * 60)
    print("  百度OCR API 连接测试")
    print("=" * 60)
    status = result["status"]
    icon = "✅" if status == "ok" else "⚠️" if status == "not_configured" else "❌"
    print(f"\n{icon} 状态: {status}")
    print(f"   {result['message']}")

    if status == "not_configured":
        print("\n📋 配置方法:")
        print("   Windows PowerShell:")
        print("   $env:BAIDU_OCR_API_KEY='your_api_key'")
        print("   $env:BAIDU_OCR_SECRET_KEY='your_secret_key'")
        print("\n   Linux/Mac:")
        print("   export BAIDU_OCR_API_KEY=your_api_key")
        print("   export BAIDU_OCR_SECRET_KEY=your_secret_key")
        print("\n💡 申请地址: https://ai.baidu.com/tech/ocr/finance")
        print("   ✅ 免费额度: 每月500次（智能财务票据识别）")
        print("\n⚠️  当前模式: 本地规则解析（精度约85%，API精度92%+）")


def cmd_filing():
    """测试金税四期申报流程"""
    from scripts.generate_demo import (
        generate_demo_company, generate_demo_invoices,
        generate_demo_account_balances,
    )
    from core.engine import AccountCategory

    company  = generate_demo_company()
    invoices = generate_demo_invoices()
    balances = generate_demo_account_balances(company)

    revenue = sum(abs(b.credit_amount - b.debit_amount)
                  for b in balances if b.category == AccountCategory.REVENUE)
    cost    = sum(abs(b.debit_amount - b.credit_amount)
                  for b in balances if b.category == AccountCategory.COST)
    expense = sum(abs(b.debit_amount - b.credit_amount)
                  for b in balances if b.category == AccountCategory.EXPENSE)

    output_inv = [inv for inv in invoices
                  if inv.invoice_type in {InvoiceType.VAT_SPECIAL, InvoiceType.VAT_ELECTRONIC}]
    input_inv  = [inv for inv in invoices
                  if inv.invoice_type not in {InvoiceType.VAT_SPECIAL, InvoiceType.VAT_ELECTRONIC}]

    orch = FilingOrchestrator(company, mode="simulate")
    result = orch.run_monthly(
        output_invoices=output_inv,
        input_invoices=input_inv,
        total_revenue=revenue,
        total_cost=cost,
        total_expense=expense,
    )

    print("=" * 60)
    print(f"  金税四期申报流程 - {result['company']}")
    print("=" * 60)

    vat = result["vat"]
    print(f"\n📊 增值税申报 [{result['period']}]")
    print(f"   销项税: ¥{vat.get('output_tax',0):,.2f}")
    print(f"   进项税: ¥{vat.get('input_tax',0):,.2f}")
    print(f"   应纳增值税: ¥{vat.get('vat_payable',0):,.2f}")
    print(f"   附加税费: ¥{vat.get('surcharge',0):,.2f}")
    print(f"   合计应缴: ¥{vat.get('total_payable',0):,.2f}")
    print(f"   申报状态: {vat.get('status','—')}")
    if vat.get("serial_no"):
        print(f"   受理编号: {vat['serial_no']}")
    if vat.get("message"):
        print(f"   消息: {vat['message']}")

    income = result["income_tax"]
    print(f"\n🏢 企业所得税 ({result['period']})")
    print(f"   应纳税所得额: ¥{income.get('taxable_income',0):,.2f}")
    print(f"   税率: {income.get('tax_rate','—')}")
    print(f"   应纳税额: ¥{income.get('tax_payable',0):,.2f}")
    print(f"   申报状态: {income.get('status','—')}")

    print(f"\n⚠️  金税四期风险预检 ({result['risk_summary']['high']}高/{result['risk_summary']['medium']}中/{result['risk_summary']['low']}低)")
    for risk in result["risks"]:
        icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(risk["level"], "⚪")
        print(f"   {icon} [{risk['risk_id']}] {risk['title']}")
        print(f"      💡 {risk['suggestion']}")

    print(f"\n📄 XML申报包预览 (增值税前300字符):")
    print(result["xml"]["vat"][:300])


def cmd_full():
    """运行完整集成演示（OCR + 做账 + 申报 + 仪表盘）"""
    from scripts.generate_demo import run_full_demo
    run_full_demo(with_filing=True)


COMMANDS = {
    "demo":      cmd_demo,
    "ocr":       cmd_ocr_test,
    "vouchers":  cmd_vouchers,
    "reports":   cmd_reports,
    "tax":       cmd_tax,
    "risk":      cmd_risk,
    "baidu_ocr": cmd_baidu_ocr_test,
    "filing":    cmd_filing,
    "full":      cmd_full,
}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("AI代理记账系统 v2.0")
        print("Usage: python main.py <command>")
        print()
        print("  demo       - 运行完整演示并生成HTML仪表盘")
        print("  ocr        - 测试本地OCR票据识别")
        print("  baidu_ocr  - 测试百度OCR API连接状态")
        print("  filing     - 测试金税四期申报流程")
        print("  full       - 完整集成演示（OCR+做账+申报+仪表盘）")
        print("  vouchers   - 查看凭证列表")
        print("  reports    - 查看财务报表")
        print("  tax        - 查看报税数据")
        print("  risk       - 运行风险检测")
        sys.exit(0)

    cmd = sys.argv[1]
    if cmd in COMMANDS:
        COMMANDS[cmd]()
    else:
        print(f"未知命令: {cmd}")
        print(f"可用命令: {list(COMMANDS.keys())}")
