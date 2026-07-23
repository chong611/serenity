# Hermes 本地 AI 情报采集器 —— 交给 Kimi 的建设指令（AI Radar 前置项目）

> **本文档的用法**：把整份文档交给 Kimi（K3 Swarm Max / Kimi Work / Kimi Code CLI），说："按本蓝图从 H0 开始建设 Hermes，每个里程碑验收通过再进入下一个。" 文档自包含。
>
> **与 AI Radar 的关系**：Hermes 是 `kimi3-ai-radar-blueprint.md`（下称 Radar 蓝图）的**前置本地版**——只做"采集 → 增量 → 分析 → 本地报告"，不做对外发布。目的：① 先在本地把采集与分析的质量调到可信；② 代码结构与 Radar 蓝图对齐（模块名/表结构兼容），建成后 Radar 的 M1-M3 直接平移复用 Hermes 的适配器和流水线。凡本蓝图未覆盖的通用约定（LLM 多供应商路由、prompt 稳定性、成本记账），沿用 Radar 蓝图 §2.2/§7/§16，不再重复。

---

## 0. 给 Kimi 的总指令

你是本项目总工程师。目标：一个**跑在用户个人电脑上的单机工具**——用户每天双击一次（或敲一条命令），Hermes 就把上次运行截止水位之后全网新增的 AI 动态、AI use case、新模型、新工具全部抓回本地 SQLite，用 LLM swarm 分析归类，产出当日情报报告和可检索的本地 dashboard，跑完自动在浏览器打开。

硬性纪律：

1. 按里程碑 H0→H4 推进，验收不过不前进；任何与本文档记载不符的外部 API 行为，立即停下报告。
2. **单机本地优先**：Python 3.11+ / SQLite / 无服务器依赖 / 无常驻进程；Windows 与 macOS 双平台一键可用。
3. **增量正确性是本项目的灵魂**（§3）：宁可少抓不可重复计费/重复分析；水位线逻辑必须过全部 §8 验收场景。
4. **零 LLM key 也能用**：没有配置任何 LLM key 时，采集与浏览功能完整可用，分析环节优雅跳过并提示。
5. 合规红线见 §11；LLM 后端约束沿用 Radar 蓝图 §0.1（禁用订阅侧 coding endpoint）。

## 1. 产品定义

**一句话**：个人本地的 AI 情报水库——一键增量抓取 + LLM 分析 + 本地报告/检索，为将来的 AI Radar 养数据、练流水线。

**用户故事**：
- 我今天双击 `run`，Hermes 从我上次运行的截止点续抓所有源的新内容，几分钟后浏览器自动打开今日报告。
- 我隔了三天没跑，再跑时它自动补齐这三天的空档，不重复、不遗漏。
- 我拿到一个新平台的 API key，把它填进 `keys.yaml`，下次 run 该平台的源自动激活。
- 我想找"上个月所有做客服自动化的 AI use case"，在本地 dashboard 搜索即得。

**产出物**（每次 run）：
- `reports/YYYY-MM-DD_HHMM.md`：本次运行报告（新增事件簇 Top N、新 use case、新模型/工具、值得读的原文清单）。
- 本地 dashboard（`hermes serve` 或 run 末尾自动启动）：事件流、use case 库、全文检索、源健康页。
- SQLite 数据库 `data/hermes.sqlite`：全部结构化数据，未来直接被 Radar 复用。

## 2. 关键机制

### 2.1 一键运行

- 入口三种，等价：macOS 双击 `Hermes.command`；Windows 双击 `hermes.bat`；终端 `python -m hermes run`。
- `run` 的流程：`bootstrap 自检（venv/依赖/Playwright 就绪）→ 读取 keys 探测可用源 → 增量采集（并发）→ 去重入库 → LLM 分析（如有 key）→ 生成报告 → 启动本地 dashboard 并打开浏览器`。
- **首次运行向导**：检测到空库时进入交互式向导——选择回填窗口（默认 7 天，可选 1/7/30 天）、确认可用 key、预估本次用量后开跑。
- 常用参数：`--since 2026-07-01`（手动指定起点，覆盖水位线）、`--sources hn,arxiv`（只跑指定源）、`--no-llm`（只采集）、`--full-refresh <source>`（重置单源水位线）、`--dry-run`（只打印将要抓取的范围）。
- 运行结束打印一行摘要：`新增 187 条 | 42 个事件簇(6 新) | 9 个新 use case | LLM 花费 $0.21 | 用时 4m12s`。

