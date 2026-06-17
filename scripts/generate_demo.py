"""
演示数据生成器
模拟一个代账公司处理多客户票据的完整场景
"""

import random
import uuid
from datetime import date, datetime, timedelta

from core.models import (
    AccountingEntry, AccountBalance, AccountCategory, Company,
    Direction, Invoice, InvoiceType, Voucher,
)
from core.ocr import InvoiceOCR
from core.engine import AccountingEngine


def generate_demo_company() -> Company:
    """生成演示企业"""
    return Company(
        id=str(uuid.uuid4())[:8],
        name="星辰科技有限公司",
        tax_id="91110108MA01XXXXX",
        taxpayer_type="小规模纳税人",
        industry="信息技术服务",
        accounting_period="monthly",
        registered_capital=1000000.0,
        contact_person="张总",
        contact_phone="13800138000",
    )


def generate_demo_invoices() -> list[Invoice]:
    """生成演示票据数据（模拟OCR识别结果）"""
    today = date.today()
    invoices = [
        # 增值税电子发票 - 办公用品
        Invoice(
            id=f"inv_{uuid.uuid4().hex[:6]}",
            invoice_type=InvoiceType.VAT_ELECTRONIC,
            invoice_code="044002200111",
            invoice_number="12345678",
            invoice_date=today.replace(day=random.randint(1, 15)),
            seller_name="得力办公用品有限公司",
            buyer_name="星辰科技有限公司",
            amount=850.00,
            tax_amount=110.50,
            total_amount=960.50,
            raw_text="增值税电子发票 得力办公用品 金额850.00 税额110.50 价税合计960.50",
            confidence=0.95,
        ),
        # 增值税普通发票 - 餐饮
        Invoice(
            id=f"inv_{uuid.uuid4().hex[:6]}",
            invoice_type=InvoiceType.VAT_NORMAL,
            invoice_code="044002200112",
            invoice_number="23456789",
            invoice_date=today.replace(day=random.randint(1, 20)),
            seller_name="海底捞餐饮管理有限公司",
            buyer_name="星辰科技有限公司",
            amount=1200.00,
            tax_amount=0,
            total_amount=1200.00,
            raw_text="增值税普通发票 海底捞 金额1200.00 价税合计1200.00",
            confidence=0.92,
        ),
        # 银行回单 - 房租支付
        Invoice(
            id=f"inv_{uuid.uuid4().hex[:6]}",
            invoice_type=InvoiceType.BANK_RECEIPT,
            invoice_code="",
            invoice_number="20260615001",
            invoice_date=today.replace(day=5),
            seller_name="万科物业有限公司",
            buyer_name="星辰科技有限公司",
            amount=15000.00,
            tax_amount=0,
            total_amount=15000.00,
            raw_text="银行付款回单 收款方:万科物业 金额:15000.00 用途:办公室租金",
            confidence=0.90,
        ),
        # 火车票 - 出差
        Invoice(
            id=f"inv_{uuid.uuid4().hex[:6]}",
            invoice_type=InvoiceType.TRAIN_TICKET,
            invoice_code="",
            invoice_number="T20260615001",
            invoice_date=today.replace(day=10),
            seller_name="中国铁路总公司",
            buyer_name="星辰科技有限公司",
            amount=545.00,
            tax_amount=0,
            total_amount=545.00,
            raw_text="火车票 北京南-上海虹桥 G123次 二等座 545.00元",
            confidence=0.88,
        ),
        # 出租车票
        Invoice(
            id=f"inv_{uuid.uuid4().hex[:6]}",
            invoice_type=InvoiceType.TAXI_RECEIPT,
            invoice_code="",
            invoice_number="",
            invoice_date=today.replace(day=12),
            seller_name="北京出租汽车公司",
            buyer_name="星辰科技有限公司",
            amount=68.00,
            tax_amount=0,
            total_amount=68.00,
            raw_text="北京市出租汽车专用发票 金额:68.00",
            confidence=0.85,
        ),
        # 定额发票 - 停车费
        Invoice(
            id=f"inv_{uuid.uuid4().hex[:6]}",
            invoice_type=InvoiceType.QUOTA_INVOICE,
            invoice_code="044002200113",
            invoice_number="34567890",
            invoice_date=today.replace(day=8),
            seller_name="万达广场停车场",
            buyer_name="星辰科技有限公司",
            amount=50.00,
            tax_amount=0,
            total_amount=50.00,
            raw_text="通用定额发票 伍拾元整",
            confidence=0.87,
        ),
        # 机打发票 - 快递费
        Invoice(
            id=f"inv_{uuid.uuid4().hex[:6]}",
            invoice_type=InvoiceType.EXPRESS_FEE,
            invoice_code="",
            invoice_number="",
            invoice_date=today.replace(day=3),
            seller_name="顺丰速运有限公司",
            buyer_name="星辰科技有限公司",
            amount=35.00,
            tax_amount=0,
            total_amount=35.00,
            raw_text="顺丰速运 快递费 35.00元",
            confidence=0.83,
        ),
        # 网约车发票
        Invoice(
            id=f"inv_{uuid.uuid4().hex[:6]}",
            invoice_type=InvoiceType.RIDE_HAILING,
            invoice_code="",
            invoice_number="",
            invoice_date=today.replace(day=14),
            seller_name="滴滴出行科技有限公司",
            buyer_name="星辰科技有限公司",
            amount=128.00,
            tax_amount=0,
            total_amount=128.00,
            raw_text="滴滴出行 行程单 金额128.00",
            confidence=0.89,
        ),
        # 增值税电子发票 - 软件服务费
        Invoice(
            id=f"inv_{uuid.uuid4().hex[:6]}",
            invoice_type=InvoiceType.VAT_ELECTRONIC,
            invoice_code="044002200114",
            invoice_number="45678901",
            invoice_date=today.replace(day=6),
            seller_name="阿里云计算有限公司",
            buyer_name="星辰科技有限公司",
            amount=3000.00,
            tax_amount=180.00,
            total_amount=3180.00,
            raw_text="增值税电子发票 阿里云 云服务器ECS 金额3000.00 税额180.00",
            confidence=0.96,
        ),
        # 飞机行程单
        Invoice(
            id=f"inv_{uuid.uuid4().hex[:6]}",
            invoice_type=InvoiceType.FLIGHT_ITINERARY,
            invoice_code="",
            invoice_number="ET20260615001",
            invoice_date=today.replace(day=15),
            seller_name="中国国际航空公司",
            buyer_name="星辰科技有限公司",
            amount=2180.00,
            tax_amount=0,
            total_amount=2180.00,
            raw_text="航空运输电子客票行程单 北京-深圳 CA1234 票价2180.00",
            confidence=0.91,
        ),
    ]
    return invoices


