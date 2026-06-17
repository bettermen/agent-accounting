---
name: agent-accounting
description: "AI代理记账自动化系统：票据OCR识别→智能分录→三大报表→金税四期申报→风险预警。面向中小代账公司，覆盖票据采集、分类、分录生成、凭证编制、试算平衡、报表输出、报税申报全流程。Triggers: 代理记账, 记账报税, 票据识别, 自动做账, 代账, 财务报表, 金税四期, 增值税申报, OCR发票, accounting automation"
version: "1.0.0"
metadata:
  openclaw:
    requires:
      bins:
        - python.exe
      env:
        - BAIDU_OCR_API_KEY
        - BAIDU_OCR_SECRET_KEY
        - TAX_API_KEY
        - TAX_API_BASE_URL
    emoji: "🤖"
    homepage: https://github.com/bettermen/agent-accounting
---

# agent-accounting — AI代理记账自动化技能

> **面向代账公司的全流程AI自动化工具**
> 从票据采集到金税四期申报一站式覆盖，效率提升50x

## 概述

agent-accounting 是一个 AI 驱动的代理记账自动化系统，覆盖企业记账全流程。支持本地OCR模式和百度OCR API双引擎，内置智能分录引擎、三大报表自动生成、金税四期申报对接。

**项目路径：** `C:\Users\PC\WorkBuddy\2026-06-17-11-54-26\agent-accounting\`
**入口文件：** `main.py`
**Python：** `C:\Users\PC\.workbuddy\binaries\python\envs\default\Scripts\python.exe`

---

## 快速开始

```python
import subprocess, os

PROJECT_DIR = r"C:\Users\PC\WorkBuddy\2026-06-17-11-54-26\agent-accounting"
PYTHON = r"C:\Users\PC\.workbuddy\binaries\python\envs\default\Scripts\python.exe"

def run_accounting(cmd="full"):
    """运行代理记账流程
    cmd: full|demo|ocr|vouchers|reports|tax|risk|filing|baidu_ocr
    """
    result = subprocess.run(
        [PYTHON, "main.py", cmd],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        timeout=30
    )
    return result.stdout

# 一键完整流程：OCR → 做账 → 申报 → 仪表盘
output = run_accounting("full")
print(output)

# 打开仪表盘
import webbrowser
webbrowser.open(f"file:///{PROJECT_DIR}/demo_data/dashboard.html")
```

---

## 功能一：票据 OCR 识别

```bash
# 测试本地OCR识别（无需API Key）
python "C:\Users\PC\WorkBuddy\2026-06-17-11-54-26\agent-accounting\main.py" ocr
```

支持13类票据：增值税专用发票、增值税普通发票、电子发票、火车票、飞机行程单、出租车票、银行回单、工资单、费用报销单、采购单、销售单、收据、合同。

可选百度OCR API增强（每月500次免费）：
- 申请地址：https://ai.baidu.com/tech/ocr/finance
- 设置环境变量：`$env:BAIDU_OCR_API_KEY="xxx"` + `$env:BAIDU_OCR_SECRET_KEY="yyy"`
- 检测状态：`python main.py baidu_ocr`

---

## 功能二：自动生成会计分录和凭证

```bash
# 查看凭证列表
python "C:\Users\PC\WorkBuddy\2026-06-17-11-54-26\agent-accounting\main.py" vouchers
```

智能分录引擎内置50+会计科目表，根据票据类型自动匹配借贷科目，批量生成标准会计凭证，自动验证借贷平衡。

---

## 功能三：财务报表生成

```bash
# 查看三大报表
python "C:\Users\PC\WorkBuddy\2026-06-17-11-54-26\agent-accounting\main.py" reports
```

自动生成：试算平衡表、资产负债表、利润表。

---

## 功能四：税务计算与风险预警

```bash
# 报税计算
python "C:\Users\PC\WorkBuddy\2026-06-17-11-54-26\agent-accounting\main.py" tax

# 风险检测
python "C:\Users\PC\WorkBuddy\2026-06-17-11-54-26\agent-accounting\main.py" risk
```

覆盖：增值税进销项核算、企业所得税季度预缴、印花税计算；10项金税四期风险指标检测（税负异常/零申报/发票重复/过期等）。

---

## 功能五：金税四期申报

```bash
# 执行申报流程（含风险预检+XML生成）
python "C:\Users\PC\WorkBuddy\2026-06-17-11-54-26\agent-accounting\main.py" filing
```

支持第三方申报服务商对接（百望云/航信/企享云）：
- `$env:TAX_API_KEY="your_tax_api_key"`
- `$env:TAX_API_BASE_URL="https://api.your-provider.com/v1"`

高风险自动阻止申报，输出修正建议。

---

## 功能六：完整演示流程

```bash
# 完整演示：OCR → 做账 → 报表 → 申报 → 仪表盘
python "C:\Users\PC\WorkBuddy\2026-06-17-11-54-26\agent-accounting\main.py" full
```

一步生成完整代理记账周期结果，含交互式HTML仪表盘（KPI卡片、Chart.js图表、凭证明细、申报状态面板）。

---

## 功能七：可视化仪表盘

```python
# 仪表盘路径
DASHBOARD_PATH = r"C:\Users\PC\WorkBuddy\2026-06-17-11-54-26\agent-accounting\demo_data\dashboard.html"

import webbrowser
webbrowser.open(f"file:///{DASHBOARD_PATH}")
```

仪表盘包含：KPI卡片（凭证数/票据数/税额/风险等级）、票据分类饼图、费用支出柱状图、凭证汇总表、资产负债表、利润表、申报状态面板、风险预警列表。

---

## 常见场景处理

**场景：用户说"帮我记一笔账"**
1. 使用 `core/ocr.py` 识别票据
2. 使用 `core/engine.py` 生成分录和凭证
3. 展示凭证列表供确认

**场景：用户说"这个月报税"**
1. 运行 `main.py tax` 计算税额
2. 运行 `main.py risk` 检测风险
3. 运行 `main.py filing` 执行申报
4. 展示申报结果

**场景：用户说"生成财务报表"**
1. 运行 `main.py reports` 生成三大报表
2. 运行 `main.py full` 附带生成仪表盘
3. 打开 HTML 仪表盘供查看

**场景：用户说"配置百度OCR"**
1. 引导用户申请百度OCR API Key
2. 设置环境变量 `BAIDU_OCR_API_KEY` 和 `BAIDU_OCR_SECRET_KEY`
3. 运行 `main.py baidu_ocr` 验证配置

---

## 模块架构

```
core/
├── models.py        # 数据模型
├── ocr.py           # 本地OCR（13类票据）
├── baidu_ocr.py     # 百度OCR API（含降级）
├── engine.py        # 智能分录引擎
├── reports.py       # 三大报表生成
├── tax.py           # 税务计算+风险预警
└── golden_tax.py    # 金税四期申报接口
web/
└── dashboard.py     # HTML可视化仪表盘
scripts/
└── generate_demo.py # 演示数据生成器
main.py              # CLI入口
```

---

## 环境要求

- Python 3.10+
- 可选：requests（百度OCR API调用）
- 可选：Pillow（票据图片预处理）
- 可选：openpyxl（Excel导出）