### 2.2 可插拔 API key（keys.yaml）

```yaml
# keys.yaml —— 有 key 的源自动激活，没有的自动降级或停用；每次 run 开头打印激活清单
llm:            # 多供应商路由，规格沿用 Radar 蓝图 §2.2（cheap/standard/premium 三档）
  kimi:     {api_key: "", base_url: "https://api.moonshot.ai/v1"}
  deepseek: {api_key: ""}
  dashscope: {api_key: ""}
data:
  github: ""        # 无 → 60 req/h 匿名；有 → 5000 req/h
  huggingface: ""   # 无 → 匿名限额；有 → 1000 次/5min
  reddit: {client_id: "", client_secret: ""}   # 个人非商业用途, 见 §11
  producthunt: ""   # 个人非商业 token, 见 §11
  x_read: ""        # ⚠️ 按量计费($0.005/条读取), 默认关闭, config 里显式打开才生效
notify:
  telegram: {bot_token: "", chat_id: ""}       # 可选: run 结束把摘要推到手机
```

### 2.3 LLM 分析（沿用 Radar 规格的本地化裁剪）

- 三档路由、prompt 字节级稳定、JSON mode、成本记入 `costs` 表——全部沿用 Radar 蓝图。
- 本地差异：并发默认 20（笔记本网络友好）；**单次 run 预算上限默认 $1.5**（config 可调），触顶后剩余条目标记 `pending_analysis`，下次 run 优先补齐。

## 3. 增量引擎（核心规格，必须逐条实现）

### 3.1 水位线模型

每个源在 `fetch_state` 表维护独立状态：

```sql
CREATE TABLE fetch_state (
  source_id INTEGER PRIMARY KEY REFERENCES sources(id),
  watermark_ts TEXT,        -- 已确认入库内容的最大 published_at (UTC ISO8601)
  last_cursor TEXT,         -- 分页游标类源的续抓点(如 API cursor)
  last_run_at TEXT,         -- 上次成功运行时刻(仅展示用, 不参与增量判定)
  backfill_done INTEGER NOT NULL DEFAULT 0,
  snapshot_hash TEXT        -- 快照型源(trending/页面diff)上次内容指纹
);
```

**铁律**：

1. **水位线 = 已成功入库条目的最大 `published_at`，绝不是运行时刻**。用运行时刻当水位会把"发布晚于上次抓取但被源延迟收录"的条目永久漏掉。
2. **重叠窗口**：每次从 `watermark_ts - overlap` 开始抓（默认 overlap=12h，逐源可调），配合唯一键去重，兜住迟到条目与源端时钟偏差。
3. **先入库、后推水位**：一页数据事务性写入成功后才允许推进水位；run 中途被 Ctrl+C/断网打断，已入库部分保留、水位停在最后完成页——下次 run 自然续抓，**不需要人工修复**。
4. **全库 UTC**：所有时间存 UTC ISO8601；展示层转本地时区。源返回无时区时间时按该源文档指明的时区解释并在适配器内注释。
5. 去重唯一键优先级：`(source_id, external_id)` → 无 external_id 用 `(source_id, url 规范化)` → 再无用 `(source_id, content_hash)`。跨源同 URL 不去重（留给聚类层判断，保留各源信号）。

### 3.2 三类源的增量语义

