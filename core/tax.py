"""
报税辅助模块
自动生成各税种申报数据，支持增值税、企业所得税、印花税等
"""

from datetime import date, datetime
from typing import Optional

from .models import AccountBalance, AccountCategory, Company, Invoice, InvoiceType


class TaxHelper:
    """报税辅助器"""

    # ============================================================
    # 增值税率表
    # ============================================================
    VAT_RATES = {
        "一般纳税人": {
            "default": 0.13,
            "服务": 0.06,
            "建筑": 0.09,
            "运输": 0.09,
            "农产品": 0.09,
        },
        "小规模纳税人": {
            "default": 0.01,  # 2026年现行优惠政策
            "出租": 0.05,
        },
    }

    # 企业所得税率
    INCOME_TAX_RATES = {
        "一般企业": 0.25,
        "小微企业": 0.05,  # 年应纳税所得额≤300万
        "高新企业": 0.15,
    }

    @classmethod
    def compute_vat(cls, company: Company,
                    output_invoices: list[Invoice],
                    input_invoices: list[Invoice]) -> dict:
        """
        计算增值税
        返回：销项税、进项税、应纳税额
        """
        # 销项税额（开出去的发票）
        output_tax = sum(inv.tax_amount for inv in output_invoices
                        if inv.invoice_type in {InvoiceType.VAT_SPECIAL, InvoiceType.VAT_ELECTRONIC})

        # 如果没有明细税额，用总额估算
        if output_tax == 0:
            rate = cls.VAT_RATES.get(company.taxpayer_type, {}).get("default", 0.13)
            output_tax = sum(inv.total_amount / (1 + rate) * rate
                           for inv in output_invoices
                           if inv.invoice_type in {InvoiceType.VAT_SPECIAL, InvoiceType.VAT_ELECTRONIC})

        # 进项税额（收到的发票）
        input_tax = sum(inv.tax_amount for inv in input_invoices)

        # 火车票/飞机票可抵扣
        travel_deduct = 0.0
        for inv in input_invoices:
            if inv.invoice_type == InvoiceType.TRAIN_TICKET:
                travel_deduct += inv.total_amount / 1.09 * 0.09
            elif inv.invoice_type == InvoiceType.FLIGHT_ITINERARY:
                travel_deduct += inv.total_amount / 1.09 * 0.09
            elif inv.invoice_type in {InvoiceType.TAXI_RECEIPT, InvoiceType.RIDE_HAILING}:
                travel_deduct += inv.total_amount / 1.03 * 0.03

        input_tax += travel_deduct
        payable = max(0, output_tax - input_tax)

        return {
            "company": company.name,
            "taxpayer_type": company.taxpayer_type,
            "period": f"{date.today().year}-{date.today().month:02d}",
            "output_tax": round(output_tax, 2),
            "input_tax": round(input_tax, 2),
            "travel_deduct": round(travel_deduct, 2),
            "vat_payable": round(payable, 2),
            "need_file": payable > 0,
        }

    @classmethod
    def compute_income_tax(cls, company: Company,
                           total_revenue: float,
                           total_cost: float,
                           total_expense: float,
                           adjustments: Optional[dict] = None) -> dict:
        """
        计算企业所得税
        """
        # 应纳税所得额
        taxable_income = total_revenue - total_cost - total_expense
        if adjustments:
            taxable_income += adjustments.get("add", 0)   # 纳税调增
            taxable_income -= adjustments.get("deduct", 0)  # 纳税调减

        taxable_income = max(0, taxable_income)

        # 确定适用税率
        if "高新" in company.industry:
            rate = cls.INCOME_TAX_RATES["高新企业"]
        elif taxable_income <= 3000000:  # 300万
            rate = cls.INCOME_TAX_RATES["小微企业"]
        else:
            rate = cls.INCOME_TAX_RATES["一般企业"]

        tax_payable = taxable_income * rate

        return {
            "company": company.name,
            "period": f"{date.today().year}",
            "total_revenue": round(total_revenue, 2),
            "total_cost": round(total_cost, 2),
            "total_expense": round(total_expense, 2),
            "taxable_income": round(taxable_income, 2),
            "tax_rate": rate,
            "tax_payable": round(tax_payable, 2),
            "need_file": tax_payable > 0,
        }

    @classmethod
    def compute_stamp_tax(cls, contract_amounts: dict[str, float]) -> dict:
        """
        计算印花税
        contract_amounts: {"购销合同": 100000, "借款合同": 500000, ...}
        """
        rates = {
            "购销合同": 0.0003,
            "加工承揽合同": 0.0005,
            "建设工程勘察设计合同": 0.0005,
            "建筑安装工程承包合同": 0.0003,
            "财产租赁合同": 0.001,
            "货物运输合同": 0.0005,
            "仓储保管合同": 0.001,
            "借款合同": 0.00005,
            "财产保险合同": 0.001,
            "技术合同": 0.0003,
        }

        total_tax = 0.0
        details = []

        for contract_type, amount in contract_amounts.items():
            rate = rates.get(contract_type, 0.0003)
            tax = amount * rate
            total_tax += tax
            details.append({
                "type": contract_type,
                "amount": amount,
                "rate": rate,
                "tax": round(tax, 2),
            })

        return {
            "period": f"{date.today().year}-{date.today().month:02d}",
            "total_stamp_tax": round(total_tax, 2),
            "details": details,
        }

    @classmethod
    def generate_tax_calendar(cls, company: Company) -> list[dict]:
        """生成月度报税日历"""
        today = date.today()
        return [
            {"tax_type": "增值税", "deadline": f"{today.year}-{today.month:02d}-15",
             "period": "月度", "priority": "high"},
            {"tax_type": "个人所得税", "deadline": f"{today.year}-{today.month:02d}-15",
             "period": "月度", "priority": "high"},
            {"tax_type": "企业所得税(预缴)", "deadline": f"{today.year}-{today.month:02d}-15",
             "period": "季度", "priority": "medium"},
            {"tax_type": "印花税", "deadline": f"{today.year}-{today.month:02d}-15",
             "period": "月度/次", "priority": "low"},
            {"tax_type": "财务报表", "deadline": f"{today.year}-{today.month:02d}-15",
             "period": "月度", "priority": "medium"},
        ]

    @classmethod
    def check_zero_declaration_risk(cls, company: Company,
                                     consecutive_months: int) -> dict:
        """检查零申报风险"""
        if consecutive_months >= 6:
            return {
                "risk": "high",
                "message": f"已连续{consecutive_months}个月零申报，触发金税四期预警阈值",
                "suggestion": "核查是否有未确认收入，建议尽快确认收入并正常申报",
            }
        elif consecutive_months >= 3:
            return {
                "risk": "medium",
                "message": f"已连续{consecutive_months}个月零申报",
                "suggestion": "关注业务开展情况，避免异常零申报",
            }
        return {"risk": "low", "message": "零申报周期正常"}


