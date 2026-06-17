"""
百度OCR真实API集成模块
支持：
  - 混贴票据识别（13类，一张图多张票据自动切分）
  - 增值税发票识别（专用）
  - AccessToken自动获取与30天缓存
  - 降级到本地规则解析（API失败/未配置时自动切换）

文档参考：
  https://ai.baidu.com/ai-doc/OCR/Zk3h7xz52
  接口地址：https://aip.baidubce.com/rest/2.0/ocr/v1/finance
"""

import base64
import json
import logging
import os
import time
import urllib.parse
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import requests

from .models import Invoice, InvoiceType
from .ocr import InvoiceOCR

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────
# 百度 OCR API 端点
# ──────────────────────────────────────────────────────────
BAIDU_TOKEN_URL = "https://aip.baidubce.com/oauth/2.0/token"
# 智能财务票据识别（13类混贴）
BAIDU_FINANCE_OCR_URL = "https://aip.baidubce.com/rest/2.0/ocr/v1/finance"
# 增值税发票识别（专项，返回更多字段）
BAIDU_VAT_INVOICE_URL = "https://aip.baidubce.com/rest/2.0/ocr/v1/vat_invoice"
# 混贴票据识别
BAIDU_MIXED_RECEIPT_URL = "https://aip.baidubce.com/rest/2.0/ocr/v1/multiple_invoice"

# 百度OCR 票据类型 → 本系统 InvoiceType 映射
BAIDU_TYPE_MAP = {
    "增值税发票":         InvoiceType.VAT_NORMAL,
    "增值税专用发票":     InvoiceType.VAT_SPECIAL,
    "增值税电子普通发票": InvoiceType.VAT_ELECTRONIC,
    "增值税电子专用发票": InvoiceType.VAT_ELECTRONIC,
    "全电发票":           InvoiceType.VAT_ELECTRONIC,
    "全电纸质发票":       InvoiceType.VAT_NORMAL,
    "定额发票":           InvoiceType.QUOTA_INVOICE,
    "通用机打发票":       InvoiceType.MACHINE_INVOICE,
    "卷式发票":           InvoiceType.MACHINE_INVOICE,
    "火车票":             InvoiceType.TRAIN_TICKET,
    "航空运输电子客票行程单": InvoiceType.FLIGHT_ITINERARY,
    "出租车票":           InvoiceType.TAXI_RECEIPT,
    "网约车行程单":       InvoiceType.RIDE_HAILING,
    "汽车票":             InvoiceType.TRAIN_TICKET,
    "银行回单":           InvoiceType.BANK_RECEIPT,
    "过路过桥费发票":     InvoiceType.OTHER,
    "船票":               InvoiceType.OTHER,
    "二手车销售统一发票": InvoiceType.OTHER,
    "机动车销售统一发票": InvoiceType.OTHER,
}


class TokenCache:
    """AccessToken 本地30天缓存"""

    def __init__(self, cache_file: str = None):
        self.cache_file = cache_file or os.path.join(
            os.path.expanduser("~"), ".workbuddy", "baidu_ocr_token.json"
        )
        self._token: Optional[str] = None
        self._expires_at: float = 0

    def get(self) -> Optional[str]:
        """获取有效token，优先内存→文件→返回None"""
        # 内存缓存（本次进程）
        if self._token and time.time() < self._expires_at:
            return self._token
        # 文件缓存（跨进程）
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if time.time() < data.get("expires_at", 0):
                    self._token = data["access_token"]
                    self._expires_at = data["expires_at"]
                    return self._token
        except Exception:
            pass
        return None

    def save(self, token: str, expires_in: int):
        """保存token到内存和文件"""
        self._token = token
        self._expires_at = time.time() + expires_in - 3600  # 提前1小时刷新
        os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
        with open(self.cache_file, "w", encoding="utf-8") as f:
            json.dump({
                "access_token": token,
                "expires_at": self._expires_at,
                "saved_at": datetime.now().isoformat(),
            }, f, ensure_ascii=False, indent=2)


_token_cache = TokenCache()