| 类型 | 例子 | 增量方式 |
|---|---|---|
| 时间线型（支持时间过滤/排序） | HN Algolia(`numericFilters=created_at_i>`)、arXiv、RSS、Reddit new、GitHub Search(created:>) | 按 `watermark - overlap` 起抓，翻页直到条目时间 < 起点或达 `max_pages`（逐源硬上限，防失控） |
| 游标型（只给 cursor 不给时间过滤） | 部分 API 的 feed | 存 `last_cursor` 续抓；cursor 失效(4xx)自动回退为时间线語义重抓 overlap 窗口 |
| 快照型（无时间概念） | GitHub Trending 页、HF trending 榜、pricing/changelog 页 | 每次抓完整快照，与 `snapshot_hash` 对应的上份快照做 diff，**新出现/变更的条目**作为增量产出，`published_at` 记为本次发现时刻并打 `discovered` 标记 |

### 3.3 RSS 的增量细则

- 优先用条件请求：保存并回发 `ETag`/`Last-Modified`（`fetch_state.last_cursor` 复用存储），304 直接跳过——大幅省流量。
- RSS 窗口有限（一般 20-50 条）：若 `now - watermark >` 该 feed 覆盖窗口（比如停跑一个月），feed 本身已丢中间数据——对配置了 `archive_url` 的源走存档页补抓，否则在报告中如实标注"该源存在 N 天不可恢复空档"，**不得假装无缝**。

## 4. 数据源目录

> 原则：比 Radar 蓝图更广（本地个人用途解锁了 Reddit/Product Hunt，见 §11）。逐源实现为独立适配器，`sources.yaml` 注册。标 ⚠️ 的由建设者在 H1 阶段实测确认后启用。

**第一梯队（无需任何 key）**：
- Hacker News：Algolia API（AI 关键词 + `created_at_i` 增量 + points 过滤）；Show HN 单独跑一路（use case 富矿）。
- arXiv：分类 RSS（cs.AI/cs.CL/cs.LG/cs.SE/stat.ML）+ API 补抓，1 req/3s。
- Hugging Face：models（trendingScore 快照型 + createdAt 时间线型双路）、`huggingface.co/papers` 每日精选、HF Blog RSS。
- 官方博客 RSS：OpenAI、DeepMind、HF；Anthropic/Mistral/Meta AI/xAI 走 Olshansk/rss-feeds + HTML-diff 兜底（同 Radar §2.3）。
- 聚合 newsletter：TLDR AI RSS、Smol AI 存档、Ben's Bites。
- GitHub 关键仓库 Releases：`github.com/{owner}/{repo}/releases.atom`（免 key、天然增量）——初始清单 ≥30 个核心仓库（vllm、llama.cpp、transformers、langchain、ollama、comfyui 等）。
- YouTube 频道 RSS：`youtube.com/feeds/videos.xml?channel_id=...`——初始 ≥15 个 AI 频道（官方发布会/头部技术博主），只取标题+描述+链接。
- Bluesky：公开 searchPosts API（AI 关键词，免 key）⚠️。
- 中文源：机器之心/量子位/InfoQ 中文等的 RSS 或 RSSHub 路由 ⚠️（H1 实测哪个稳定用哪个）。
- Techmeme（feed.xml）、lobste.rs（rss + ai tag）、dev.to（公开 API/RSS，ai tag）⚠️。
- pricing/changelog HTML-diff：同 Radar §6 清单。

**第二梯队（免费 key 增强）**：GitHub Search API（新 AI 仓库）、HF 带 token 提额。

**第三梯队（个人非商业 key，§11 约束）**：Reddit（r/LocalLLaMA、r/MachineLearning、r/OpenAI、r/singularity、r/artificial 的 new+top）、Product Hunt GraphQL（AI topic 每日新品——use case 富矿）。

**第四梯队（付费，默认关）**：X 读取 API（$0.005/条）——config 显式开启才生效，且必须设 `max_reads_per_run`。

## 5. 架构与仓库结构

