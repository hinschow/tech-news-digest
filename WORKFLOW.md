# Tech News Digest - 完整工作流方案

## 架构设计

### 核心理念
- **数据采集与报告生成分离**：定时采集原始数据到本地，按需生成报告
- **采集即存全文**：每次采集自动抓取文章全文（enrich 默认开启），避免链接过期丢失内容
- **本地数据优先**：所有数据存储在本地，支持历史分析、AI摘要和二次挖掘
- **避免遗漏**：高频采集（每小时）确保不错过重要消息

## 工作流程

### 第一阶段：数据采集（每小时）

**目标**：持续采集新闻数据到本地存储

**Cron 任务配置**：
- **频率**：每小时第 5 分钟运行
- **Cron 表达式**：`5 * * * *`
- **时区**：Asia/Shanghai

**任务内容**：
```bash
python scripts/run-pipeline.py \
  --defaults config/defaults \
  --hours 1 \
  --output archive/raw-data/$(date +%Y-%m-%d-%H).json \
  --force
```

> 注意：全文抓取（enrich）默认开启，无需额外参数。如需禁用可加 `--no-enrich`。
> enrich 门槛：quality_score >= 3 即抓取全文，单次最多 50 篇，每篇最多 3000 字符。

**输出文件命名**：
- `archive/raw-data/2026-03-10-08.json` (早上 8 点采集)
- `archive/raw-data/2026-03-10-09.json` (早上 9 点采集)
- `archive/raw-data/2026-03-10-10.json` (早上 10 点采集)
- ...

**数据保留策略**：
- 保留最近 30 天的原始数据
- 30 天前的数据自动归档或删除

### 第二阶段：报告生成（早晚各一次）

#### 早报（每天 8:00）

**Cron 任务配置**：
- **频率**：每天早上 8:00
- **Cron 表达式**：`0 8 * * *`
- **时区**：Asia/Shanghai

**任务内容**：
1. 读取过去 24 小时的所有本地数据文件
2. 合并、去重、按质量评分排序
3. 生成中文早报
4. 发送到 Telegram

**数据范围**：
- 时间窗口：过去 24 小时
- 文件范围：`archive/raw-data/2026-03-09-08.json` 到 `archive/raw-data/2026-03-10-07.json`

#### 晚报（每天 19:00）

**Cron 任务配置**：
- **频率**：每天晚上 19:00
- **Cron 表达式**：`0 19 * * *`
- **时区**：Asia/Shanghai

**任务内容**：
1. 读取今天的所有本地数据文件
2. 合并、去重、按质量评分排序
3. 生成中文晚报
4. 发送到 Telegram

**数据范围**：
- 时间窗口：今天 00:00 到当前时间
- 文件范围：`archive/raw-data/2026-03-10-*.json`

### 第三阶段：按需分析

用户可以随时要求 AI 助手进行：

**1. 趋势分析**
- 统计某个技术的提及频率（按天/周/月）
- 对比不同时期的热点变化
- 识别新兴技术趋势

**2. 专题报告**
- 只看特定主题（AI Agent / Crypto / LLM / Frontier Tech）
- 追踪特定项目的动态（如 OpenAI / Anthropic）
- 关注特定作者的文章（如 Simon Willison / Paul Graham）

**3. 数据挖掘**
- 查找历史上某个事件的报道
- 统计某个公司的融资/发布记录
- 分析某个技术的讨论热度变化

## 需要开发的脚本

### 1. `scripts/merge-historical.py`

**功能**：合并指定时间范围内的所有原始数据文件

**输入参数**：
```bash
python scripts/merge-historical.py \
  --input-dir archive/raw-data \
  --start-date 2026-03-09 \
  --end-date 2026-03-10 \
  --output merged-output.json
```

**处理逻辑**：
1. 扫描 `input-dir` 目录，找到时间范围内的所有 JSON 文件
2. 读取每个文件的 `topics` 字段，提取所有文章
3. 按 `link` 字段去重（保留质量评分最高的）
4. 按 `quality_score` 降序排序
5. 输出统一格式的 JSON

**输出格式**：
```json
{
  "generated": "2026-03-10T08:00:00+08:00",
  "time_range": {
    "start": "2026-03-09T08:00:00+08:00",
    "end": "2026-03-10T08:00:00+08:00"
  },
  "input_files": [
    "archive/raw-data/2026-03-09-08.json",
    "archive/raw-data/2026-03-09-09.json",
    ...
  ],
  "total_input_articles": 5000,
  "total_output_articles": 350,
  "topics": {
    "ai-agent": {
      "count": 50,
      "articles": [...]
    },
    "crypto": {
      "count": 60,
      "articles": [...]
    },
    ...
  }
}
```