def get_access_token(api_key: str, secret_key: str) -> str:
    """
    获取百度AccessToken（带30天缓存）

    Args:
        api_key: 百度AI控制台的API Key
        secret_key: 百度AI控制台的Secret Key

    Returns:
        access_token字符串

    Raises:
        requests.HTTPError: 网络请求失败
        KeyError: 返回数据中无access_token字段
    """
    # 先查缓存
    cached = _token_cache.get()
    if cached:
        logger.debug("使用缓存的AccessToken")
        return cached

    url = (
        f"{BAIDU_TOKEN_URL}"
        f"?grant_type=client_credentials"
        f"&client_id={api_key}"
        f"&client_secret={secret_key}"
    )
    resp = requests.post(url, headers={"Accept": "application/json"}, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    if "error" in data:
        raise ValueError(f"获取AccessToken失败: {data.get('error_description', data['error'])}")

    token = data["access_token"]
    expires_in = data.get("expires_in", 2592000)  # 默认30天
    _token_cache.save(token, expires_in)
    logger.info(f"已获取新AccessToken，有效期{expires_in//86400}天")
    return token


def _file_to_base64(file_path: str, url_encode: bool = True) -> str:
    """文件转base64（可选URL编码，POST form-data需要）"""
    with open(file_path, "rb") as f:
        content = base64.b64encode(f.read()).decode("utf-8")
    if url_encode:
        content = urllib.parse.quote_plus(content)
    return content


def _parse_finance_result(result: dict) -> list[Invoice]:
    """
    解析百度「智能财务票据识别」接口返回结果
    返回结构：
    {
      "words_result": [
        {
          "type": "增值税发票",
          "result": {
            "InvoiceNum": "...",
            "InvoiceDate": "...",
            "AmountInFiguers": "...",
            "TotalTax": "...",
            ...
          }
        },
        ...
      ]
    }
    """
    invoices = []
    word_results = result.get("words_result", [])

    for item in word_results:
        baidu_type = item.get("type", "")
        res = item.get("result", {})

        inv_type = BAIDU_TYPE_MAP.get(baidu_type, InvoiceType.OTHER)

        # ── 提取各字段 ──────────────────────────────────────
        invoice_code   = res.get("InvoiceCode", {}).get("word", "")
        invoice_number = res.get("InvoiceNum", {}).get("word", "")
        seller_name    = res.get("SellerName", {}).get("word", "")
        buyer_name     = res.get("PurchaserName", {}).get("word", "")

        # 金额处理
        def to_float(field_name: str) -> float:
            raw = res.get(field_name, {})
            if isinstance(raw, dict):
                raw = raw.get("word", "")
            if not raw:
                return 0.0
            # 去掉¥, ,  等非数字字符
            raw = str(raw).replace("¥", "").replace("￥", "").replace(",", "").strip()
            try:
                return float(raw)
            except ValueError:
                return 0.0

        # 百度各接口金额字段名不统一，尝试多种
        amount      = (to_float("AmountInFiguers")
                       or to_float("Amount")
                       or to_float("PretaxAmount"))
        tax_amount  = (to_float("TotalTax")
                       or to_float("TaxAmount")
                       or to_float("Tax"))
        total       = to_float("TotalAmount") or (amount + tax_amount)

        # 日期解析
        inv_date = None
        date_raw = res.get("InvoiceDate", {})
        if isinstance(date_raw, dict):
            date_raw = date_raw.get("word", "")
        if date_raw:
            for fmt in ("%Y年%m月%d日", "%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
                try:
                    inv_date = datetime.strptime(date_raw.strip(), fmt).date()
                    break
                except ValueError:
                    pass

        # 置信度：有发票号+金额则高置信
        confidence = 0.92 if (invoice_number and total > 0) else 0.75

        inv = Invoice(
            id="",
            invoice_type=inv_type,
            invoice_code=invoice_code,
            invoice_number=invoice_number,
            invoice_date=inv_date,
            seller_name=seller_name,
            buyer_name=buyer_name,
            amount=amount,
            tax_amount=tax_amount,
            total_amount=total,
            raw_text=json.dumps(res, ensure_ascii=False)[:600],
            confidence=confidence,
            image_path="",
            source="baidu_ocr_api",
        )
        invoices.append(inv)

    return invoices


def _parse_mixed_result(result: dict) -> list[Invoice]:
    """
    解析百度「混贴票据识别」接口返回结果
    返回结构：
    {
      "words_result": [
        {
          "type": "vat_invoice",
          "vat_invoice": { ... } | "train_ticket": { ... } | ...
        }
      ]
    }
    """
    invoices = []
    # mixed_receipt 接口的结构与 finance 稍有差异，兼容处理
    for item in result.get("words_result", []):
        # 尝试合并成通用格式再复用 finance 解析器
        merged = {"type": item.get("type", ""), "result": {}}
        for key, val in item.items():
            if isinstance(val, dict):
                merged["result"].update(val)
        invs = _parse_finance_result({"words_result": [merged]})
        invoices.extend(invs)
    return invoices


class BaiduOCRClient:
    """
    百度OCR真实API客户端

    使用方式：
        client = BaiduOCRClient(api_key="...", secret_key="...")
        invoices = client.recognize_finance(image_path="receipt.jpg")

    降级策略：
        若API Key未配置或调用失败，自动降级到本地正则解析（InvoiceOCR）
    """

    def __init__(self, api_key: str = None, secret_key: str = None):
        """
        Args:
            api_key: 百度AI控制台 API Key（或从环境变量 BAIDU_OCR_API_KEY 读取）
            secret_key: 百度AI控制台 Secret Key（或从环境变量 BAIDU_OCR_SECRET_KEY 读取）
        """
        self.api_key    = api_key    or os.environ.get("BAIDU_OCR_API_KEY", "")
        self.secret_key = secret_key or os.environ.get("BAIDU_OCR_SECRET_KEY", "")
        self._local_ocr = InvoiceOCR()
        self._enabled   = bool(self.api_key and self.secret_key)

        if not self._enabled:
            logger.warning(
                "百度OCR API Key未配置，将使用本地规则解析。"
                "配置方式：设置环境变量 BAIDU_OCR_API_KEY / BAIDU_OCR_SECRET_KEY"
            )

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _get_token(self) -> Optional[str]:
        """获取token，失败返回None（触发降级）"""
        try:
            return get_access_token(self.api_key, self.secret_key)
        except Exception as e:
            logger.error(f"获取AccessToken失败: {e}")
            return None

    def recognize_finance(self, image_path: str) -> list[Invoice]:
        """
        调用「智能财务票据识别」API识别单张图片中的票据（支持多张混贴）

        Args:
            image_path: 图片或PDF路径（PNG/JPG/JPEG/BMP/PDF，≤8MB）

        Returns:
            解析出的Invoice列表（多张票据多条）
        """
        if not self._enabled:
            return self._fallback_local(image_path)

        token = self._get_token()
        if not token:
            return self._fallback_local(image_path)

        try:
            # 判断文件类型
            suffix = Path(image_path).suffix.lower()
            if suffix == ".pdf":
                key, content = "pdf_file", _file_to_base64(image_path, url_encode=True)
            else:
                key, content = "image", _file_to_base64(image_path, url_encode=True)

            url = f"{BAIDU_FINANCE_OCR_URL}?access_token={token}"
            resp = requests.post(
                url,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data=f"{key}={content}",
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            # 错误处理
            if "error_code" in data:
                raise ValueError(
                    f"百度OCR错误 {data['error_code']}: {data.get('error_msg', '')}"
                )

            invoices = _parse_finance_result(data)
            for inv in invoices:
                inv.image_path = image_path
            logger.info(f"[BaiduOCR] {image_path} → 识别出{len(invoices)}张票据")
            return invoices

        except Exception as e:
            logger.warning(f"百度OCR API调用失败（{e}），降级到本地解析")
            return self._fallback_local(image_path)

    def recognize_vat_invoice(self, image_path: str) -> Optional[Invoice]:
        """
        调用「增值税发票识别」API（返回更详细的字段）

        Returns:
            单张Invoice或None（降级时返回本地解析结果）
        """
        if not self._enabled:
            return None

        token = self._get_token()
        if not token:
            return None

        try:
            suffix = Path(image_path).suffix.lower()
            if suffix == ".pdf":
                key, content = "pdf_file", _file_to_base64(image_path, url_encode=True)
            else:
                key, content = "image", _file_to_base64(image_path, url_encode=True)

            url = f"{BAIDU_VAT_INVOICE_URL}?access_token={token}"
            resp = requests.post(
                url,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data=f"{key}={content}&seal_tag=false",
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            if "error_code" in data:
                logger.warning(f"增值税发票识别错误: {data}")
                return None

            wr = data.get("words_result", {})

            def wr_val(key: str) -> str:
                v = wr.get(key, "")
                if isinstance(v, dict):
                    return v.get("word", "")
                if isinstance(v, list) and v:
                    return v[0].get("word", "") if isinstance(v[0], dict) else str(v[0])
                return str(v) if v else ""

            def wr_float(key: str) -> float:
                raw = wr_val(key).replace("¥", "").replace("￥", "").replace(",", "").strip()
                try:
                    return float(raw)
                except ValueError:
                    return 0.0

            # 发票类型
            type_str = wr_val("InvoiceTypeOrg") or wr_val("InvoiceType")
            inv_type = BAIDU_TYPE_MAP.get(type_str, InvoiceType.VAT_NORMAL)

            # 日期
            inv_date = None
            date_raw = wr_val("InvoiceDate")
            for fmt in ("%Y年%m月%d日", "%Y-%m-%d", "%Y/%m/%d"):
                try:
                    inv_date = datetime.strptime(date_raw, fmt).date()
                    break
                except ValueError:
                    pass

            amount     = wr_float("AmountInFiguers") or wr_float("Amount")
            tax_amount = wr_float("TotalTax") or wr_float("Tax")
            total      = amount + tax_amount

            return Invoice(
                id="",
                invoice_type=inv_type,
                invoice_code=wr_val("InvoiceCode"),
                invoice_number=wr_val("InvoiceNum"),
                invoice_date=inv_date,
                seller_name=wr_val("SellerName"),
                buyer_name=wr_val("PurchaserName"),
                amount=amount,
                tax_amount=tax_amount,
                total_amount=total,
                raw_text=json.dumps(wr, ensure_ascii=False)[:600],
                confidence=0.95,
                image_path=image_path,
                source="baidu_ocr_vat_api",
            )

        except Exception as e:
            logger.warning(f"增值税发票OCR失败: {e}")
            return None

    def batch_recognize(self, image_paths: list[str]) -> list[Invoice]:
        """
        批量识别多个图片文件

        Returns:
            所有图片中识别出的Invoice列表（按图片顺序）
        """
        all_invoices: list[Invoice] = []
        for path in image_paths:
            invs = self.recognize_finance(path)
            all_invoices.extend(invs)
        return all_invoices

    def _fallback_local(self, image_path: str) -> list[Invoice]:
        """本地规则降级（从文件名推断类型，无法读取图片内容）"""
        logger.info(f"使用本地规则解析: {image_path}")
        # 无法真正读取图片，返回占位对象
        filename = Path(image_path).stem
        inv = self._local_ocr.parse_text_to_invoice(filename, image_path)
        inv.confidence = 0.40
        inv.source = "local_rule_fallback"
        return [inv]

    def test_connection(self) -> dict:
        """
        测试API连接状态

        Returns:
            {"status": "ok"|"error"|"not_configured", "message": str}
        """
        if not self._enabled:
            return {
                "status": "not_configured",
                "message": "API Key未配置，请设置 BAIDU_OCR_API_KEY / BAIDU_OCR_SECRET_KEY 环境变量",
                "fallback": "本地规则解析（精度较低）",
            }
        try:
            token = get_access_token(self.api_key, self.secret_key)
            return {
                "status": "ok",
                "message": f"AccessToken获取成功（{token[:12]}...）",
                "api_url": BAIDU_FINANCE_OCR_URL,
            }
        except Exception as e:
            return {
                "status": "error",
                "message": str(e),
                "suggestion": "检查API Key/Secret Key是否正确，以及账户是否已开通OCR服务",
            }


# ──────────────────────────────────────────────────────────
# 模块级便捷函数
# ──────────────────────────────────────────────────────────
_default_client: Optional[BaiduOCRClient] = None


def get_default_client() -> BaiduOCRClient:
    """获取全局默认OCR客户端（单例）"""
    global _default_client
    if _default_client is None:
        _default_client = BaiduOCRClient()
    return _default_client


def recognize_image(image_path: str,
                    api_key: str = None,
                    secret_key: str = None) -> list[Invoice]:
    """
    便捷函数：识别单张图片中的票据

    Args:
        image_path: 图片路径
        api_key: 可选，覆盖环境变量
        secret_key: 可选，覆盖环境变量
    """
    if api_key or secret_key:
        client = BaiduOCRClient(api_key, secret_key)
    else:
        client = get_default_client()
    return client.recognize_finance(image_path)