class RiskEngine:
    """风险预警引擎"""

    @staticmethod
    def check_voucher_balance(vouchers) -> list[dict]:
        """检查凭证借贷平衡"""
        alerts = []
        for v in vouchers:
            diff = abs(v.total_debit - v.total_credit)
            if diff > 0.01:
                alerts.append({
                    "type": "凭证不平",
                    "severity": "high",
                    "voucher_id": v.id,
                    "voucher_number": v.voucher_number,
                    "message": f"凭证#{v.voucher_number} 借贷差额¥{diff:.2f}",
                })
        return alerts

    @staticmethod
    def check_overdue_tax(tax_deadlines: list[dict], completed: list[str]) -> list[dict]:
        """检查逾期未申报"""
        alerts = []
        for tax in tax_deadlines:
            if tax["tax_type"] not in completed:
                alerts.append({
                    "type": "逾期未报",
                    "severity": "high" if tax["priority"] == "high" else "medium",
                    "tax_type": tax["tax_type"],
                    "deadline": tax["deadline"],
                    "message": f"{tax['tax_type']} 截止 {tax['deadline']} 尚未申报",
                })
        return alerts

    @staticmethod
    def check_tax_burden_anomaly(vat_payable: float, total_revenue: float,
                                  industry_avg: float = 0.03) -> dict:
        """检查税负率异常"""
        if total_revenue <= 0:
            return {"type": "税负异常", "severity": "low", "message": "无收入，无法计算税负率"}

        burden = vat_payable / total_revenue
        if burden < industry_avg * 0.5:
            return {
                "type": "税负异常",
                "severity": "high",
                "message": f"增值税税负率{burden:.2%}，低于行业平均{industry_avg:.2%}的50%，可能触发税务预警",
                "suggestion": "核查进项税抵扣是否合规，确保销售收入全部确认",
            }
        elif burden < industry_avg * 0.8:
            return {
                "type": "税负偏低",
                "severity": "medium",
                "message": f"增值税税负率{burden:.2%}，低于行业平均{industry_avg:.2%}",
                "suggestion": "关注税负变化趋势",
            }
        return {"type": "税负正常", "severity": "low", "message": f"税负率{burden:.2%}，处于正常范围"}

    @staticmethod
    def check_invoice_expiry(invoices: list[Invoice]) -> list[dict]:
        """检查发票认证期限即将到期"""
        from datetime import date
        alerts = []
        today = date.today()
        for inv in invoices:
            if inv.invoice_date:
                days_since = (today - inv.invoice_date).days
                if inv.invoice_type in {InvoiceType.VAT_SPECIAL, InvoiceType.VAT_ELECTRONIC}:
                    if 300 <= days_since < 360:
                        alerts.append({
                            "type": "发票即将过期",
                            "severity": "medium",
                            "invoice": f"{inv.invoice_code} {inv.invoice_number}",
                            "message": f"进项发票已{days_since}天，临近360天认证期限",
                            "suggestion": "请尽快完成认证抵扣",
                        })
        return alerts
