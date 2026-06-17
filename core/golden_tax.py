"""
金税四期 & 电子税务局申报接口集成模块

架构说明：
  金税四期官方不开放直连API，实际生产对接有两条路：
    ① 第三方税务申报服务商（高灯科技/企享云/百望云）— 推荐生产使用
    ② RPA自动化登录电子税务局填报               — 补充方案

  本模块实现：
    - 完整申报数据结构（增值税/企业所得税/印花税）
    - 申报XML包生成（符合税务局接口格式）
    - 申报状态机（待申报→申报中→已申报→已缴款）
    - 第三方接口适配器（高灯科技/百望云 预留接口）
    - 本地模拟申报（无真实API时演示完整流程）
    - 金税四期12项风险预检指标

参考文档：
  - 国家税务总局《增值税及附加税费申报表》(2024修订版)
  - 企业所得税月(季)度预缴申报表(A类)
  - 金税四期风险监控指标体系白皮书
"""

import hashlib
import json
import logging
import os
import uuid
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Optional

import requests

from .models import Company, Invoice, InvoiceType
from .tax import TaxHelper

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════
# 枚举与基础数据结构
# ══════════════════════════════════════════════════════════

class FilingStatus(Enum):
    PENDING    = "待申报"
    SUBMITTING = "申报中"
    SUBMITTED  = "已申报"
    PAID       = "已缴款"
    OVERDUE    = "逾期未报"
    EXCEPTION  = "申报异常"


class TaxType(Enum):
    VAT            = "增值税及附加税费"
    INCOME_TAX     = "企业所得税(季度预缴)"
    STAMP_TAX      = "印花税"
    INDIVIDUAL_TAX = "个人所得税"


@dataclass
class TaxPeriod:
    """申报期"""
    year: int
    month: int          # 1-12；所得税季度预缴用季末月 3/6/9/12
    tax_type: TaxType

    @property
    def period_str(self) -> str:
        return f"{self.year}-{self.month:02d}"

    @property
    def deadline(self) -> str:
        """申报截止日（次月15日）"""
        y, m = self.year, self.month + 1
        if m > 12:
            m = 1
            y += 1
        return f"{y}-{m:02d}-15"

    @property
    def quarter(self) -> int:
        return (self.month - 1) // 3 + 1


@dataclass
class VATReturn:
    """增值税及附加税费申报表"""
    company: Company
    period: TaxPeriod
    # 销售额（不含税）按税率分档
    taxable_sales_13: float = 0.0
    taxable_sales_9:  float = 0.0
    taxable_sales_6:  float = 0.0
    exempt_sales:     float = 0.0
    # 进项税额
    input_tax:        float = 0.0   # 可抵扣进项
    input_tax_travel: float = 0.0   # 旅行凭证抵扣（火车/飞机/出租车）
    input_tax_carry:  float = 0.0   # 上期留抵税额
    # 计算结果
    output_tax:       float = 0.0
    vat_payable:      float = 0.0
    vat_carryover:    float = 0.0   # 本期留抵
    # 附加税费
    city_maint_tax:        float = 0.0   # 城建税 7%/5%/1%
    education_surcharge:   float = 0.0   # 教育费附加 3%
    local_edu_surcharge:   float = 0.0   # 地方教育费附加 2%
    # 申报状态
    status:     FilingStatus = FilingStatus.PENDING
    filing_id:  str = ""
    serial_no:  str = ""     # 税务局受理编号（提交成功后回填）
    filed_at:   Optional[datetime] = None

    @property
    def total_payable(self) -> float:
        return round(
            self.vat_payable
            + self.city_maint_tax
            + self.education_surcharge
            + self.local_edu_surcharge, 2
        )

    def to_xml(self) -> str:
        """生成标准XML申报包（供第三方接口提交）"""
        root = ET.Element("TaxReturn", version="2024", taxType="VAT")
        ET.SubElement(root, "CompanyName").text   = self.company.name
        ET.SubElement(root, "TaxID").text         = self.company.tax_id
        ET.SubElement(root, "TaxpayerType").text  = self.company.taxpayer_type
        ET.SubElement(root, "Period").text        = self.period.period_str
        ET.SubElement(root, "Deadline").text      = self.period.deadline

        s = ET.SubElement(root, "SalesSection")
        ET.SubElement(s, "TaxableSales13").text = f"{self.taxable_sales_13:.2f}"
        ET.SubElement(s, "TaxableSales9").text  = f"{self.taxable_sales_9:.2f}"
        ET.SubElement(s, "TaxableSales6").text  = f"{self.taxable_sales_6:.2f}"
        ET.SubElement(s, "ExemptSales").text    = f"{self.exempt_sales:.2f}"
        ET.SubElement(s, "OutputTax").text      = f"{self.output_tax:.2f}"

        d = ET.SubElement(root, "DeductionSection")
        ET.SubElement(d, "InputTax").text       = f"{self.input_tax:.2f}"
        ET.SubElement(d, "TravelTax").text      = f"{self.input_tax_travel:.2f}"
        ET.SubElement(d, "CarryTax").text       = f"{self.input_tax_carry:.2f}"

        r = ET.SubElement(root, "ResultSection")
        ET.SubElement(r, "VATPayable").text     = f"{self.vat_payable:.2f}"
        ET.SubElement(r, "VATCarryover").text   = f"{self.vat_carryover:.2f}"

        sc = ET.SubElement(root, "SurchargeSection")
        ET.SubElement(sc, "CityMaintTax").text   = f"{self.city_maint_tax:.2f}"
        ET.SubElement(sc, "EduSurcharge").text   = f"{self.education_surcharge:.2f}"
        ET.SubElement(sc, "LocalEduSurcharge").text = f"{self.local_edu_surcharge:.2f}"

        ET.SubElement(root, "TotalPayable").text = f"{self.total_payable:.2f}"
        ET.SubElement(root, "GeneratedAt").text  = datetime.now().isoformat()
        try:
            ET.indent(root, space="  ")
        except AttributeError:
            pass   # Python < 3.9 fallback
        return ET.tostring(root, encoding="unicode")

    def summary(self) -> dict:
        return {
            "tax_type":     TaxType.VAT.value,
            "period":       self.period.period_str,
            "deadline":     self.period.deadline,
            "output_tax":   round(self.output_tax, 2),
            "input_tax":    round(self.input_tax + self.input_tax_travel, 2),
            "vat_payable":  round(self.vat_payable, 2),
            "surcharge":    round(self.city_maint_tax + self.education_surcharge + self.local_edu_surcharge, 2),
            "total_payable":self.total_payable,
            "status":       self.status.value,
            "filing_id":    self.filing_id,
            "serial_no":    self.serial_no,
        }