def generate_demo_account_balances(company: Company) -> list[AccountBalance]:
    """生成演示科目余额"""
    period = f"{date.today().year}-{date.today().month:02d}"
    return [
        AccountBalance("1001", "库存现金", AccountCategory.ASSET, 50000, 35000, Direction.DEBIT, period),
        AccountBalance("1002", "银行存款", AccountCategory.ASSET, 500000, 180000, Direction.DEBIT, period),
        AccountBalance("1122", "应收账款", AccountCategory.ASSET, 120000, 80000, Direction.DEBIT, period),
        AccountBalance("1403", "原材料", AccountCategory.ASSET, 3850, 0, Direction.DEBIT, period),
        AccountBalance("1601", "固定资产", AccountCategory.ASSET, 200000, 0, Direction.DEBIT, period),
        AccountBalance("1602", "累计折旧", AccountCategory.ASSET, 0, 15000, Direction.CREDIT, period),
        AccountBalance("2202", "应付账款", AccountCategory.LIABILITY, 0, 45000, Direction.CREDIT, period),
        AccountBalance("2211", "应付职工薪酬", AccountCategory.LIABILITY, 0, 60000, Direction.CREDIT, period),
        AccountBalance("2221", "应交税费", AccountCategory.LIABILITY, 0, 8500, Direction.CREDIT, period),
        AccountBalance("3001", "实收资本", AccountCategory.EQUITY, 0, 500000, Direction.CREDIT, period),
        AccountBalance("3103", "本年利润", AccountCategory.EQUITY, 0, 80000, Direction.CREDIT, period),
        AccountBalance("5001", "主营业务收入", AccountCategory.REVENUE, 0, 150000, Direction.CREDIT, period),
        AccountBalance("5602", "管理费用", AccountCategory.EXPENSE, 45000, 0, Direction.DEBIT, period),
        AccountBalance("5603", "销售费用", AccountCategory.EXPENSE, 15000, 0, Direction.DEBIT, period),
        AccountBalance("5604", "财务费用", AccountCategory.EXPENSE, 500, 0, Direction.DEBIT, period),
    ]


