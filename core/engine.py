"""
智能会计分录引擎
自动根据票据类型匹配会计科目，生成借贷分录，组装记账凭证
"""

import uuid
from datetime import date, datetime
from typing import Optional

from .models import (
    AccountCategory, AccountingEntry, Direction, Invoice, InvoiceType, Voucher,
    Company, AccountBalance,
)
from .ocr import InvoiceOCR


# ============================================================
# 标准会计科目表（常用科目，可按需扩展）
# ============================================================
CHART_OF_ACCOUNTS = {
    # 资产类
    "1001": ("库存现金", AccountCategory.ASSET),
    "1002": ("银行存款", AccountCategory.ASSET),
    "1012": ("其他货币资金", AccountCategory.ASSET),
    "1122": ("应收账款", AccountCategory.ASSET),
    "1123": ("预付账款", AccountCategory.ASSET),
    "1221": ("其他应收款", AccountCategory.ASSET),
    "1403": ("原材料", AccountCategory.ASSET),
    "1405": ("库存商品", AccountCategory.ASSET),
    "1601": ("固定资产", AccountCategory.ASSET),
    "1602": ("累计折旧", AccountCategory.ASSET),
    "1701": ("无形资产", AccountCategory.ASSET),
    # 负债类
    "2001": ("短期借款", AccountCategory.LIABILITY),
    "2202": ("应付账款", AccountCategory.LIABILITY),
    "2203": ("预收账款", AccountCategory.LIABILITY),
    "2211": ("应付职工薪酬", AccountCategory.LIABILITY),
    "2221": ("应交税费", AccountCategory.LIABILITY),
    "222101": ("应交增值税", AccountCategory.LIABILITY),
    "22210101": ("进项税额", AccountCategory.LIABILITY),
    "22210102": ("销项税额", AccountCategory.LIABILITY),
    "222102": ("应交企业所得税", AccountCategory.LIABILITY),
    "222103": ("应交个人所得税", AccountCategory.LIABILITY),
    "222104": ("应交印花税", AccountCategory.LIABILITY),
    "2241": ("其他应付款", AccountCategory.LIABILITY),
    # 权益类
    "3001": ("实收资本", AccountCategory.EQUITY),
    "3002": ("资本公积", AccountCategory.EQUITY),
    "3101": ("盈余公积", AccountCategory.EQUITY),
    "3103": ("本年利润", AccountCategory.EQUITY),
    "3104": ("利润分配", AccountCategory.EQUITY),
    # 成本类
    "4001": ("生产成本", AccountCategory.COST),
    "4101": ("制造费用", AccountCategory.COST),
    "4103": ("劳务成本", AccountCategory.COST),
    # 损益-收入
    "5001": ("主营业务收入", AccountCategory.REVENUE),
    "5051": ("其他业务收入", AccountCategory.REVENUE),
    "5301": ("营业外收入", AccountCategory.REVENUE),
    # 损益-费用
    "5601": ("主营业务成本", AccountCategory.EXPENSE),
    "5602": ("管理费用", AccountCategory.EXPENSE),
    "560201": ("管理费用-办公费", AccountCategory.EXPENSE),
    "560202": ("管理费用-工资", AccountCategory.EXPENSE),
    "560203": ("管理费用-福利费", AccountCategory.EXPENSE),
    "560204": ("管理费用-通讯费", AccountCategory.EXPENSE),
    "560205": ("管理费用-折旧费", AccountCategory.EXPENSE),
    "560206": ("管理费用-租赁费", AccountCategory.EXPENSE),
    "560207": ("管理费用-差旅费", AccountCategory.EXPENSE),
    "560208": ("管理费用-业务招待费", AccountCategory.EXPENSE),
    "560209": ("管理费用-服务费", AccountCategory.EXPENSE),
    "5603": ("销售费用", AccountCategory.EXPENSE),
    "560301": ("销售费用-广告费", AccountCategory.EXPENSE),
    "560302": ("销售费用-运输费", AccountCategory.EXPENSE),
    "5604": ("财务费用", AccountCategory.EXPENSE),
    "560401": ("财务费用-利息支出", AccountCategory.EXPENSE),
    "560402": ("财务费用-手续费", AccountCategory.EXPENSE),
    "5711": ("营业外支出", AccountCategory.EXPENSE),
}


