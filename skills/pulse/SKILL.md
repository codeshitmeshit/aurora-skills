---
name: pulse
description: >
  📡 Pulse — 每日信息简报。
  设计为通过 cron 在早晚自动触发，也可手动执行。
  当用户说 "pulse"、"/pulse"、"简报"、"早报"、"晚报" 时使用此 skill。
---

# 📡 Pulse — 每日信息简报

一个综合性的每日简报，涵盖科技产品发布、开源趋势、精选新闻、播客更新、股票行情和天气预报。设计为每天早晚各运行一次，也支持手动触发。

## 语言

最终输出使用**简体中文**（zh-CN），产品名、仓库名、技术术语保留英文。

## 工作流概览

按顺序执行以下步骤。Step 1.5 运行 Python 预取脚本并行获取大部分数据源（约 1-3 秒）。后续步骤直接使用预取数据，**不要**对已覆盖的数据源再调用 `web_fetch`/`web_search`，除非预取出错。仅 Step 4b、4c 仍需 `web_search`。

---

### Step 1: 确定日期与时间上下文

1. 记录今天的日期和当前时间。
2. 判断是**早间**（14:00 之前）还是**晚间**（14:00+）运行——影响标题 emoji：
   - 早间 → 🌅
   - 晚间 → 🌆
3. 确定星期几——用于天气建议。
4. Product Hunt 发布在周一至周五（太平洋时间）。如果今天是周末，使用最近一个周五的排行榜并注明。

---

### Step 1.5: 运行预取脚本

```bash
cd <skill_directory>/scripts && python3 prefetch.py 2>/dev/null
```

返回一个 JSON，包含 `producthunt`、`github_trending`、`hacker_news`、`weather`、`podcasts`、`news_search` 数据——全部并行获取。

- **直接使用预取数据**用于 Step 2、3、4a、4b、4d、5 —— 不要再调用 `web_fetch`。
- 如果某个数据源的 `error` 字段不为 null，对该数据源回退到 `web_fetch`/`web_search`。
- 天气数据来自**高德天气 API**（国内稳定），新闻搜索来自**火山引擎联网搜索 API**。

---

### Step 2: Product Hunt（AI 相关，Top 3-5）

目标：获取今日 Product Hunt 排行榜中 **Top 3-5 个 AI 相关产品**。

**数据源**：使用 `prefetch.producthunt.items` 数组。回退：仅在预取出错时 `web_fetch` `https://www.producthunt.com/feed`。

1. 从列表中挑选 **Top 3-5 个 AI 相关产品**（AI 工具、LLM、ML 基础设施、AI Agent、AIGC、开发者工具、Golang/云原生工具等）。如果 AI 产品不足 3 个，用整体 Top 产品补充。
2. 每个产品收集：产品名、一句话描述、投票数（如有）、直链。
3. 写一句简短点评——为什么值得关注。

---

### Step 3: GitHub Trending（Top 5）

目标：获取 GitHub Trending（每日）**Top 5 仓库**。

**数据源**：使用 `prefetch.github_trending` 数组。每项包含 `name`、`description`、`language`、`stars_today`、`total_stars`、`url`。

1. 使用预取数据的前 5 个仓库。
2. 如果与用户兴趣相关（AI Agent、TypeScript、Python、Golang、Rust、云原生等），添加简短点评。

---

### Step 4: 获取与策划新闻和播客

这是最需要编辑判断的步骤。从多个来源收集新闻，然后严格筛选。

#### 4a: Hacker News — 科技热点

**数据源**：使用 `prefetch.hacker_news` 数组（每项包含 `title`、`url`、`points`、`comments`）。

1. 挑选 **3-5 条**与科技/AI/开发者最相关的高质量讨论。
2. 跳过纯招聘帖、Show HN 中不够重大的项目。

#### 4b: 科技公司 & AI 行业新闻

**数据源**：使用 `prefetch.news_search`（火山引擎联网搜索结果）。包含 `content`（AI 生成的新闻摘要）和 `references`（来源链接）。

1. 从 `content` 中提取重大新闻条目。
2. 结合 `references` 中的链接作为来源。
3. 只保留真正重大的新闻：财报、重大产品发布、领导层变动、监管行动、收购、新模型发布、重大研究突破。
4. 如果没有重大新闻，**跳过**此小节——不要凑数。

#### ~~4c: AI 行业新闻~~

已合并到 4b（火山引擎搜索同时覆盖科技公司和 AI 新闻��。

#### 4d: 播客更新

**数据源**：使用 `prefetch.podcasts` 数组（已过滤为 48 小时内更新，每项包含 `name`、`episode_title`、`episode_url`、`episode_date`、`shownotes`）。

