"""
报表生成模块
自动生成：资产负债表、利润表、现金流量表、科目余额表
"""

import json
from datetime import date, datetime
from typing import Optional

from .models import (
    AccountBalance, AccountCategory, Direction, ReportType, Voucher, Company,
)


class ReportGenerator:
    """财务报表生成器"""

    @staticmethod
    def generate_trial_balance(balances: list[AccountBalance]) -> dict:
        """
        生成科目余额表（试算平衡）
        返回：{ "data": [...], "total_debit": ..., "total_credit": ..., "balanced": bool }
        """
        data = []
        total_debit = 0.0
        total_credit = 0.0

        for b in balances:
            row = {
                "code": b.account_code,
                "name": b.account_name,
                "category": b.category.value,
                "direction": b.direction.value,
                "debit": b.debit_amount,
                "credit": b.credit_amount,
                "balance": abs(b.debit_amount - b.credit_amount),
            }
            data.append(row)
            total_debit += b.debit_amount
            total_credit += b.credit_amount

        return {
            "period": balances[0].period if balances else "",
            "data": sorted(data, key=lambda x: x["code"]),
            "total_debit": round(total_debit, 2),
            "total_credit": round(total_credit, 2),
            "balanced": abs(total_debit - total_credit) < 0.01,
        }

    @staticmethod
    def generate_balance_sheet(balances: list[AccountBalance]) -> dict:
        """生成资产负债表"""
        assets = []
        liabilities = []
        equity = []

        total_assets = 0.0
        total_liabilities = 0.0
        total_equity = 0.0

        for b in balances:
            balance = b.debit_amount - b.credit_amount
            item = {"code": b.account_code, "name": b.account_name, "amount": round(abs(balance), 2)}

            if b.category == AccountCategory.ASSET:
                assets.append(item)
                total_assets += max(0, balance)
            elif b.category == AccountCategory.LIABILITY:
                liabilities.append(item)
                total_liabilities += max(0, -balance) if balance < 0 else 0
            elif b.category == AccountCategory.EQUITY:
                equity.append(item)
                total_equity += max(0, -balance) if balance < 0 else 0

        return {
            "report_date": date.today().isoformat(),
            "assets": assets,
            "total_assets": round(total_assets, 2),
            "liabilities": liabilities,
            "total_liabilities": round(total_liabilities, 2),
            "equity": equity,
            "total_equity": round(total_equity, 2),
            "balanced": abs(total_assets - (total_liabilities + total_equity)) < 1,
        }

    @staticmethod
    def generate_income_statement(
        revenue_items: list[AccountBalance],
        expense_items: list[AccountBalance],
        cost_items: Optional[list[AccountBalance]] = None,
    ) -> dict:
        """生成利润表"""
        total_revenue = sum(abs(b.credit_amount - b.debit_amount)
                            for b in revenue_items
                            if b.category == AccountCategory.REVENUE)
        total_cost = sum(abs(b.debit_amount - b.credit_amount)
                        for b in (cost_items or [])
                        if b.category == AccountCategory.COST)
        total_expense = sum(abs(b.debit_amount - b.credit_amount)
                          for b in expense_items
                          if b.category == AccountCategory.EXPENSE)

        gross_profit = total_revenue - total_cost
        net_profit = gross_profit - total_expense

        return {
            "report_date": date.today().isoformat(),
            "revenue": round(total_revenue, 2),
            "cost": round(total_cost, 2),
            "gross_profit": round(gross_profit, 2),
            "expense": round(total_expense, 2),
            "net_profit_before_tax": round(net_profit, 2),
            "revenue_items": [
                {"code": b.account_code, "name": b.account_name,
                 "amount": round(abs(b.credit_amount - b.debit_amount), 2)}
                for b in revenue_items
            ],
            "expense_items": [
                {"code": b.account_code, "name": b.account_name,
                 "amount": round(abs(b.debit_amount - b.credit_amount), 2)}
                for b in expense_items
            ],
        }

    @staticmethod
    def generate_voucher_summary(vouchers: list[Voucher]) -> dict:
        """生成凭证汇总"""
        by_type: dict[str, int] = {}
        total_vouchers = len(vouchers)
        total_amount = 0.0

        for v in vouchers:
            vt = v.voucher_type
            by_type[vt] = by_type.get(vt, 0) + 1
            total_amount += v.total_debit

        return {
            "total_vouchers": total_vouchers,
            "total_amount": round(total_amount, 2),
            "by_type": by_type,
            "status_summary": {
                "draft": sum(1 for v in vouchers if v.status == "draft"),
                "reviewed": sum(1 for v in vouchers if v.status == "reviewed"),
                "posted": sum(1 for v in vouchers if v.status == "posted"),
            },
            "vouchers": [
                {
                    "id": v.id,
                    "date": v.voucher_date.isoformat(),
                    "type": v.voucher_type,
                    "number": v.voucher_number,
                    "entries": len(v.entries),
                    "debit": v.total_debit,
                    "credit": v.total_credit,
                    "status": v.status,
                    "attachments": v.attachments,
                }
                for v in vouchers
            ],
        }