class AccountingEngine:
    """智能会计分录引擎"""

    def __init__(self):
        self.ocr = InvoiceOCR()

    def generate_entries(self, invoice: Invoice, voucher_id: str) -> list[AccountingEntry]:
        """
        根据票据自动生成会计分录
        核心逻辑：票据类型→科目映射→生成借贷分录
        """
        mapping = self._get_entry_rules(invoice)
        entries = []
        line = 0

        # 借方分录
        debit = AccountingEntry(
            id=str(uuid.uuid4())[:8],
            voucher_id=voucher_id,
            line_no=line,
            account_code=mapping["debit_code"],
            account_name=mapping["debit_name"],
            direction=Direction.DEBIT,
            amount=invoice.amount,
            summary=f"{invoice.invoice_type.value} - {invoice.seller_name}",
            invoice_id=invoice.id,
        )
        entries.append(debit)
        line += 1

        # 如果有税额（专票/电子票），单独做进项税额分录
        if invoice.tax_amount > 0 and "tax_code" in mapping:
            tax_entry = AccountingEntry(
                id=str(uuid.uuid4())[:8],
                voucher_id=voucher_id,
                line_no=line,
                account_code=mapping["tax_code"],
                account_name=mapping["tax_name"],
                direction=Direction.DEBIT,
                amount=invoice.tax_amount,
                summary=f"进项税额 - {invoice.invoice_code} {invoice.invoice_number}",
                invoice_id=invoice.id,
            )
            entries.append(tax_entry)
            line += 1

        # 贷方分录
        credit = AccountingEntry(
            id=str(uuid.uuid4())[:8],
            voucher_id=voucher_id,
            line_no=line,
            account_code=mapping["credit_code"],
            account_name=mapping["credit_name"],
            direction=Direction.CREDIT,
            amount=invoice.total_amount if invoice.total_amount > 0 else invoice.amount + invoice.tax_amount,
            summary=f"支付 - {invoice.seller_name}",
            invoice_id=invoice.id,
        )
        entries.append(credit)

        return entries

    def _get_entry_rules(self, invoice: Invoice) -> dict:
        """获取票据对应的分录规则"""
        inv_type = invoice.invoice_type

        # 银行回单特殊处理
        if inv_type == InvoiceType.BANK_RECEIPT:
            return {
                "debit_code": "2202", "debit_name": "应付账款",
                "credit_code": "1002", "credit_name": "银行存款",
            }

        # 银行流水 - 收入
        if inv_type == InvoiceType.BANK_STATEMENT:
            return {
                "debit_code": "1002", "debit_name": "银行存款",
                "credit_code": "5001", "credit_name": "主营业务收入",
            }

        # 差旅类票据
        travel_types = {InvoiceType.TRAIN_TICKET, InvoiceType.FLIGHT_ITINERARY,
                        InvoiceType.TAXI_RECEIPT, InvoiceType.RIDE_HAILING}
        if inv_type in travel_types:
            # 计算可抵扣进项税（火车票9%，飞机票9%，公路3%）
            tax_rate = 0.09 if inv_type in {InvoiceType.TRAIN_TICKET, InvoiceType.FLIGHT_ITINERARY} else 0.03
            tax = round(invoice.total_amount / (1 + tax_rate) * tax_rate, 2)
            amount = invoice.total_amount - tax
            return {
                "debit_code": "560207", "debit_name": "管理费用-差旅费",
                "credit_code": "1001", "credit_name": "库存现金",
                "tax_code": "22210101", "tax_name": "应交税费-应交增值税-进项税额",
            }

        # 增值税发票
        if inv_type in {InvoiceType.VAT_SPECIAL, InvoiceType.VAT_ELECTRONIC}:
            if invoice.tax_amount > 0:
                return {
                    "debit_code": "1403", "debit_name": "原材料",
                    "credit_code": "2202", "credit_name": "应付账款",
                    "tax_code": "22210101", "tax_name": "应交税费-应交增值税-进项税额",
                }
            return {
                "debit_code": "5602", "debit_name": "管理费用",
                "credit_code": "1002", "credit_name": "银行存款",
            }

        # 普通发票/定额发票
        if inv_type in {InvoiceType.VAT_NORMAL, InvoiceType.QUOTA_INVOICE, InvoiceType.MACHINE_INVOICE}:
            return {
                "debit_code": "5602", "debit_name": "管理费用",
                "credit_code": "1001", "credit_name": "库存现金",
            }

        # 快递费
        if inv_type == InvoiceType.EXPRESS_FEE:
            return {
                "debit_code": "560201", "debit_name": "管理费用-办公费",
                "credit_code": "1001", "credit_name": "库存现金",
            }

        # 默认：费用化处理
        return {
            "debit_code": "5602", "debit_name": "管理费用",
            "credit_code": "1001", "credit_name": "库存现金",
        }

    def batch_create_vouchers(self, invoices: list[Invoice], company: Company,
                               voucher_date: Optional[date] = None) -> list[Voucher]:
        """
        批量生成记账凭证
        智能合并：同一天同类型票据合并到一个凭证
        """
        if voucher_date is None:
            voucher_date = date.today()

        # 按类型分组
        groups: dict[InvoiceType, list[Invoice]] = {}
        for inv in invoices:
            inv_type = inv.invoice_type
            if inv_type not in groups:
                groups[inv_type] = []
            groups[inv_type].append(inv)

        vouchers = []
        number = 1

        for inv_type, invs in groups.items():
            vid = str(uuid.uuid4())[:10]
            entries = []

            for inv in invs:
                inv_entries = self.generate_entries(inv, vid)
                entries.extend(inv_entries)

            # 计算借贷合计
            total_debit = sum(e.amount for e in entries if e.direction == Direction.DEBIT)
            total_credit = sum(e.amount for e in entries if e.direction == Direction.CREDIT)

            v = Voucher(
                id=vid,
                voucher_date=voucher_date,
                voucher_type="记",
                voucher_number=number,
                company_id=company.id,
                entries=entries,
                total_debit=total_debit,
                total_credit=total_credit,
                attachments=len(invs),
                status="draft",
            )
            vouchers.append(v)
            number += 1

        return vouchers

    def validate_voucher(self, voucher: Voucher) -> tuple[bool, str]:
        """验证凭证借贷平衡"""
        diff = abs(voucher.total_debit - voucher.total_credit)
        if diff > 0.01:
            return False, f"借贷不平：借方¥{voucher.total_debit:.2f}，贷方¥{voucher.total_credit:.2f}，差额¥{diff:.2f}"
        if not voucher.entries:
            return False, "凭证无分录"
        return True, "OK"

    def lookup_account(self, code: str) -> tuple[str, AccountCategory]:
        """查询科目"""
        if code in CHART_OF_ACCOUNTS:
            return CHART_OF_ACCOUNTS[code]
        return ("未知科目", AccountCategory.EXPENSE)

    @staticmethod
    def list_all_accounts() -> dict:
        """列出所有可用科目"""
        return dict(CHART_OF_ACCOUNTS)