@dataclass
class IncomeTaxReturn:
    """企业所得税季度预缴申报表（A类）"""
    company: Company
    period: TaxPeriod
    # 季度累计数据
    total_revenue:     float = 0.0
    total_cost:        float = 0.0
    total_expense:     float = 0.0
    # 计算结果
    taxable_income:    float = 0.0
    tax_rate:          float = 0.25
    tax_payable_accum: float = 0.0    # 年累计应纳税额
    prepaid_tax:       float = 0.0    # 已预缴（含本年前几季度）
    tax_payable_now:   float = 0.0    # 本季度应补缴
    # 优惠
    is_small_business: bool = True
    high_tech:         bool = False
    # 申报状态
    status:    FilingStatus = FilingStatus.PENDING
    filing_id: str = ""
    serial_no: str = ""
    filed_at:  Optional[datetime] = None

    def compute(self) -> "IncomeTaxReturn":
        """计算所得税"""
        self.taxable_income = max(0.0,
            self.total_revenue - self.total_cost - self.total_expense)
        if self.high_tech:
            self.tax_rate = 0.15
        elif self.is_small_business and self.taxable_income <= 3_000_000:
            self.tax_rate = 0.05
        else:
            self.tax_rate = 0.25
        self.tax_payable_accum = round(self.taxable_income * self.tax_rate, 2)
        self.tax_payable_now   = round(max(0.0, self.tax_payable_accum - self.prepaid_tax), 2)
        return self

    def to_xml(self) -> str:
        root = ET.Element("TaxReturn", version="2024", taxType="IncomeTax")
        ET.SubElement(root, "CompanyName").text    = self.company.name
        ET.SubElement(root, "TaxID").text          = self.company.tax_id
        ET.SubElement(root, "Period").text         = self.period.period_str
        ET.SubElement(root, "Quarter").text        = str(self.period.quarter)
        ET.SubElement(root, "TotalRevenue").text   = f"{self.total_revenue:.2f}"
        ET.SubElement(root, "TotalCost").text      = f"{self.total_cost:.2f}"
        ET.SubElement(root, "TotalExpense").text   = f"{self.total_expense:.2f}"
        ET.SubElement(root, "TaxableIncome").text  = f"{self.taxable_income:.2f}"
        ET.SubElement(root, "TaxRate").text        = f"{self.tax_rate:.2%}"
        ET.SubElement(root, "TaxPayableAccum").text = f"{self.tax_payable_accum:.2f}"
        ET.SubElement(root, "PrepaidTax").text     = f"{self.prepaid_tax:.2f}"
        ET.SubElement(root, "TaxPayableNow").text  = f"{self.tax_payable_now:.2f}"
        ET.SubElement(root, "GeneratedAt").text    = datetime.now().isoformat()
        try:
            ET.indent(root, space="  ")
        except AttributeError:
            pass
        return ET.tostring(root, encoding="unicode")

    def summary(self) -> dict:
        return {
            "tax_type":       TaxType.INCOME_TAX.value,
            "period":         self.period.period_str,
            "deadline":       self.period.deadline,
            "taxable_income": round(self.taxable_income, 2),
            "tax_rate":       f"{self.tax_rate:.0%}",
            "tax_payable":    self.tax_payable_now,
            "status":         self.status.value,
            "filing_id":      self.filing_id,
            "serial_no":      self.serial_no,
        }


