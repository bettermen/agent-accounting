"""
数据模型 - 代理记账核心数据结构
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Optional


class InvoiceType(Enum):
    """票据类型"""
    VAT_SPECIAL = "增值税专用发票"
    VAT_NORMAL = "增值税普通发票"
    VAT_ELECTRONIC = "增值税电子发票"
    QUOTA_INVOICE = "定额发票"
    MACHINE_INVOICE = "机打发票"
    BANK_RECEIPT = "银行回单"
    BANK_STATEMENT = "银行流水"
    TRAIN_TICKET = "火车票"
    FLIGHT_ITINERARY = "飞机行程单"
    TAXI_RECEIPT = "出租车票"
    RIDE_HAILING = "网约车行程单"
    EXPRESS_FEE = "快递费发票"
    OTHER = "其他票据"


class Direction(Enum):
    """借贷方向"""
    DEBIT = "借"
    CREDIT = "贷"


class AccountCategory(Enum):
    """会计科目大类"""
    ASSET = "资产类"
    LIABILITY = "负债类"
    EQUITY = "所有者权益类"
    COST = "成本类"
    REVENUE = "损益-收入类"
    EXPENSE = "损益-费用类"


class ReportType(Enum):
    """报表类型"""
    BALANCE_SHEET = "资产负债表"
    INCOME_STATEMENT = "利润表"
    CASH_FLOW = "现金流量表"
    TAX_RETURN_VAT = "增值税申报表"
    TAX_RETURN_INCOME = "企业所得税申报表"
    TAX_RETURN_STAMP = "印花税申报表"


@dataclass
class Invoice:
    """票据数据结构"""
    id: str
    invoice_type: InvoiceType
    invoice_code: str = ""
    invoice_number: str = ""
    invoice_date: Optional[date] = None
    seller_name: str = ""
    buyer_name: str = ""
    amount: float = 0.0
    tax_amount: float = 0.0
    total_amount: float = 0.0
    items: list = field(default_factory=list)
    raw_text: str = ""
    confidence: float = 0.0
    image_path: str = ""
    source: str = "local_rule"   # local_rule / baidu_ocr_api / baidu_ocr_vat_api / local_rule_fallback
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class AccountingEntry:
    """会计分录"""
    id: str
    voucher_id: str
    line_no: int
    account_code: str        # 科目编码
    account_name: str        # 科目名称
    direction: Direction
    amount: float
    summary: str = ""
    invoice_id: str = ""


@dataclass
class Voucher:
    """记账凭证"""
    id: str
    voucher_date: date
    voucher_type: str = "记"       # 记/收/付/转
    voucher_number: int = 0
    company_id: str = ""
    entries: list = field(default_factory=list)   # list[AccountingEntry]
    total_debit: float = 0.0
    total_credit: float = 0.0
    attachments: int = 0
    maker: str = "AI"
    reviewer: str = ""
    status: str = "draft"         # draft/reviewed/posted
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class Company:
    """被代账企业"""
    id: str
    name: str
    tax_id: str                 # 统一社会信用代码
    taxpayer_type: str          # 一般纳税人/小规模纳税人
    industry: str = ""
    accounting_period: str = "monthly"
    registered_capital: float = 0.0
    contact_person: str = ""
    contact_phone: str = ""


@dataclass
class AccountBalance:
    """科目余额"""
    account_code: str
    account_name: str
    category: AccountCategory
    debit_amount: float = 0.0
    credit_amount: float = 0.0
    direction: Direction = Direction.DEBIT
    period: str = ""            # YYYY-MM


@dataclass
class RiskAlert:
    """风险预警"""
    id: str
    company_id: str
    risk_type: str              # 零申报/逾期未报/税负异常/发票异常
    severity: str               # high/medium/low
    description: str
    suggestion: str
    detected_at: datetime = field(default_factory=datetime.now)
    resolved: bool = False