### 2. `scripts/generate-report.py`

**功能**：从合并后的 JSON 生成中文报告

**输入参数**：
```bash
python scripts/generate-report.py \
  --input merged-output.json \
  --template morning \
  --output morning-report.md \
  --top-n 5
```

**模板类型**：
- `morning`：早报模板（精简，每个主题 5 条）
- `evening`：晚报模板（详细，每个主题 10 条）
- `weekly`：周报模板（完整，每个主题 15 条）

**处理逻辑**：
1. 读取合并后的 JSON
2. 按模板要求筛选文章（top-n 控制每个主题的文章数量）
3. 生成 Markdown 格式的报告
4. 包含执行摘要、主题分类、GitHub Releases、Trending、Blog Picks

**输出格式**：
- Markdown 文件，格式与当前 `morning-brief-20260310.md` 一致

### 3. `scripts/analyze-trends.py`

**功能**：分析历史数据，生成趋势报告

**输入参数**：
```bash
python scripts/analyze-trends.py \
  --input-dir archive/raw-data \
  --start-date 2026-03-01 \
  --end-date 2026-03-10 \
  --keyword "DeepSeek" \
  --output trend-report.json
```

**分析维度**：
- 关键词提及频率（按天统计）
- 主题热度变化（AI Agent / Crypto / LLM / Frontier Tech）
- 热门项目排行（按 stars 增长速度）
- 活跃作者排行（按文章数量）

**输出格式**：
```json
{
  "keyword": "DeepSeek",
  "time_range": {
    "start": "2026-03-01",
    "end": "2026-03-10"
  },
  "daily_mentions": [
    {"date": "2026-03-01", "count": 5},
    {"date": "2026-03-02", "count": 8},
    ...
  ],
  "total_mentions": 67,
  "top_articles": [
    {
      "title": "DeepSeek-V3 发布",
      "date": "2026-03-05",
      "quality_score": 25
    },
    ...
  ]
}
```

## 目录结构

```
skills/tech-news-digest/
├── config/
│   └── defaults/           # 默认配置
│       ├── sources.json    # 数据源配置
│       └── topics.json     # 主题配置
├── scripts/
│   ├── run-pipeline.py     # 数据采集主脚本（含全文抓取）
│   ├── merge-historical.py # 合并历史数据（已开发）
│   ├── generate-report.py  # 生成报告（已开发，支持早报/晚报/周报）
│   ├── analyze-trends.py   # 趋势分析（已开发）
│   ├── enrich-articles.py  # 全文抓取（采集时自动调用）
│   └── send-telegram.py    # Telegram 推送（旧版，generate-report.py 已内置）
├── archive/
│   ├── raw-data/           # 原始数据存储
│   │   ├── 2026-03-10-08.json
│   │   ├── 2026-03-10-09.json
│   │   └── ...
│   ├── reports/            # 生成的报告
│   │   ├── morning-2026-03-10.md
│   │   ├── evening-2026-03-10.md
│   │   └── ...
│   └── trends/             # 趋势分析结果
│       ├── deepseek-trend.json
│       └── ...
├── WORKFLOW.md             # 本文档
└── README.md
```

## OpenClaw Cron 配置

### 任务 1：数据采集（每小时）

```json
{
  "name": "news-data-collection",
  "schedule": {
    "kind": "cron",
    "expr": "5 * * * *",
    "tz": "Asia/Shanghai"
  },
  "sessionTarget": "isolated",
  "payload": {
    "kind": "agentTurn",
    "message": "运行数据采集：python C:\\Users\\Hins\\.openclaw\\workspace\\skills\\tech-news-digest\\scripts\\run-pipeline.py --defaults C:\\Users\\Hins\\.openclaw\\workspace\\skills\\tech-news-digest\\config\\defaults --hours 1 --output C:\\Users\\Hins\\.openclaw\\workspace\\archive\\raw-data\\$(Get-Date -Format 'yyyy-MM-dd-HH').json --force\n\n仅采集数据，不发送通知。若失败记录错误日志。"
  },
  "delivery": {
    "mode": "none"
  }
}
```

### 任务 2：早报生成（每天 8:00）