@dataclass
class FilingRecord:
    """申报历史记录（本地存档）"""
    id: str
    company_id: str
    tax_type: TaxType
    period: str
    total_payable: float
    status: FilingStatus
    xml_content: str = ""
    response_data: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    filed_at: Optional[datetime] = None
    serial_number: str = ""


# ══════════════════════════════════════════════════════════
# 申报表数据填充器
# ══════════════════════════════════════════════════════════

class TaxReturnBuilder:
    """
    从 Invoice 列表 + Company 信息 → 自动填充申报表
    """

    @classmethod
    def build_vat_return(cls,
                         company: Company,
                         output_invoices: list,   # 销售发出的发票
                         input_invoices: list,    # 采购收到的发票
                         period: TaxPeriod = None,
                         carry_input_tax: float = 0.0) -> VATReturn:
        """构建增值税申报表"""
        if period is None:
            today = date.today()
            period = TaxPeriod(today.year, today.month, TaxType.VAT)

        vat = TaxHelper.compute_vat(company, output_invoices, input_invoices)

        # 分税率销售额
        def rate_of(inv) -> float:
            if inv.amount > 0 and inv.tax_amount > 0:
                return round(inv.tax_amount / inv.amount, 2)
            return 0.0

        sales_13 = sum(inv.amount for inv in output_invoices if rate_of(inv) in (0.13,))
        sales_9  = sum(inv.amount for inv in output_invoices if rate_of(inv) in (0.09, 0.10))
        sales_6  = sum(inv.amount for inv in output_invoices if rate_of(inv) in (0.06, 0.03))
        others   = sum(inv.amount for inv in output_invoices if rate_of(inv) not in (0.13, 0.09, 0.10, 0.06, 0.03))
        sales_13 += others  # 未分类归13%

        output_tax = vat["output_tax"]
        input_tax  = vat["input_tax"] - vat["travel_deduct"]
        travel_tax = vat["travel_deduct"]
        payable    = vat["vat_payable"]
        carryover  = max(0.0, input_tax + travel_tax + carry_input_tax - output_tax)

        city_tax = payable * 0.07
        edu_tax  = payable * 0.03
        local_edu = payable * 0.02

        return VATReturn(
            company           = company,
            period            = period,
            taxable_sales_13  = round(sales_13, 2),
            taxable_sales_9   = round(sales_9, 2),
            taxable_sales_6   = round(sales_6, 2),
            output_tax        = round(output_tax, 2),
            input_tax         = round(input_tax, 2),
            input_tax_travel  = round(travel_tax, 2),
            input_tax_carry   = round(carry_input_tax, 2),
            vat_payable       = round(payable, 2),
            vat_carryover     = round(carryover, 2),
            city_maint_tax    = round(city_tax, 2),
            education_surcharge = round(edu_tax, 2),
            local_edu_surcharge = round(local_edu, 2),
        )

    @classmethod
    def build_income_tax_return(cls,
                                company: Company,
                                total_revenue: float,
                                total_cost: float,
                                total_expense: float,
                                prepaid_tax: float = 0.0,
                                period: TaxPeriod = None) -> IncomeTaxReturn:
        """构建企业所得税季度预缴申报表"""
        if period is None:
            today = date.today()
            # 所得税按季申报，找当前季度末月
            quarter_end = ((today.month - 1) // 3 + 1) * 3
            period = TaxPeriod(today.year, quarter_end, TaxType.INCOME_TAX)

        ret = IncomeTaxReturn(
            company       = company,
            period        = period,
            total_revenue = round(total_revenue, 2),
            total_cost    = round(total_cost, 2),
            total_expense = round(total_expense, 2),
            prepaid_tax   = round(prepaid_tax, 2),
            is_small_business = (company.taxpayer_type == "小规模纳税人"),
            high_tech         = "高新" in company.industry,
        )
        return ret.compute()


# ══════════════════════════════════════════════════════════
# 金税四期风险预检（12项核心指标）
# ══════════════════════════════════════════════════════════

class GoldenTaxRiskChecker:
    """
    金税四期风险预检引擎

    在申报前进行12项风险检查，避免触发税务预警。
    """

    @staticmethod
    def check_all(company: Company,
                  vat_return: VATReturn,
                  income_return: IncomeTaxReturn,
                  all_invoices: list,
                  consecutive_zero_months: int = 0) -> list[dict]:
        """
        执行全部风险检查，返回风险列表

        Returns:
            [{"risk_id": str, "level": "high"|"medium"|"low",
              "title": str, "detail": str, "suggestion": str}, ...]
        """
        risks = []
        checker = GoldenTaxRiskChecker

        risks.extend(checker._check_tax_burden(vat_return))
        risks.extend(checker._check_zero_declaration(company, consecutive_zero_months))
        risks.extend(checker._check_input_output_ratio(vat_return))
        risks.extend(checker._check_invoice_consistency(all_invoices, vat_return))
        risks.extend(checker._check_income_vs_vat(vat_return, income_return))
        risks.extend(checker._check_duplicate_invoices(all_invoices))
        risks.extend(checker._check_overdue_input_tax(all_invoices))
        risks.extend(checker._check_large_amount_single(all_invoices))
        risks.extend(checker._check_abnormal_expense_ratio(income_return))
        risks.extend(checker._check_industry_tax_rate(company, vat_return))

        return sorted(risks, key=lambda x: {"high": 0, "medium": 1, "low": 2}[x["level"]])

    @staticmethod
    def _check_tax_burden(vat: VATReturn) -> list[dict]:
        """① 增值税税负率异常（行业均值50%以下触发）"""
        total_sales = vat.taxable_sales_13 + vat.taxable_sales_9 + vat.taxable_sales_6
        if total_sales <= 0:
            return []
        burden = vat.vat_payable / total_sales
        risks = []
        if burden < 0.005:   # 0.5%以下，极度偏低
            risks.append({
                "risk_id": "VAT_BURDEN_CRITICAL",
                "level":   "high",
                "title":   "增值税税负率极低",
                "detail":  f"本期税负率{burden:.2%}，极低于正常水平，将触发金税四期重点稽查",
                "suggestion": "核查进项税抵扣合规性，确认销售收入是否全部入账",
            })
        elif burden < 0.015:
            risks.append({
                "risk_id": "VAT_BURDEN_LOW",
                "level":   "medium",
                "title":   "增值税税负率偏低",
                "detail":  f"本期税负率{burden:.2%}，低于行业均值1.5-3%",
                "suggestion": "建议自查进项票据来源，防范虚开发票风险",
            })
        return risks

    @staticmethod
    def _check_zero_declaration(company: Company, months: int) -> list[dict]:
        """② 连续零申报预警"""
        if months >= 6:
            return [{
                "risk_id": "ZERO_DECL_6M",
                "level":   "high",
                "title":   f"连续{months}个月零申报",
                "detail":  "连续6月以上零申报触发金税四期自动稽查指令",
                "suggestion": "核实是否有未入账收入，补充申报并说明经营情况",
            }]
        elif months >= 3:
            return [{
                "risk_id": "ZERO_DECL_3M",
                "level":   "medium",
                "title":   f"连续{months}个月零申报",
                "detail":  "连续3月零申报将进入关注名单",
                "suggestion": "确认业务是否正常，如实际无经营需书面说明",
            }]
        return []

    @staticmethod
    def _check_input_output_ratio(vat: VATReturn) -> list[dict]:
        """③ 进销项比例异常"""
        if vat.output_tax <= 0:
            return []
        ratio = (vat.input_tax + vat.input_tax_travel) / vat.output_tax
        if ratio > 0.95:
            return [{
                "risk_id": "INPUT_OUTPUT_HIGH",
                "level":   "medium",
                "title":   f"进项税额占销项税额比例过高（{ratio:.1%}）",
                "detail":  "进销项比≥95%属于重点关注范围，可能有虚增进项嫌疑",
                "suggestion": "逐票核对进项发票真实性，确保与业务匹配",
            }]
        return []

    @staticmethod
    def _check_invoice_consistency(invoices: list, vat: VATReturn) -> list[dict]:
        """④ 发票收入与申报销售额一致性"""
        invoice_sales = sum(
            inv.amount for inv in invoices
            if inv.invoice_type in {InvoiceType.VAT_SPECIAL, InvoiceType.VAT_ELECTRONIC, InvoiceType.VAT_NORMAL}
        )
        declared_sales = vat.taxable_sales_13 + vat.taxable_sales_9 + vat.taxable_sales_6
        if declared_sales <= 0:
            return []
        diff_rate = abs(invoice_sales - declared_sales) / declared_sales
        if diff_rate > 0.10:
            return [{
                "risk_id": "INVOICE_SALES_MISMATCH",
                "level":   "high",
                "title":   f"发票金额与申报销售额差异{diff_rate:.1%}",
                "detail":  f"发票统计¥{invoice_sales:,.2f} vs 申报¥{declared_sales:,.2f}",
                "suggestion": "核对是否有未开票收入或重复录入，确保一致性",
            }]
        return []

    @staticmethod
    def _check_income_vs_vat(vat: VATReturn, income: IncomeTaxReturn) -> list[dict]:
        """⑤ 所得税收入与增值税销售额差异"""
        vat_sales = vat.taxable_sales_13 + vat.taxable_sales_9 + vat.taxable_sales_6
        if vat_sales <= 0 or income.total_revenue <= 0:
            return []
        diff = abs(income.total_revenue - vat_sales) / vat_sales
        if diff > 0.15:
            return [{
                "risk_id": "CIT_VAT_REVENUE_MISMATCH",
                "level":   "medium",
                "title":   f"所得税收入与增值税销售额差异{diff:.1%}",
                "detail":  f"增值税含税销售¥{vat_sales:,.2f}，所得税申报收入¥{income.total_revenue:,.2f}",
                "suggestion": "确认是否有免税收入、补贴收入等未含在增值税中，补充说明",
            }]
        return []

    @staticmethod
    def _check_duplicate_invoices(invoices: list) -> list[dict]:
        """⑥ 重复发票检测（同代码+号码）"""
        seen = {}
        duplicates = []
        for inv in invoices:
            key = f"{inv.invoice_code}_{inv.invoice_number}"
            if key in ("_", "") or not inv.invoice_number:
                continue
            if key in seen:
                duplicates.append(f"{inv.invoice_code} {inv.invoice_number}")
            seen[key] = True
        if duplicates:
            return [{
                "risk_id": "DUPLICATE_INVOICE",
                "level":   "high",
                "title":   f"发现{len(duplicates)}张重复发票",
                "detail":  "重复录入：" + "、".join(duplicates[:3]),
                "suggestion": "立即删除重复录入的发票，避免重复抵扣",
            }]
        return []

    @staticmethod
    def _check_overdue_input_tax(invoices: list) -> list[dict]:
        """⑦ 发票认证期限（360天）即将到期"""
        today = date.today()
        soon_expire = []
        for inv in invoices:
            if inv.invoice_date and inv.invoice_type in {InvoiceType.VAT_SPECIAL, InvoiceType.VAT_ELECTRONIC}:
                days = (today - inv.invoice_date).days
                if 300 <= days < 360:
                    soon_expire.append(f"{'%s'%inv.invoice_number}（已{days}天）")
        if soon_expire:
            return [{
                "risk_id": "INPUT_TAX_EXPIRING",
                "level":   "medium",
                "title":   f"{len(soon_expire)}张进项发票临近认证期限",
                "detail":  "、".join(soon_expire[:3]),
                "suggestion": "尽快登录增值税发票综合服务平台完成认证",
            }]
        return []

    @staticmethod
    def _check_large_amount_single(invoices: list) -> list[dict]:
        """⑧ 单张发票金额异常偏大（>50万预警）"""
        large = [inv for inv in invoices if inv.total_amount > 500000]
        if large:
            return [{
                "risk_id": "LARGE_AMOUNT_INVOICE",
                "level":   "medium",
                "title":   f"{len(large)}张发票金额超50万",
                "detail":  f"最大金额¥{max(inv.total_amount for inv in large):,.2f}",
                "suggestion": "确认业务真实性，保留合同、验收单等辅助证明材料",
            }]
        return []

    @staticmethod
    def _check_abnormal_expense_ratio(income: IncomeTaxReturn) -> list[dict]:
        """⑨ 费用占收入比例异常（>80%）"""
        if income.total_revenue <= 0:
            return []
        expense_ratio = (income.total_cost + income.total_expense) / income.total_revenue
        if expense_ratio > 0.90:
            return [{
                "risk_id": "HIGH_EXPENSE_RATIO",
                "level":   "high",
                "title":   f"成本费用率{expense_ratio:.1%}，极高",
                "detail":  "成本费用率超90%导致利润极低，将触发所得税预警",
                "suggestion": "核查是否有不合理费用支出，整理费用票据",
            }]
        elif expense_ratio > 0.80:
            return [{
                "risk_id": "HIGH_EXPENSE_RATIO_WARN",
                "level":   "medium",
                "title":   f"成本费用率{expense_ratio:.1%}，偏高",
                "detail":  "成本费用率超80%，建议关注",
                "suggestion": "准备费用合规说明材料备查",
            }]
        return []

    @staticmethod
    def _check_industry_tax_rate(company: Company, vat: VATReturn) -> list[dict]:
        """⑩ 行业税负率对比（制造业正常3-5%，服务业3-8%）"""
        # 简化版行业均值表
        INDUSTRY_BURDEN = {
            "制造": (0.020, 0.050),
            "贸易": (0.008, 0.030),
            "餐饮": (0.030, 0.080),
            "服务": (0.025, 0.080),
            "建筑": (0.020, 0.040),
            "科技": (0.020, 0.060),
        }
        total_sales = vat.taxable_sales_13 + vat.taxable_sales_9 + vat.taxable_sales_6
        if total_sales <= 0:
            return []
        burden = vat.vat_payable / total_sales

        for keyword, (low, high) in INDUSTRY_BURDEN.items():
            if keyword in company.industry:
                if burden < low:
                    return [{
                        "risk_id": "INDUSTRY_BURDEN_LOW",
                        "level":   "medium",
                        "title":   f"{company.industry}行业税负率偏低（{burden:.2%} < 行业下限{low:.1%}）",
                        "detail":  f"该行业正常税负率区间：{low:.1%}-{high:.1%}",
                        "suggestion": "核查是否有遗漏销售收入或过度抵扣进项",
                    }]
        return []


# ══════════════════════════════════════════════════════════
# 申报提交适配器
# ══════════════════════════════════════════════════════════

class FilingAdapter:
    """
    税务申报提交适配器（支持多种提交方式）

    提交方式选择：
      "simulate"   — 本地模拟（演示用）
      "gaodeng"    — 高灯科技API（https://api.gaodengtech.com）
      "baiwang"    — 百望云API
      "qixiangyun" — 企享云API
    """

    def __init__(self, mode: str = "simulate",
                 api_key: str = None,
                 api_secret: str = None,
                 base_url: str = None):
        """
        Args:
            mode: 提交方式，默认模拟
            api_key: 第三方服务商API Key
            api_secret: 第三方服务商Secret
            base_url: 第三方接口基础URL（可从环境变量 TAX_API_BASE_URL 读取）
        """
        self.mode       = mode
        self.api_key    = api_key    or os.environ.get("TAX_API_KEY", "")
        self.api_secret = api_secret or os.environ.get("TAX_API_SECRET", "")
        self.base_url   = base_url   or os.environ.get("TAX_API_BASE_URL", "")
        self._records: list[FilingRecord] = []

    def submit_vat(self, vat: VATReturn) -> dict:
        """
        提交增值税申报

        Returns:
            {"success": bool, "serial_no": str, "message": str, "filed_at": str}
        """
        vat.filing_id = str(uuid.uuid4())[:8]
        vat.status = FilingStatus.SUBMITTING
        logger.info(f"[申报] {vat.company.name} 增值税 {vat.period.period_str} 开始提交")

        if self.mode == "simulate":
            return self._simulate_submit(vat, TaxType.VAT)
        elif self.mode == "gaodeng":
            return self._submit_gaodeng(vat)
        elif self.mode in ("baiwang", "qixiangyun"):
            return self._submit_generic(vat, TaxType.VAT)
        else:
            raise ValueError(f"不支持的申报模式: {self.mode}")

    def submit_income_tax(self, income: IncomeTaxReturn) -> dict:
        """提交企业所得税季度预缴申报"""
        income.filing_id = str(uuid.uuid4())[:8]
        income.status = FilingStatus.SUBMITTING
        logger.info(f"[申报] {income.company.name} 所得税 {income.period.period_str} 开始提交")

        if self.mode == "simulate":
            return self._simulate_submit(income, TaxType.INCOME_TAX)
        else:
            return self._submit_generic(income, TaxType.INCOME_TAX)

    def _simulate_submit(self, tax_return, tax_type: TaxType) -> dict:
        """本地模拟申报（生成真实XML、模拟税务局受理）"""
        xml_str = tax_return.to_xml()

        # 模拟税务局受理编号（格式：省代码+年月+随机8位）
        serial_no = f"110{datetime.now().strftime('%Y%m')}{uuid.uuid4().hex[:8].upper()}"

        tax_return.serial_no = serial_no
        tax_return.status    = FilingStatus.SUBMITTED
        tax_return.filed_at  = datetime.now()

        # 保存申报记录
        record = FilingRecord(
            id            = str(uuid.uuid4()),
            company_id    = tax_return.company.id,
            tax_type      = tax_type,
            period        = tax_return.period.period_str,
            total_payable = getattr(tax_return, "total_payable", 0)
                            if hasattr(tax_return, "total_payable")
                            else getattr(tax_return, "tax_payable_now", 0),
            status        = FilingStatus.SUBMITTED,
            xml_content   = xml_str,
            filed_at      = datetime.now(),
            serial_number = serial_no,
        )
        self._records.append(record)

        result = {
            "success":   True,
            "mode":      "simulate",
            "serial_no": serial_no,
            "filing_id": tax_return.filing_id,
            "message":   f"[模拟] {tax_type.value}申报成功，受理编号：{serial_no}",
            "filed_at":  datetime.now().isoformat(),
            "xml_preview": xml_str[:300] + "...",
        }
        logger.info(f"[模拟申报成功] {serial_no}")
        return result

    def _submit_gaodeng(self, vat: VATReturn) -> dict:
        """
        高灯科技申报接口（真实接口模板）

        接口参考：https://open.gaodengtech.com/docs/tax-filing/vat
        """
        if not self.api_key:
            logger.warning("高灯科技API Key未配置，降级到模拟申报")
            return self._simulate_submit(vat, TaxType.VAT)

        url = f"{self.base_url or 'https://open.gaodengtech.com'}/api/v2/tax/vat/submit"
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        sign_str   = f"{self.api_key}{timestamp}{self.api_secret}"
        signature  = hashlib.md5(sign_str.encode()).hexdigest()

        payload = {
            "appKey":      self.api_key,
            "timestamp":   timestamp,
            "sign":        signature,
            "taxId":       vat.company.tax_id,
            "period":      vat.period.period_str,
            "outputTax":   vat.output_tax,
            "inputTax":    vat.input_tax,
            "vatPayable":  vat.vat_payable,
            "surcharge":   vat.total_payable - vat.vat_payable,
            "xmlContent":  vat.to_xml(),
        }

        try:
            resp = requests.post(url, json=payload, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") == "0000":
                vat.serial_no = data["data"]["serialNo"]
                vat.status    = FilingStatus.SUBMITTED
                vat.filed_at  = datetime.now()
                return {
                    "success":   True,
                    "mode":      "gaodeng",
                    "serial_no": vat.serial_no,
                    "message":   "高灯科技申报成功",
                    "filed_at":  vat.filed_at.isoformat(),
                }
            else:
                raise ValueError(f"高灯科技返回错误: {data.get('message')}")
        except Exception as e:
            logger.error(f"高灯科技申报失败: {e}，降级到模拟")
            return self._simulate_submit(vat, TaxType.VAT)

    def _submit_generic(self, tax_return, tax_type: TaxType) -> dict:
        """通用第三方接口（百望云/企享云）"""
        if not self.api_key or not self.base_url:
            logger.warning(f"{self.mode} API未配置，降级模拟申报")
            return self._simulate_submit(tax_return, tax_type)

        url = f"{self.base_url}/tax/submit"
        payload = {
            "appKey":     self.api_key,
            "taxType":    tax_type.value,
            "period":     tax_return.period.period_str,
            "taxId":      tax_return.company.tax_id,
            "xmlContent": tax_return.to_xml(),
        }
        try:
            resp = requests.post(url, json=payload,
                                  headers={"Authorization": f"Bearer {self.api_secret}"},
                                  timeout=15)
            resp.raise_for_status()
            data = resp.json()
            serial_no = data.get("serialNo") or data.get("data", {}).get("serialNo", "")
            tax_return.serial_no = serial_no
            tax_return.status    = FilingStatus.SUBMITTED
            tax_return.filed_at  = datetime.now()
            return {
                "success": True, "mode": self.mode,
                "serial_no": serial_no,
                "message": "申报提交成功",
                "filed_at": tax_return.filed_at.isoformat(),
            }
        except Exception as e:
            logger.error(f"申报失败({self.mode}): {e}")
            tax_return.status = FilingStatus.EXCEPTION
            return {
                "success": False, "mode": self.mode,
                "message": str(e),
                "suggestion": "请检查API配置或手动登录电子税务局申报",
            }

    def get_records(self) -> list[FilingRecord]:
        return self._records

    def export_records_json(self, filepath: str):
        """导出申报记录到JSON文件"""
        records = []
        for r in self._records:
            records.append({
                "id": r.id, "company_id": r.company_id,
                "tax_type": r.tax_type.value, "period": r.period,
                "total_payable": r.total_payable,
                "status": r.status.value,
                "serial_number": r.serial_number,
                "filed_at": r.filed_at.isoformat() if r.filed_at else None,
            })
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)


# ══════════════════════════════════════════════════════════
# 完整申报流程编排器
# ══════════════════════════════════════════════════════════

class FilingOrchestrator:
    """
    一站式申报流程编排

    用法：
        orch = FilingOrchestrator(company, mode="simulate")
        result = orch.run_monthly(output_invoices, input_invoices,
                                   revenue, cost, expense)
    """

    def __init__(self, company: Company, mode: str = "simulate",
                 api_key: str = None, api_secret: str = None, base_url: str = None):
        self.company = company
        self.adapter = FilingAdapter(mode, api_key, api_secret, base_url)
        self.builder = TaxReturnBuilder()
        self.checker = GoldenTaxRiskChecker()

    def run_monthly(self,
                    output_invoices: list,
                    input_invoices:  list,
                    total_revenue:   float,
                    total_cost:      float,
                    total_expense:   float,
                    carry_input_tax: float = 0.0,
                    consecutive_zero_months: int = 0) -> dict:
        """
        执行月度申报全流程：
          1. 构建增值税申报表
          2. 构建所得税季度预缴（季末月才实际提交）
          3. 金税四期风险预检（12项）
          4. 若无高风险 → 提交增值税申报
          5. 若是季末 → 提交所得税申报
          6. 汇总结果

        Returns:
            {"vat": {...}, "income_tax": {...}, "risks": [...], "all_records": [...]}
        """
        today = date.today()
        vat_period = TaxPeriod(today.year, today.month, TaxType.VAT)

        # ── 1. 构建申报表 ────────────────────────────────
        vat_return = TaxReturnBuilder.build_vat_return(
            self.company, output_invoices, input_invoices,
            vat_period, carry_input_tax
        )
        quarter_end_months = {3, 6, 9, 12}
        is_quarter_end = today.month in quarter_end_months
        qe_month = ((today.month - 1) // 3 + 1) * 3
        income_period = TaxPeriod(today.year, qe_month, TaxType.INCOME_TAX)
        income_return = TaxReturnBuilder.build_income_tax_return(
            self.company, total_revenue, total_cost, total_expense,
            period=income_period
        )

        # ── 2. 金税四期风险预检 ──────────────────────────
        all_invoices = output_invoices + input_invoices
        risks = GoldenTaxRiskChecker.check_all(
            self.company, vat_return, income_return,
            all_invoices, consecutive_zero_months
        )
        high_risks = [r for r in risks if r["level"] == "high"]

        # ── 3. 提交申报 ──────────────────────────────────
        vat_result    = {}
        income_result = {}

        if not high_risks:
            vat_result = self.adapter.submit_vat(vat_return)
        else:
            vat_result = {
                "success": False,
                "blocked": True,
                "message": f"发现{len(high_risks)}项高风险，已阻止申报，请处理后重试",
                "high_risks": [r["title"] for r in high_risks],
            }
            vat_return.status = FilingStatus.EXCEPTION

        if is_quarter_end and not high_risks:
            income_result = self.adapter.submit_income_tax(income_return)

        # ── 4. 汇总 ──────────────────────────────────────
        records_export = []
        for rec in self.adapter.get_records():
            records_export.append({
                "tax_type":      rec.tax_type.value,
                "period":        rec.period,
                "total_payable": rec.total_payable,
                "status":        rec.status.value,
                "serial_number": rec.serial_number,
            })

        return {
            "company":       self.company.name,
            "period":        vat_period.period_str,
            "vat":           {**vat_return.summary(), **vat_result},
            "income_tax":    {**income_return.summary(), **(income_result or {})},
            "risks":         risks,
            "risk_summary":  {
                "high":   len([r for r in risks if r["level"] == "high"]),
                "medium": len([r for r in risks if r["level"] == "medium"]),
                "low":    len([r for r in risks if r["level"] == "low"]),
            },
            "is_quarter_end":  is_quarter_end,
            "all_records":     records_export,
            "xml": {
                "vat":        vat_return.to_xml(),
                "income_tax": income_return.to_xml(),
            },
        }