```
hermes/
├── hermes/
│   ├── __main__.py        # CLI: run/serve/status/sources/backfill
│   ├── config.py  db.py  llm.py(=Radar路由)  prompts.py  budget.py
│   ├── state.py           # §3 增量引擎(水位线/重叠/快照diff), 独立模块+完整单测
│   ├── ingest/
│   │   ├── base.py        # 适配器基类: fetch_incremental(state)->items 统一契约
│   │   ├── hn.py arxiv.py hf.py github.py rss.py htmldiff.py
│   │   ├── youtube_rss.py bluesky.py reddit.py producthunt.py x_read.py
│   ├── analyze/
│   │   ├── score.py       # 相关性/新闻价值/分类(含 use_case)——prompt 同 Radar §7
│   │   ├── cluster.py     # FTS5 召回 + LLM 判定, 同 Radar
│   │   ├── usecase.py     # use case 结构化抽取(见 §6)
│   │   └── report.py      # 运行报告生成
│   ├── web/               # 本地 dashboard (FastAPI + 原生JS, 只读)
│   └── notify.py          # 可选 TG 摘要推送
├── Hermes.command  hermes.bat  Makefile
├── config.yaml  keys.yaml.example  sources.yaml
├── tests/                 # 含 §8 全部增量场景的可重复测试
└── data/  reports/
```

数据模型：沿用 Radar 蓝图 §5 的 `sources/raw_items/items/clusters/...` 全套（Hermes 就是它的子集实例），新增 `fetch_state`（§3.1）与 `use_cases` 表：

```sql
CREATE TABLE use_cases (
  id INTEGER PRIMARY KEY, item_id INTEGER NOT NULL REFERENCES items(id),
  title TEXT NOT NULL,          -- 一句话: 谁用AI做了什么
  industry TEXT, task TEXT,     -- 行业 / 任务类型(客服/编码/营销/科研...)
  tools TEXT NOT NULL DEFAULT '[]',  -- 用到的模型/框架/产品 JSON
  outcome TEXT,                 -- 效果/数据(仅源文有据)
  maturity TEXT CHECK(maturity IN ('idea','demo','production','company')),
  extracted_at TEXT NOT NULL);
```

## 6. 分析流水线

1. **打分**（cheap 档）：同 Radar §7 SCORER，category 枚举增加 `use_case`；丢弃线本地放宽（relevance<45 丢弃——本地是水库，宁多勿漏，硬盘便宜）。
2. **聚类**（cheap 档）：同 Radar §7。
3. **use case 抽取**（standard 档）：对 category ∈ {use_case, product, open_source} 且分数达标的条目跑：

```
SYSTEM (USECASE_EXTRACTOR):
判断给定内容是否描述了一个具体的 AI 应用案例(某人/公司用 AI 解决某问题)。
是 → 输出 {"is_use_case": true, "title": "谁用AI做了什么(一句中文)",
  "industry": "...", "task": "...", "tools": ["..."],
  "outcome": "源文中的效果/数字, 无则null", "maturity": "idea|demo|production|company"}
否 → {"is_use_case": false}
铁律: outcome 只许引用源文明确写出的内容。
```

4. **运行报告**（premium 档 1 次调用）：汇总本次新增，生成 md：本次窗口概览 / Top 事件簇 / 新 use case 列表 / 新模型与工具 / 建议深读清单（附理由）。

## 7. 本地 dashboard

页面：**今日/本次运行**（报告渲染）、**事件流**（时间线，按 category/entity 筛）、**Use Case 库**（按行业/任务/成熟度筛选+搜索——本产品差异化页面）、**全文检索**（FTS5）、**源健康**（各源水位线/上次状态/空档警告）。风格：本地工具优先信息密度，不追求华丽；`hermes serve` 独立启动，127.0.0.1 only。

## 8. 增量与幂等验收场景（tests/ 全部自动化，H1 验收硬门槛）