def run_full_demo(with_filing: bool = False):
    """运行完整演示流程（可选：含金税四期申报）"""
    print("=" * 60)
    print("   AI代理记账系统 v2.0 - 完整流程演示")
    print("=" * 60)

    # 1. 准备企业信息
    company = generate_demo_company()
    print(f"\n📋 被代账企业: {company.name}")
    print(f"   纳税人类型: {company.taxpayer_type}")
    print(f"   行业: {company.industry}")

    # 2. 生成演示票据（模拟OCR已识别）
    invoices = generate_demo_invoices()
    print(f"\n📄 收到票据: {len(invoices)} 张")

    # 票据分类统计
    type_counts = {}
    for inv in invoices:
        t = inv.invoice_type.value
        type_counts[t] = type_counts.get(t, 0) + 1
    for t, c in type_counts.items():
        print(f"   {t}: {c}张")

    # 3. 生成会计分录
    engine = AccountingEngine()
    vouchers = engine.batch_create_vouchers(invoices, company)
    print(f"\n📝 自动生成凭证: {len(vouchers)} 张")

    for v in vouchers:
        ok, msg = engine.validate_voucher(v)
        status = "✅" if ok else "❌"
        print(f"   {status} 记-{v.voucher_number:04d} | {len(v.entries)}行分录 | 借¥{v.total_debit:,.2f} 贷¥{v.total_credit:,.2f}")

    # 4. 生成科目余额
    balances = generate_demo_account_balances(company)

    # 5. 生成报表
    from core.reports import ReportGenerator
    from core.tax import TaxHelper, RiskEngine

    # 试算平衡
    tb = ReportGenerator.generate_trial_balance(balances)
    print(f"\n📊 试算平衡: {'✅ 平衡' if tb['balanced'] else '❌ 不平衡'}")

    # 资产负债表
    bs = ReportGenerator.generate_balance_sheet(balances)

    # 利润表
    revenue_items = [b for b in balances if b.category == AccountCategory.REVENUE]
    expense_items = [b for b in balances if b.category == AccountCategory.EXPENSE]
    cost_items = [b for b in balances if b.category == AccountCategory.COST]
    income = ReportGenerator.generate_income_statement(revenue_items, expense_items, cost_items)

    # 6. 报税计算
    output_inv = [inv for inv in invoices if inv.invoice_type in {InvoiceType.VAT_SPECIAL, InvoiceType.VAT_ELECTRONIC}]
    vat_result = TaxHelper.compute_vat(company, output_inv, invoices)
    income_tax = TaxHelper.compute_income_tax(
        company, income["revenue"], income["cost"], income["expense"]
    )

    print(f"\n🧾 增值税: 销项¥{vat_result['output_tax']:,.2f} | 进项¥{vat_result['input_tax']:,.2f} | 应纳¥{vat_result['vat_payable']:,.2f}")
    print(f"🧾 企业所得税: 利润¥{income_tax['taxable_income']:,.2f} | 税率{income_tax['tax_rate']:.0%} | 应纳¥{income_tax['tax_payable']:,.2f}")

    # 7. 风险检查
    risk_engine = RiskEngine()
    risks = []

    # 凭证平衡检查
    bal_risks = risk_engine.check_voucher_balance(vouchers)
    risks.extend(bal_risks)

    # 税负检查
    tax_burden = risk_engine.check_tax_burden_anomaly(
        vat_result["vat_payable"], income["revenue"]
    )
    if tax_burden["severity"] != "low":
        risks.append(tax_burden)

    # 零申报检查
    zero_risk = TaxHelper.check_zero_declaration_risk(company, 0)
    if zero_risk["risk"] == "high":
        risks.append({"type": "零申报风险", "severity": "high",
                       "message": zero_risk["message"],
                       "suggestion": zero_risk["suggestion"]})

    print(f"\n⚠️ 风险预警: {len(risks)} 项")
    for r in risks:
        print(f"   [{r['severity']}] {r.get('type', r.get('title', ''))}: {r.get('message', '')}")

    # 8. 金税四期申报（可选）
    filing_result = None
    if with_filing:
        from core.golden_tax import FilingOrchestrator
        output_inv2 = [inv for inv in invoices if inv.invoice_type in {InvoiceType.VAT_SPECIAL, InvoiceType.VAT_ELECTRONIC}]
        input_inv2  = [inv for inv in invoices if inv.invoice_type not in {InvoiceType.VAT_SPECIAL, InvoiceType.VAT_ELECTRONIC}]
        orch = FilingOrchestrator(company, mode="simulate")
        filing_result = orch.run_monthly(
            output_invoices=output_inv2,
            input_invoices=input_inv2,
            total_revenue=income["revenue"],
            total_cost=income["cost"],
            total_expense=income["expense"],
        )
        print(f"\n🏛️ 金税四期申报（模拟）")
        print(f"   增值税: ¥{filing_result['vat'].get('total_payable',0):,.2f} | {filing_result['vat'].get('status','—')}")
        print(f"   所得税: ¥{filing_result['income_tax'].get('tax_payable',0):,.2f} | {filing_result['income_tax'].get('status','—')}")
        print(f"   风险项: {filing_result['risk_summary']['high']}高/{filing_result['risk_summary']['medium']}中")
        if filing_result['vat'].get('serial_no'):
            print(f"   受理编号: {filing_result['vat']['serial_no']}")

    # 9. 生成HTML仪表盘
    from web.dashboard import DashboardGenerator
    html = DashboardGenerator.generate(
        company, invoices, vouchers,
        vat_result, income_tax, bs, risks,
        filing_result=filing_result,
    )

    html_path = "C:/Users/PC/WorkBuddy/2026-06-17-11-54-26/agent-accounting/demo_data/dashboard.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n✅ 仪表盘已生成: {html_path}")
    return html_path, html


if __name__ == "__main__":
    run_full_demo()