```json
{
  "name": "news-morning-report",
  "schedule": {
    "kind": "cron",
    "expr": "0 8 * * *",
    "tz": "Asia/Shanghai"
  },
  "sessionTarget": "isolated",
  "payload": {
    "kind": "agentTurn",
    "message": "生成科技早报：\n1. 运行 python C:\\Users\\Hins\\.openclaw\\workspace\\skills\\tech-news-digest\\scripts\\merge-historical.py --input-dir C:\\Users\\Hins\\.openclaw\\workspace\\archive\\raw-data --hours 24 --output /tmp/morning-merged.json\n2. 运行 python C:\\Users\\Hins\\.openclaw\\workspace\\skills\\tech-news-digest\\scripts\\generate-report.py --input /tmp/morning-merged.json --template morning --output C:\\Users\\Hins\\.openclaw\\workspace\\archive\\reports\\morning-$(Get-Date -Format 'yyyy-MM-dd').md --top-n 5\n3. 读取生成的 Markdown 文件并发送到 Telegram\n\n若失败回复错误原因。"
  },
  "delivery": {
    "mode": "announce",
    "channel": "telegram",
    "to": "5689003327"
  }
}
```

### 任务 3：晚报生成（每天 19:00）

```json
{
  "name": "news-evening-report",
  "schedule": {
    "kind": "cron",
    "expr": "0 19 * * *",
    "tz": "Asia/Shanghai"
  },
  "sessionTarget": "isolated",
  "payload": {
    "kind": "agentTurn",
    "message": "生成科技晚报：\n1. 运行 python C:\\Users\\Hins\\.openclaw\\workspace\\skills\\tech-news-digest\\scripts\\merge-historical.py --input-dir C:\\Users\\Hins\\.openclaw\\workspace\\archive\\raw-data --today-only --output /tmp/evening-merged.json\n2. 运行 python C:\\Users\\Hins\\.openclaw\\workspace\\skills\\tech-news-digest\\scripts\\generate-report.py --input /tmp/evening-merged.json --template evening --output C:\\Users\\Hins\\.openclaw\\workspace\\archive\\reports\\evening-$(Get-Date -Format 'yyyy-MM-dd').md --top-n 8\n3. 读取生成的 Markdown 文件并发送到 Telegram\n\n若失败回复错误原因。"
  },
  "delivery": {
    "mode": "announce",
    "channel": "telegram",
    "to": "5689003327"
  }
}
```

## 优势总结

### 1. 数据完整性
- 每小时采集，不会错过重要消息
- 本地存储，随时可以回溯历史

### 2. 灵活性
- 报告生成与数据采集分离，可以随时重新生成报告
- 支持不同时间范围、不同主题的定制报告

### 3. 可扩展性
- 可以添加更多分析维度（趋势、对比、专题）
- 可以接入更多数据源（Twitter、Reddit、Web Search）

### 4. 性能优化
- 数据采集在后台静默运行，不影响用户体验
- 报告生成只在需要时运行，节省资源

## 已完成

- [x] `merge-historical.py` — 支持 `--hours`, `--today-only`, `--start-date/--end-date`
- [x] `generate-report.py` — 支持 morning/evening/weekly 模板，内置 Telegram 推送
- [x] `analyze-trends.py` — 关键词追踪、主题热力图、热门词排行
- [x] 目录结构 `archive/raw-data/`, `archive/reports/`, `archive/trends/`
- [x] `run-pipeline.py` — enrich 默认开启（`--no-enrich` 关闭）
- [x] `enrich-articles.py` — 门槛降至 score>=3，最多 50 篇，每篇 3000 字

## 使用示例

```bash
# 手动采集一次（含全文）
python scripts/run-pipeline.py --defaults config/defaults --hours 1 \
  --output archive/raw-data/$(date +%Y-%m-%d-%H).json --force

# 合并过去 24h 数据
python scripts/merge-historical.py --input-dir archive/raw-data --hours 24 \
  --output /tmp/morning-merged.json

# 生成早报并发送 Telegram
python scripts/generate-report.py --input /tmp/morning-merged.json \
  --template morning --telegram --coins

# 生成 Markdown 报告文件
python scripts/generate-report.py --input /tmp/morning-merged.json \
  --template morning --output archive/reports/morning-$(date +%Y-%m-%d).md

# 追踪关键词趋势
python scripts/analyze-trends.py --input-dir archive/raw-data \
  --keyword "Claude" --days 7 --output archive/trends/claude.json

# 查看热门关键词
python scripts/analyze-trends.py --input-dir archive/raw-data --days 7
```