| 场景 | 模拟 | 必须行为 |
|---|---|---|
| I1 连续日运行 | mock 源数据按天推进，连跑 3 "天" | 每次只入库新窗口条目；0 重复；水位线单调推进 |
| I2 跳空 | 第 1 天跑，第 4 天再跑 | 第二次覆盖完整 3 天空档；RSS 窗口不足的源如实报告不可恢复空档 |
| I3 同日重跑 | 同一天连 run 两次 | 第二次新增≈0、LLM 花费≈0、耗时秒级 |
| I4 中断恢复 | 采集到一半 kill 进程 | 已入库页保留；重跑自动续抓；无重复无丢失 |
| I5 迟到条目 | mock 源事后补插一条 published_at 在水位线前 12h 内的条目 | overlap 窗口捞回它 |
| I6 时钟/时区 | 条目带 5 种时区格式 + 系统时区改为 UTC+8/UTC-5 各跑一遍 | 全库 UTC 一致，水位线判定不受系统时区影响 |
| I7 cursor 失效 | mock 游标型源返回 4xx | 自动回退时间线语义，不崩溃不重复 |
| I8 快照型增量 | trending 榜两次快照有 3 新 2 掉 | 只产出 3 条新增，掉榜不产生条目 |
| I9 --since 覆盖 | 带 --since 早于水位线 | 按 --since 抓，去重兜底，结束后水位线取 max 不回退 |
| I10 首次回填 | 空库 + 7 天回填 | 完整回填后 backfill_done=1，第二次 run 走正常增量 |

## 9. 里程碑与验收

| | 交付 | 验收 |
|---|---|---|
| **H0** | 骨架：CLI/DB/state.py 增量引擎/llm 路由/keys 探测/预算熔断 | `make test-h0`：state.py 单测覆盖 §8 的 I1/I3/I4/I6/I9/I10；keys.yaml 增删 key 后 run 开头的激活清单正确变化；零 LLM key 时 run 完整走通（分析跳过） |
| **H1** | 全部第一/二梯队源适配器 + 增量实测 | ≥40 源激活；§8 全场景绿；真实网络连跑 3 天（可用脚本模拟系统日期推进）验证增量；单次日常 run ≤10 分钟 |
| **H2** | 分析流水线 + use case 抽取 | 金标准 60 条判定一致率 ≥85%（沿用 Radar M2 方法）；use case 抽取在 30 条人工核对样本上无编造 outcome |
| **H3** | 报告 + dashboard + 一键体验 | Windows 与 macOS 双平台"双击到浏览器打开报告"全流程无需终端知识；报告 md 渲染正确；Use Case 库可筛可搜 |
| **H4** | 硬化与交接 | I2/I5/I7/I8 极端场景绿；30 天跳空实测；`HANDOFF.md`：写明哪些模块可被 Radar 直接复用及差异点 |

## 10. 压测场景

沿用 §8 之外补三条：P1 大新闻日 5× 量本地跑完 ≤25 分钟且预算熔断正确；P2 断网中途恢复（重试+续抓）；P3 笔记本睡眠唤醒后继续 run 不崩。

## 11. 合规（本地个人用途的特殊性）

1. Hermes 定位**个人非商业研究工具**：因此 Reddit 免费 API、Product Hunt 个人 token 可合规使用——**但这两个适配器移植进商业化的 AI Radar 时必须停用**，`HANDOFF.md` 里显式标注。
2. 其余沿用 Radar §11：robots.txt、限速礼仪、不做登录墙对抗、不整段转载（本地库存原文仅自用，对外输出仍走摘要+链接）。
3. X 读取按量计费源默认关，开启需 config 双确认（`enabled: true` + `max_reads_per_run`）。

## 12. 人类准备清单

必需：一台 Win/macOS 电脑 + Python 3.11+（bootstrap 自动建 venv 装依赖）。可选增强：LLM key ≥1 个（没有则纯采集模式）、GitHub/HF 免费 token、Reddit/PH 个人 key、TG bot（手机收摘要）。

## 13. 成本推演

纯采集 $0。含分析（默认预算帽 $1.5/run）：日常 run 实际 ≈$0.2-0.5（cheap 档打分为主），首次 7 天回填一次性 ≈$1-3。全月每天跑 ≈ **$10-20/月**，远低于 Radar，因为没有多平台文案生成与 QA 终审的量。
