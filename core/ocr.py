"""
票据OCR识别模块
支持：增值税发票、银行回单、火车票、行程单等多种票据的智能识别
依赖：百度OCR API 或 本地规则解析（降级方案）
"""

import json
import re
from datetime import date, datetime
from typing import Optional

from .models import Invoice, InvoiceType


class InvoiceOCR:
    """票据OCR识别引擎"""

    # 票据类型→科目映射规则（用于后续做账）
    TYPE_ACCOUNT_MAP = {
        InvoiceType.VAT_SPECIAL: {
            "debit": "1403/原材料（或对应科目）",
            "credit": "2202/应付账款",
            "tax_debit": "22210101/应交税费-应交增值税-进项税额",
        },
        InvoiceType.VAT_NORMAL: {
            "debit": "5602/管理费用",
            "credit": "1002/银行存款",
        },
        InvoiceType.VAT_ELECTRONIC: {
            "debit": "5602/管理费用",
            "credit": "1002/银行存款",
            "tax_debit": "22210101/应交税费-应交增值税-进项税额",
        },
        InvoiceType.TRAIN_TICKET: {
            "debit": "560207/管理费用-差旅费",
            "credit": "1001/库存现金",
        },
        InvoiceType.FLIGHT_ITINERARY: {
            "debit": "560207/管理费用-差旅费",
            "credit": "1001/库存现金",
        },
        InvoiceType.TAXI_RECEIPT: {
            "debit": "560207/管理费用-差旅费",
            "credit": "1001/库存现金",
        },
        InvoiceType.BANK_RECEIPT: {
            "debit": "1002/银行存款",
            "credit": "1122/应收账款（或其他）",
        },
        InvoiceType.QUOTA_INVOICE: {
            "debit": "5602/管理费用",
            "credit": "1001/库存现金",
        },
    }

    @staticmethod
    def classify_by_keywords(text: str) -> InvoiceType:
        """基于关键词分类票据类型"""
        text_upper = text.upper()
        patterns = [
            (r"增值税专用发票|专用发票|VAT.*SPECIAL", InvoiceType.VAT_SPECIAL),
            (r"增值税电子.*发票|电子发票|全电发票", InvoiceType.VAT_ELECTRONIC),
            (r"增值税普通发票|普通发票|增值税发票", InvoiceType.VAT_NORMAL),
            (r"定额发票|通用定额", InvoiceType.QUOTA_INVOICE),
            (r"机打发票|通用机打", InvoiceType.MACHINE_INVOICE),
            (r"火车票|铁路|TRAIN|车次", InvoiceType.TRAIN_TICKET),
            (r"航空运输电子客票|行程单|FLIGHT|航班", InvoiceType.FLIGHT_ITINERARY),
            (r"出租车|TAXI|出租车票", InvoiceType.TAXI_RECEIPT),
            (r"网约车|滴滴|行程单.*网约|RIDE.*HAIL", InvoiceType.RIDE_HAILING),
            (r"银行回单|付款回单|转账回单|电子回单", InvoiceType.BANK_RECEIPT),
            (r"银行.*流水|对账单|交易明细", InvoiceType.BANK_STATEMENT),
            (r"快递|物流.*发票|运费.*发票|EXPRESS", InvoiceType.EXPRESS_FEE),
        ]
        for pattern, inv_type in patterns:
            if re.search(pattern, text_upper):
                return inv_type
        return InvoiceType.OTHER

    @staticmethod
    def extract_amount(text: str) -> tuple[float, float]:
        """提取金额信息，返回 (不含税金额, 税额)"""
        # 匹配含"价税合计"、"合计金额"等关键词+金额的模式
        total_match = re.search(
            r"(?:价税合计|合计金额|大写合计|小写合计)[：:\s]*[¥￥]?\s*(\d[\d,]*\.?\d*)", text
        )
        tax_match = re.search(
            r"(?:税额|税金)[：:\s]*[¥￥]?\s*(\d[\d,]*\.?\d*)", text
        )
        amount_match = re.search(
            r"(?:不含税金额|金额|不含税)[：:\s]*[¥￥]?\s*(\d[\d,]*\.?\d*)", text
        )

        total = float(total_match.group(1).replace(",", "")) if total_match else 0.0
        tax = float(tax_match.group(1).replace(",", "")) if tax_match else 0.0
        amount = float(amount_match.group(1).replace(",", "")) if amount_match else max(0, total - tax)

        return amount, tax

    @staticmethod
    def extract_invoice_code_number(text: str) -> tuple[str, str]:
        """提取发票代码和号码"""
        code_match = re.search(r"发票代码[：:\s]*(\d{10,12})", text)
        number_match = re.search(r"发票号码[：:\s]*(\d{8})", text)
        # 备用：匹配"代码XXXX 号码XXXX"格式（无标签）
        if not code_match:
            code_match = re.search(r"(?:代码|code)[：:\s]*(\d{10,12})", text, re.IGNORECASE)
        if not number_match:
            number_match = re.search(r"(?:号码|number)[：:\s]*(\d{8})", text, re.IGNORECASE)
        return (
            code_match.group(1) if code_match else "",
            number_match.group(1) if number_match else "",
        )

    @staticmethod
    def extract_date(text: str) -> Optional[date]:
        """提取开票日期"""
        date_patterns = [
            r"开票日期[：:\s]*(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})",
            r"(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})[日号]",
        ]
        for pattern in date_patterns:
            m = re.search(pattern, text)
            if m:
                try:
                    return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                except ValueError:
                    pass
        return None

    @staticmethod
    def extract_company_names(text: str) -> tuple[str, str]:
        """提取销售方和购买方名称"""
        seller_match = re.search(r"销售方名称[：:\s]*([^\n]{2,40})", text)
        buyer_match = re.search(r"购买方名称[：:\s]*([^\n]{2,40})", text)

        # 备用：查找"名称:"后的公司名
        if not seller_match:
            name_matches = re.findall(r"名\s*称[：:]\s*([^\n]{2,40})", text)
            if len(name_matches) >= 2:
                return name_matches[1], name_matches[0]  # 第二组通常是销售方

        return (
            seller_match.group(1).strip() if seller_match else "",
            buyer_match.group(1).strip() if buyer_match else "",
        )

    def parse_text_to_invoice(self, raw_text: str, image_path: str = "") -> Invoice:
        """
        将OCR识别文本解析为Invoice对象（本地降级方案，无需API）
        """
        inv_type = self.classify_by_keywords(raw_text)
        amount, tax = self.extract_amount(raw_text)
        code, number = self.extract_invoice_code_number(raw_text)
        inv_date = self.extract_date(raw_text)
        seller, buyer = self.extract_company_names(raw_text)

        confidence = 0.85 if inv_type != InvoiceType.OTHER else 0.5
        if code and number:
            confidence = min(1.0, confidence + 0.1)
        if amount > 0:
            confidence = min(1.0, confidence + 0.05)

        return Invoice(
            id="",
            invoice_type=inv_type,
            invoice_code=code,
            invoice_number=number,
            invoice_date=inv_date,
            seller_name=seller,
            buyer_name=buyer,
            amount=amount,
            tax_amount=tax,
            total_amount=amount + tax,
            raw_text=raw_text[:500],
            confidence=confidence,
            image_path=image_path,
        )

    def batch_parse(self, text_list: list[str]) -> list[Invoice]:
        """批量解析票据文本"""
        return [self.parse_text_to_invoice(text) for text in text_list]

    def get_account_mapping(self, inv_type: InvoiceType) -> dict:
        """获取票据类型对应的科目映射"""
        return self.TYPE_ACCOUNT_MAP.get(inv_type, {
            "debit": "5602/管理费用",
            "credit": "1001/库存现金",
        })
