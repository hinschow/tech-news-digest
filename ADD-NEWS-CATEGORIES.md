# 添加行情、国际、国内、军事新闻配置方案

## 第一步：添加新主题到 topics.json

在 `config/defaults/topics.json` 的 `topics` 数组中添加以下 4 个主题：

```json
{
  "id": "market",
  "emoji": "📈",
  "label": "市场行情",
  "description": "股市、期货、大宗商品、外汇市场动态",
  "search": {
    "queries": ["stock market news", "股市行情", "期货市场", "大宗商品"],
    "twitter_queries": ["股市", "A股", "美股"],
    "must_include": ["股市", "期货", "大宗商品", "外汇", "stock", "market"],
    "exclude": ["广告", "推荐股票"]
  },
  "display": {
    "max_items": 6,
    "style": "compact"
  }
},
{
  "id": "international",
  "emoji": "🌍",
  "label": "国际新闻",
  "description": "全球政治、经济、社会重大事件",
  "search": {
    "queries": ["international news", "world news", "国际新闻"],
    "twitter_queries": ["国际", "全球"],
    "must_include": ["国际", "全球", "world", "international"],
    "exclude": ["娱乐", "八卦"]
  },
  "display": {
    "max_items": 8,
    "style": "detailed"
  }
},
{
  "id": "domestic",
  "emoji": "🇨🇳",
  "label": "国内新闻",
  "description": "中国国内政治、经济、社会重大事件",
  "search": {
    "queries": ["中国新闻", "国内新闻", "China news"],
    "twitter_queries": ["中国", "国内"],
    "must_include": ["中国", "国内", "China"],
    "exclude": ["娱乐", "八卦"]
  },
  "display": {
    "max_items": 8,
    "style": "detailed"
  }
},
{
  "id": "military",
  "emoji": "⚔️",
  "label": "军事新闻",
  "description": "军事动态、国防科技、地缘政治",
  "search": {
    "queries": ["military news", "defense technology", "军事新闻", "国防"],
    "twitter_queries": ["军事", "国防"],
    "must_include": ["军事", "国防", "military", "defense", "武器"],
    "exclude": ["游戏", "虚构"]
  },
  "display": {
    "max_items": 6,
    "style": "compact"
  }
}
```

## 第二步：添加数据源到 sources.json

在 `config/defaults/sources.json` 的 `sources` 数组中添加以下数据源：

### 市场行情类

```json
{
  "id": "sina-finance-rss",
  "type": "rss",
  "name": "新浪财经",
  "url": "https://finance.sina.com.cn/roll/index.d.html?col=89&page=1",
  "enabled": true,
  "priority": true,
  "topics": ["market"],
  "note": "新浪财经滚动新闻"
},
{
  "id": "eastmoney-rss",
  "type": "rss",
  "name": "东方财富",
  "url": "http://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2516&k=&num=50&page=1",
  "enabled": true,
  "priority": false,
  "topics": ["market"],
  "note": "东方财富网财经新闻"
},
{
  "id": "wsj-markets-rss",
  "type": "rss",
  "name": "华尔街日报市场",
  "url": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
  "enabled": true,
  "priority": true,
  "topics": ["market"],
  "note": "华尔街日报市场新闻"
}
```

### 国际新闻类

```json
{
  "id": "bbc-world-rss",
  "type": "rss",
  "name": "BBC World",
  "url": "http://feeds.bbci.co.uk/news/world/rss.xml",
  "enabled": true,
  "priority": true,
  "topics": ["international"],
  "note": "BBC世界新闻"
},
{
  "id": "reuters-world-rss",
  "type": "rss",
  "name": "路透社世界",
  "url": "https://www.reutersagency.com/feed/?taxonomy=best-topics&post_type=best",
  "enabled": true,
  "priority": true,
  "topics": ["international"],
  "note": "路透社世界新闻"
},
{
  "id": "cnn-world-rss",
  "type": "rss",
  "name": "CNN World",
  "url": "http://rss.cnn.com/rss/cnn_world.rss",
  "enabled": true,
  "priority": false,
  "topics": ["international"],
  "note": "CNN世界新闻"
}
```

### 国内新闻类

```json
{
  "id": "xinhua-rss",
  "type": "rss",
  "name": "新华社",
  "url": "http://www.news.cn/rss/china.xml",
  "enabled": true,
  "priority": true,
  "topics": ["domestic"],
  "note": "新华社国内新闻"
},
{
  "id": "people-daily-rss",
  "type": "rss",
  "name": "人民日报",
  "url": "http://www.people.com.cn/rss/politics.xml",
  "enabled": true,
  "priority": true,
  "topics": ["domestic"],
  "note": "人民日报政治新闻"
},
{
  "id": "thepaper-rss",
  "type": "rss",
  "name": "澎湃新闻",
  "url": "https://www.thepaper.cn/rss_channel_25950.xml",
  "enabled": true,
  "priority": false,
  "topics": ["domestic"],
  "note": "澎湃新闻时政"
}
```

### 军事新闻类

```json
{
  "id": "globaltimes-military-rss",
  "type": "rss",
  "name": "环球时报军事",
  "url": "https://mil.huanqiu.com/rss.xml",
  "enabled": true,
  "priority": true,
  "topics": ["military"],
  "note": "环球时报军事频道"
},
{
  "id": "guancha-military-rss",
  "type": "rss",
  "name": "观察者网军事",
  "url": "https://www.guancha.cn/military/rss",
  "enabled": true,
  "priority": false,
  "topics": ["military"],
  "note": "观察者网军事"
},
{
  "id": "defensenews-rss",
  "type": "rss",
  "name": "Defense News",
  "url": "https://www.defensenews.com/arc/outboundfeeds/rss/",
  "enabled": true,
  "priority": false,
  "topics": ["military"],
  "note": "国防新闻"
}
```

## 第三步：更新报告生成脚本

在 `scripts/generate-report.py` 中添加新主题的显示配置：

找到 `TOPIC_DISPLAY` 字典，添加：

```python
TOPIC_DISPLAY = {
    "llm": ("🧠", "AI / LLM"),
    "ai-agent": ("🤖", "AI Agent"),
    "crypto": ("💰", "区块链"),
    "frontier-tech": ("🔬", "前沿科技"),
    "market": ("📈", "市场行情"),
    "international": ("🌍", "国际新闻"),
    "domestic": ("🇨🇳", "国内新闻"),
    "military": ("⚔️", "军事新闻"),
}
```

## 第四步：测试

1. 运行数据采集：
```bash
python scripts/run-pipeline.py --defaults config/defaults --hours 24 --output test.json --force
```

2. 生成报告：
```bash
python scripts/generate-report.py --input test.json --template morning --output test-report.md --top-n 5
```

3. 检查报告中是否包含新的 4 个主题分类

## 注意事项

1. **RSS源可能失效**：部分中文网站的RSS可能不稳定，需要测试后调整
2. **编码问题**：确保所有RSS源返回UTF-8编码
3. **更新频率**：财经和新闻类更新频率高，建议每小时采集
4. **数据质量**：初期可能需要调整 `must_include` 和 `exclude` 关键词来提高准确性

## 推荐的RSS源（备选）

如果上述RSS源不可用，可以尝试：

- **财经**：FT中文网、第一财经、财新网
- **国际**：纽约时报中文网、卫报、法新社
- **国内**：央视新闻、中国日报、界面新闻
- **军事**：中国军网、新浪军事、搜狐军事