播客列表（在 `prefetch.py` 中维护）：
硅谷101, 晚点聊, 张小珺Jùn｜商业访谈录

#### 4e: 策划规则（必须遵守）

在确定最终新闻列表前，严格执行以下过滤：

- **时效性**：事件必须发生在今天或即将发生。不包含昨天或更早的新闻，除非是持续发展中的事件。
- **重要性**：用户会不会想被打断来了解这条新闻？如果不会，跳过。
- **去重**：使用 `memory_search` 搜索 "Pulse" 查找近期简报。不要包含已在最近 Pulse 中出现的新闻。如果是旧新闻的新进展，标注「🔄 进展更新」。
- **结果**：全部新闻类别合计 **3-8 条**。宁少勿滥。

---

### Step 5: 加密货币行情

**数据源**：使用 `prefetch.crypto.ETH`（火山引擎搜索结果）。包含 `content`（ETH 实时行情摘要）。

从 content 中提取：当前价格（USD）、24h 涨跌幅、24h 最高/最低价。
如果 24h 涨跌幅 > 5% 或 < -5%，标注为异常波动。

---

### Step 6: 天气数据

**数据源**：使用 `prefetch.weather`。每个城市（北京海淀/杭州西湖/深圳南山/广州番禺）包含 `now`（实况）、`today` 和 `tomorrow`，各有 `high`、`low`、`desc`、`emoji`、`wind`。天气数据来自高德天气 API（区级精度）。

格式：列表（非表格），每个城市显示今明两天，含 emoji、描述、低温°C ~ 高温°C。

---

### Step 7: 去重检查

组装最终输出前：

1. 使用 `memory_search` 搜索 "Pulse" 查找近期简报。
2. 对比已收集的新闻与近期输出。
3. 移除重复内容。如果是有意义的更新，标注「🔄 进展更新」。

---

### Step 8: 组装输出

> **关键——输出以标题开始，不加任何前言。**
> 第一个字符必须是 `#`。不要有前导文字、状态更新、"数据已收集完毕"、"正在整理"等过渡句。

使用以下模板。所有板块标题和产品/仓库/新闻名**必须直接超链接**——不要单独列"来源"。

语言：中文（全角标点：，、：！？。）用于正文；英文用于产品名、仓库名和技术术语。

```markdown
# 📡 Pulse | {🌅 or 🌆} — {YYYY年M月D日}

## 🚀 Product Hunt

- **[Product Name](URL)** {upvotes}
简短介绍与点评（简体中文）。

- **[Product Name](URL)**
...

（3-5 项）

---

## 🔥 GitHub Trending

- **[owner/repo](https://github.com/owner/repo)** ⭐ {total stars} (+{today})
Description。{Language}。简短点评（简体中文）。

- **[owner/repo](URL)** ⭐ ...
...

（5 项）

---

## 📰 News

- **[Headline](URL)**
1-2 句摘要（简体中文）。

- **[Headline](URL)**
...

（3-8 项，如果是安静的一天可以更少）

---

## 🎙️ Podcasts（如有更新）

- **[节目名 - 单集标题](episode_url)**
shownotes 摘要（1-2 句简体中文重点总结）。

---

## 💰 Crypto

**Ethereum (ETH)**
- 当前价格：**${price}**
- 24h 涨跌：{emoji} **{change_pct}%**
- 24h 范围：${low} ~ ${high}

{if 涨跌 > 5% 或 < -5%: ⚠️ 异常波动提示}

---

## 🌤️ Weather

**🧱 北京·海淀**
- 实况：{emoji} {desc}，{temp}°C
- 今天：{emoji} {desc}，{low}°C ~ {high}°C
- 明天：{emoji} {desc}，{low}°C ~ {high}°C

**🏙️ 杭州·西湖**
- 实况 / 今天 / 明天（同上格式）

**🌊 深圳·南山**
- 实况 / 今天 / 明天（同上格式）

**🌺 广州·番禺**
- 实况 / 今天 / 明天（同上格式）

{综合四座城市天气，给出雨伞、防晒、洗车等建议}

---
```

### 格式规则

- **无前言** ⚠️：回复必须直接以 `# 📡 Pulse | ...` 开始。不要输出标题之前的任何文字。
- **标题层级**：`#` 顶级，`##` 板块，列表用于各条目。
- **链接**：每个产品、仓库、新闻标题必须是可点击的超链接。
- **天气 emoji**：使用合适的天气 emoji。
- **简洁**：每条点评最多 1-2 句。整个 Pulse 应在 2 分钟内可扫完。
- **不凑数**：如果某板块没有值得报道的内容，用一句话说明如"今天暂无重大新闻"。
- **中文标点**：中文正文使用全角标点。
- **不重复**：同一天不包含相同新闻。
