# 🤖 Agent Accounting — AI代理记账自动化系统

> 面向中小代账公司的全流程AI自动化工具：票据识别 → 智能分录 → 报表生成 → 金税四期申报

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

---

## 📋 背景与痛点

中国代理记账行业超**10万家机构**，服务**2500万+小微企业**，但仍面临严峻挑战：

| 痛点 | 现状 |
|------|------|
| 票据处理占据 **70% 工时** | 月末手工录入"票据山"，3天才能录完 |
| 错报漏报风险高 | 金税四期零容忍，人工失误率约3-5% |
| 人效瓶颈 | 纯人工 80户/人，行业利润率已跌破15% |
| 客户沟通成本高 | 催票、核对、解释报表各环节反复沟通 |

本系统通过 AI 将 **70%+ 重复流程自动化**，理论人效提升至 **300户/人**。

---

## ✨ 功能模块

```
agent-accounting/
├── core/
│   ├── models.py        # 数据模型（票据/凭证/科目/风险告警）
│   ├── ocr.py           # 本地票据OCR识别（13类票据，关键词+正则）
│   ├── baidu_ocr.py     # 百度财务票据识别真实API（含降级回退）
│   ├── engine.py        # 智能会计分录引擎（50+科目，自动匹配）
│   ├── reports.py       # 三大报表生成（试算平衡/资产负债/利润表）
│   ├── tax.py           # 报税辅助+风险预警（增值税/所得税/印花税）
│   └── golden_tax.py    # 金税四期申报接口（XML生成+状态机+风险预检）
├── web/
│   └── dashboard.py     # HTML可视化仪表盘（Chart.js + KPI卡片）
├── scripts/
│   └── generate_demo.py # 演示数据生成器（完整流程端到端）
└── main.py              # CLI入口
```

### 核心能力

- **🔍 票据OCR识别** — 支持增值税专/普票、电子发票、火车票、飞机票、出租车票、银行回单、工资单等13类
- **⚡ 智能分录引擎** — 依据票据类型自动匹配借贷科目，生成标准会计凭证，自动验证借贷平衡
- **📊 三大报表** — 自动生成试算平衡表、资产负债表、利润表
- **🧮 税务计算** — 增值税进销项自动核算、企业所得税季度预缴、印花税计算
- **⚠️ 风险预警** — 10项金税四期指标检测（税负异常/零申报/发票重复/过期等）
- **📨 申报集成** — 生成标准XML申报包，支持对接百望云/航信/企享云等第三方申报服务
- **🖥️ 可视化仪表盘** — HTML报告，含KPI卡片、图表、凭证明细、申报状态

---

## 🚀 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 运行完整演示

```bash
# 一键完整流程：OCR识别 → 做账 → 申报 → 生成仪表盘
python main.py full

# 仅演示（跳过OCR真实调用）
python main.py demo

# 单独测试各模块
python main.py ocr       # 本地OCR测试
python main.py vouchers  # 查看凭证列表
python main.py reports   # 查看财务报表
python main.py tax       # 查看报税数据
python main.py risk      # 风险检测
python main.py filing    # 金税四期申报流程
python main.py baidu_ocr # 检测百度OCR API状态
```

---

## 🔧 配置

### 百度OCR API（可选，不配置则使用本地正则）

1. 前往 [ai.baidu.com/tech/ocr/finance](https://ai.baidu.com/tech/ocr/finance) 申请，每月免费500次
2. 设置环境变量：

```bash
# Windows
$env:BAIDU_OCR_API_KEY="your_api_key"
$env:BAIDU_OCR_SECRET_KEY="your_secret_key"

# Linux/macOS
export BAIDU_OCR_API_KEY="your_api_key"
export BAIDU_OCR_SECRET_KEY="your_secret_key"
```

### 金税四期第三方申报API（可选）

支持百望云、航信、企享云等服务商：

```bash
$env:TAX_API_KEY="your_tax_api_key"
$env:TAX_API_BASE_URL="https://api.your-provider.com/v1"
```

---

## 📈 效率对比

| 流程环节 | 传统人工 | AI自动化 | 提升 |
|----------|----------|----------|------|
| 票据整理分类 | 3天 | 半天 | 6x |
| 会计分录生成 | 2天 | 秒级 | 100x |
| 报表编制 | 1天 | 分钟级 | 50x |
| 报税申报 | 半天 | 5分钟 | 6x |
| **合计（100票）** | **~6天** | **~1小时** | **~50x** |

---

## 🏗️ 技术架构

```
票据图片/文件
    ↓
[OCR模块] baidu_ocr.py / ocr.py（降级）
    ↓
[分类引擎] 13类票据识别 + 关键字段提取
    ↓
[分录引擎] engine.py — 科目表匹配 + 借贷凭证生成
    ↓
[报表模块] reports.py — 试算平衡 + 三大报表
    ↓
[税务模块] tax.py — 增值税/所得税/印花税计算
    ↓
[申报模块] golden_tax.py — 风险预检 + XML生成 + 状态跟踪
    ↓
[仪表盘] dashboard.py — HTML可视化报告
```

---

## 📄 License

MIT License — 欢迎二次开发和商业使用。

---

## 🤝 贡献

欢迎 Issue 和 PR！可扩展方向：
- [ ] 对接更多OCR服务（腾讯云/阿里云）
- [ ] 微信小程序扫票上传
- [ ] 多租户SaaS架构
- [ ] 与用友/金蝶财务软件对接
- [ ] 银行流水自动核账
