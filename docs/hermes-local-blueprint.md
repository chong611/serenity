# Hermes 本地 AI 情报采集器 —— 交给 Kimi 的建设指令（AI Radar 前置项目）

> **本文档的用法**：把整份文档交给 Kimi（K3 Swarm Max / Kimi Work / Kimi Code CLI），说："按本蓝图从 H0 开始建设 Hermes，每个里程碑验收通过再进入下一个。" 文档自包含。
>
> **与 AI Radar 的关系**：Hermes 是 `kimi3-ai-radar-blueprint.md`（下称 Radar 蓝图）的**前置本地版**——只做"采集 → 增量 → 分析 → 本地报告"，不做对外发布。目的：① 先在本地把采集与分析质量调到可信；② 代码结构与 Radar 对齐（模块名/表结构兼容），建成后 Radar 的 M1-M3 直接平移复用 Hermes 的适配器与流水线。
>
> **本版已并入一轮专家审查**（增量引擎 / 本地 UX / 对抗性 / 数据源四路），§3 增量引擎与 §14 本地体验为重写后的精确规格，务必逐条实现。凡引用 Radar 的通用约定（LLM 多供应商路由、prompt 稳定性、成本记账），沿用 Radar §2.2/§7/§16。

---

## 0. 给 Kimi 的总指令

你是本项目总工程师。目标：一个**跑在用户个人电脑上的单机工具**——用户每天双击一次，Hermes 就把上次运行截止水位之后全网新增的 AI 动态、AI use case、新模型、新工具全部抓回本地 SQLite，用 LLM swarm 分析归类，产出当日情报报告和可检索的本地 dashboard，跑完自动在浏览器打开。

硬性纪律：

1. 按里程碑 H0→H4 推进，验收不过不前进；任何与本文档记载不符的外部 API 行为，立即停下报告。
2. **单机本地优先**：Python 3.11+ / SQLite / 无服务器依赖 / 无后台常驻进程；Windows 与 macOS 双平台**非终端用户双击即可用**。
3. **增量正确性是本项目的灵魂**（§3）：宁可重抓（靠去重幂等吸收）不可丢数据，宁可少推水位不可跳空；水位线逻辑必须过 §8 全部验收场景。
4. **零 LLM key 也能用**：未配置任何 LLM key 时，采集、去重入库、确定性报告、dashboard 全部完整可用，仅 LLM 叙事分析优雅跳过并提示。
5. 合规红线见 §11；LLM 后端约束沿用 Radar §0.1（**禁用订阅侧 coding endpoint 作为运行期后端**）。
6. **失败要响**：本地工具最大的风险是"表面成功、实际早已停摆"。凡静默失败（源停摆、水位卡死、分析被预算截断）必须在报告与源健康页可见，不许假装无缝。

## 1. 产品定义

**一句话**：个人本地的 AI 情报水库——一键增量抓取 + LLM 分析 + 本地报告/检索，为将来的 AI Radar 养数据、练流水线。

**用户故事**：
- 我今天双击 `run`，Hermes 从我上次运行的截止点续抓所有源的新内容，几分钟后浏览器自动打开今日报告。
- 我隔了三天没跑，再跑时它自动补齐这三天的空档，不重复、不遗漏（RSS 窗口不足导致的真实空档会被如实标注）。
- 我拿到一个新平台的 API key，填进 `keys.yaml`，下次 run 该平台的源自动激活。
- 我想找"上个月所有做客服自动化的 AI use case"，在本地 dashboard 搜索即得。

**产出物**（每次 run）：
- `reports/YYYY-MM-DD_HHMM.md` + 同名 `.html`（自包含内联样式，server 挂了也能看）：本次运行报告。
- 本地 dashboard：事件流、use case 库、全文检索、源健康页。
- SQLite 数据库 `<用户数据目录>/hermes.sqlite`（§14 规定位置，不在仓库目录）：全部结构化数据，未来被 Radar 选择性复用。

## 2. 关键机制概览

### 2.1 一键运行（详细体验规格见 §14）

- 入口三种等价：macOS 双击 `Hermes.command`；Windows 双击 `hermes.bat`；终端 `python -m hermes run`。
- `run` 流程：`bootstrap 自检（Python/venv/依赖就绪，§14.1-14.3）→ 读 keys 探测可用源 → 增量采集（并发抓取、单 writer 串行入库）→ 去重 → LLM 分析（如有 key）→ 生成报告（确定性层 + 叙事层）→ 前台启动 dashboard 并打开浏览器`。
- **首次运行向导**（§14.7）：检测到该源 `backfill_done=0` 时，交互式选回填窗口（默认 7 天）、确认可用 key、预估用量后开跑；每问都有默认值，连按回车即全默认。
- 常用参数：`--since <date>`（手动起点，见 I9 语义）、`--sources hn,arxiv`、`--no-llm`、`--full-refresh <slug>`（§3.6）、`--purge-source <slug>`（删数据，与 full-refresh 区分）、`--dry-run`、`--no-serve`（不起 dashboard，供测试/脚本；**所有自动化测试与 I3 计时以此模式为准**）。
- 结束打印一行摘要：`新增 187 条 | 42 簇(6 新) | 9 新 use case | LLM $0.21 | 用时 4m12s | 2 源疑似停摆(见报告)`。

### 2.2 可插拔 key（keys.yaml 只存密钥）与 models.yaml（存映射）

```yaml
# keys.yaml —— 只存密钥。有 key 的源自动激活，无则降级或停用；run 开头打印激活清单
llm:
  kimi:      ""       # 密钥；base_url/价格在 models.yaml
  deepseek:  ""
  dashscope: ""
data:
  github: ""          # 无→60 req/h 匿名；有→5000 req/h
  huggingface: ""     # 无→匿名限额；有→1000 次/5min
  reddit: {client_id: "", client_secret: ""}   # 个人非商业, §11
  producthunt: ""     # 个人非商业, §11
  x_read: ""          # ⚠️ 按量计费($0.005/读), 默认关, config 显式开启+max_reads_per_run 才生效
notify:
  telegram: {bot_token: "", chat_id: ""}       # 可选: run 结束推摘要到手机
```

```yaml
# models.yaml —— 档位→模型映射（沿用 Radar §2.2 的 cheap/standard/premium 三档）
# base_url 与 price 由建设者在 H0 核实当日现价后填入；严禁填订阅侧 coding endpoint(§0.1/§11)
tiers:
  cheap:    {primary: {provider: kimi, model: kimi-k2.5},  fallbacks: [{provider: deepseek, model: deepseek-chat}]}
  standard: {primary: {provider: kimi, model: kimi-k2.6},  fallbacks: [{provider: dashscope, model: qwen-plus}]}
  premium:  {primary: {provider: kimi, model: kimi-k3},    fallbacks: [{provider: deepseek, model: deepseek-chat}]}
providers:
  kimi:      {base_url: "https://api.moonshot.ai/v1", price_in: null, price_out: null}   # H0 填现价
  deepseek:  {base_url: "https://api.deepseek.com/v1", price_in: null, price_out: null}
  dashscope: {base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1", price_in: null, price_out: null}
```

### 2.3 LLM 分析（沿用 Radar，本地化裁剪）

三档路由、prompt 字节级稳定、JSON mode、故障转移、成本记入 `costs` 表——全部沿用 Radar §2.2/§7/§16。本地差异：并发默认 20；**单次 run 预算帽默认 $1.5**（config 可调），触顶后剩余条目 `analysis_status='pending'`，下次 run 优先补（§3.7）。首次回填若预估用量超帽，向导提示临时上调本次预算（§3.7）。

## 3. 增量引擎（核心规格，逐条实现，附完整 §8 验收）

> 一句话心智：**水位线只沿"从旧水位起、时间上连续覆盖到的区间"推进；任何做不到连续覆盖的情形，宁可不推水位、靠 overlap+去重重抓，也不许跳过中间。**

### 3.1 状态表

```sql
CREATE TABLE fetch_state (
  source_id INTEGER PRIMARY KEY REFERENCES sources(id),
  watermark_ts        TEXT,     -- 已"连续覆盖"确认入库的最大源侧单调时间(UTC ISO8601)
  run_cursor          TEXT,     -- run 级临时分页进度(中断续抓用); run 完整结束后清空
  last_cursor         TEXT,     -- 游标型源的持久续抓点 / RSS 的 ETag+Last-Modified
  last_run_at         TEXT,     -- 仅展示, 不参与增量判定
  last_item_at        TEXT,     -- 最近一次真实新条目的时间(停摆检测, §3.8)
  empty_run_streak    INTEGER NOT NULL DEFAULT 0,   -- 连续零新增次数
  backfill_done       INTEGER NOT NULL DEFAULT 0,
  backfill_target_start TEXT,   -- 原始回填起点(回填中断续跑用, §3.5)
  coverage_gap        INTEGER NOT NULL DEFAULT 0    -- 存在未覆盖洞(截断/空档), 报告告警
);
```

### 3.2 六条铁律

1. **水位 = 源侧单调时间，不是运行时刻，也不一定是作者声称的发布时间**。每个适配器必须声明它的水位字段为"条目在该源可见/被收录的单调时间"：arXiv 用 announce/updated 日期（RSS 条目出现日）而非 submission；GitHub Releases 用 release 的 `published_at` 而非 tag commit 时间；RSS 用 `published→updated→dc:date` 回退链。用运行时刻当水位会漏掉"迟到收录"的条目。
2. **水位只沿连续覆盖推进**。时间线型源在**单次 run 内把 `watermark−overlap` 到最新的整个窗口抓完**（或抓到条目时间 < 起点），才允许一次性把 watermark 提交为本窗口最大源侧时间。窗口没抓完（中断/截断）时 **watermark 不动**，分页进度存 `run_cursor`，靠 overlap+去重在下次 run 续抓。
3. **抓取方向决定截断安全性**。凡 API 支持按时间升序或时间上下界过滤（HN Algolia `numericFilters=created_at_i>`、GitHub Search `created:A..B`、arXiv API、Bluesky `since/until`），**一律从 `watermark−overlap` 起按时间升序抓**；此时 `max_pages` 截断是安全的——水位推进到最后一条已入库条目时间，剩余窗口下次续抓。**仅支持降序**的源被 `max_pages` 截断时**禁止推水位**，置 `coverage_gap=1` 并告警，下次 run 优先用时间上界抓洞区间。
4. **未来时间条目不拖水位**。watermark 提交前 clamp 到 `min(候选, now_utc+5min)`；`published_at > now_utc+5min` 的条目照常入库但打 `future_dated`、不参与水位推进，源健康页计数告警。
5. **缺时间条目不参与水位**。走回退链后仍无时间的条目用 `first_seen_at` 入库并打 `no_pubdate`，不推水位；升序翻页的停止判定遇 null 时间条目一律视为"不满足 < 起点"继续翻页，靠去重键幂等兜底。
6. **先入库后推水位，同事务提交**。一页条目 + 该源 `fetch_state` 更新必须在**同一个 SQLite 事务**里提交（§3.9 单 writer）；任何页事务失败即中止该源本次抓取、水位不动。run 中途被打断，已提交页保留、水位停在最后完成状态，下次自然续抓，无需人工修复。

### 3.3 overlap（重叠窗口）

- 默认 `overlap_hours=12`，**逐源可调并写入 sources.yaml**；配合去重键吸收迟到条目与源端时钟偏差。
- **收录延迟大于 overlap 会丢数据**（arXiv announce 滞后 submission 1-3 天是典型）。因此：优先用源侧单调时间（铁律1）把延迟问题消灭在源头；无源侧单调时间可用的源，其 `overlap_hours` 必须 ≥ 实测最大收录延迟，H1 阶段实测记录各源延迟分布写回 sources.yaml。

### 3.4 三类源的增量语义

| incr_mode | 例子 | 增量方式 |
|---|---|---|
| `timeline` | HN Algolia、arXiv、RSS、Reddit new、GitHub Search、Bluesky、dev.to latest | 按 §3.2 铁律3，能升序则升序抓、截断安全；只能降序则整窗抓完才推水位 |
| `cursor` | 少数只给游标不给时间过滤的 API | 存 `last_cursor` 续抓；cursor 失效(4xx)自动回退为 timeline 语义重抓 overlap 窗口（I7） |
| `snapshot` | GitHub Trending 页、HF trending 榜、OpenRouter 模型清单、pricing/changelog、各客户案例列表页 | 见 §3.5 |

### 3.5 snapshot 源（重写：需完整快照表，不能只存 hash）

- 新增表存**上一份快照的规范化条目键集合**，不能只靠 `snapshot_hash`（哈希只能判整页变没变，算不了逐条 diff）：

```sql
CREATE TABLE snapshots (
  source_id INTEGER NOT NULL REFERENCES sources(id),
  taken_at  TEXT NOT NULL,
  items_json TEXT NOT NULL,          -- 本次快照的规范化条目(identity + change 字段)
  PRIMARY KEY (source_id, taken_at));
```

- **快路径**：整页指纹与上次相同则整体跳过（省算）。
- **逐条 diff**：每个 snapshot 适配器声明 `identity_fields`（判"新出现"）与 `change_fields`（判"内容变更"，默认空）。trending 类 `change_fields` 为空——只报新上榜，排名/分数/时间戳一律**排除**出指纹，否则每次 run 重复产出整榜、击穿 I3。pricing/changelog 类把价格/版本号/正文块列入 `change_fields`。
- **新快照写入与增量条目入库同事务**，防止"快照已更新但条目没入库→这批增量永久丢失"。
- **首次运行 baseline 模式**：`snapshot_hash/上一份快照为空`时，条目入库但打 `baseline` 标记，**不计入"本次新增"、默认不触发 LLM 分析**（避免首跑被整个 trending 榜灌满、烧光预算）；从第二份快照起才产出真正增量。
- 新增条目的 `published_at` 记为发现时刻并打 `discovered` 标记。

### 3.6 RSS 增量细则

- 条件请求：保存并回发 `ETag`/`Last-Modified`（存 `last_cursor`），304 直接跳过省流量。
- **RSS 窗口有限**（一般 10-50 条）：若 `now − watermark >` 该 feed 覆盖窗口（停跑很久 / feed 只留最近 15 条如 YouTube），中间数据已从 feed 掉出——配了 `archive_url` 的源走存档补抓，否则**置 `coverage_gap=1`，在报告中如实标注"该源存在约 N 天不可恢复空档"，不得假装无缝**（I2）。
- guid 不可信的 feed（生成器换版会重排 guid）：适配器声明 `guid_trusted=false`，改用规范化 link 做 `external_id`。

### 3.7 --full-refresh 与预算截断的数据关系（消除歧义）

- `--full-refresh <slug>`：**只清** `fetch_state` 的 `watermark_ts/run_cursor/last_cursor`、清 snapshot、置 `backfill_done=0` 并按该源原回填窗口重填；`raw_items/items/clusters/use_cases` **一律保留**；重抓命中去重键的条目**静默跳过、不重新分析**（守纪律3-宁可不重复计费）；仅当 `content_hash` 与库内不同且属声明的可变源才走"内容更新"路径。snapshot 源 full-refresh 后首份快照走 baseline。
- `--purge-source <slug>`：独立命令，删该源全部数据行，与 full-refresh 明确区分。
- **预算截断续跑**：`raw_items.analysis_status ∈ {pending, scored, skipped}`。预算帽触顶后未分析条目置 `pending`；下次 run **先按 `published_at` 降序补 pending 队列**再分析当日新增。首次回填预估超帽时向导提示临时上调本次预算（或回填 run 自动放宽为预估×1.5）。

### 3.8 停摆检测（静默失败必须响）

- 每源维护 `last_item_at`（最近一次真实新条目时刻）与 `empty_run_streak`。
- run 结束时，`now − last_item_at` 超过逐源阈值（如该源历史发文间隔 P95×3）的源在报告与源健康页标红"疑似停摆"。
- 连续 N 次（默认 3）零新增的 `cursor` 源，强制走一次 timeline 语义校验抓取（从最新抓到 `watermark−overlap` 边界），区分"真没新内容"与"cursor 指向死分支"（I13）。

### 3.9 SQLite 并发与去重（重写）

- **库配置**：WAL 模式 + `busy_timeout≥5000ms` + `foreign_keys=ON`。
- **单 writer 队列**：适配器并发抓取，但所有写操作经**单一 writer 串行执行**（抓取并发、写入排队）；杜绝多线程写 default-journal SQLite 的 `database is locked` 与"后页已入、前页失败"空洞。
- **去重键优先级**：`(source_id, external_id)` → `(source_id, normalized_url)` → `(source_id, content_hash)`。raw_items 对前两者建**部分唯一索引**（值非 NULL 时生效）。跨源同 URL 不去重（留给聚类层）。
- **URL 规范化规则**（统一实现，禁止各适配器各写一套）：scheme 归 https、host 小写去 www、去默认端口、去 fragment、剔除 `utm_*/ref/fbclid/gclid` 等跟踪参数（白名单外）、去尾斜杠、query 参数排序。
- **content_hash 仅限不可变源**（适配器声明 `immutable=true`）；可变内容源（Reddit/HN 标题可改、HTML 页字节常变、分数嵌正文）必须保证前两级键之一可用，重抓命中键时 **update-in-place**（更新正文/分数、保留 `first_seen_at` 与分析结果），仅当声明的关键内容字段变化超阈值才标 `content_updated` 并允许重分析。content_hash 计算范围逐适配器声明，排除计数/时间戳等易变字段。
- **源身份稳定键**：`sources` 表以 sources.yaml 的 `slug`（如 `hn`、`arxiv-cs-ai`）做 UNIQUE 自然键，启动按 slug **upsert 不重插**；重建库/重排 yaml 不产生新 source_id 孤儿。改名走 `hermes sources rename <old> <new>`（同步迁移 fetch_state 与历史归属）。

## 4. 数据源目录（已实测，替换全部占位）

> 原则：比 Radar 更广（本地个人用途解锁 Reddit/PH，见 §11）。逐源实现为独立适配器，`sources.yaml` 注册（schema 见 §5.2）。标 ⚠️ 的 H1 实测确认后启用。

**A. 无需任何 key（第一梯队）**
- Hacker News：Algolia API（AI 关键词 + `created_at_i` 升序增量 + points 过滤）；Show HN 单独一路（use case 富矿）。
- arXiv：分类 RSS（cs.AI/cs.CL/cs.LG/cs.SE/stat.ML）+ API 补抓，1 req/3s；**水位用 announce 日期**（铁律1）。
- Hugging Face：`api/daily_papers`（免 key JSON，`?date=` 天然按日增量，信噪比高于 arXiv 全量）、models（`sort=trendingScore` 走 snapshot + `createdAt` 走 timeline 双路）、HF Blog RSS。
- 官方博客 RSS：OpenAI `openai.com/news/rss.xml`、DeepMind `deepmind.google/blog/feed/basic/`、HF `huggingface.co/blog/feed.xml`；Anthropic/Mistral/Meta AI/xAI 走 Olshansk/rss-feeds + HTML-diff 兜底。
- 聚合 newsletter：TLDR AI `tldr.tech/api/rss/ai`、Smol AI 存档、Import AI `importai.substack.com/feed`、ChinAI `chinai.substack.com/feed`。
- GitHub Releases（免 key、天然增量，**已实弹验证**）：`github.com/{owner}/{repo}/releases.atom`，初始 ≥30 核心仓库（vllm、llama.cpp、transformers、langchain、ollama、comfyui、vercel/ai、ggml 等）。
- YouTube 频道 RSS：`youtube.com/feeds/videos.xml?channel_id=<UC...>`（**只 UC 开头 id**，仅最近 15 条→高频频道停跑几天即空档，按 §3.6 标注），初始 ≥15 个 AI 频道。
- Bluesky（**已确认**免 key）：`public.api.bsky.app/xrpc/app.bsky.feed.searchPosts?q=AI`，增量用 `since/until` 不用 cursor（官方 cursor 有 bug）。
- Techmeme `techmeme.com/feed.xml`（**已确认**，单 feed，pubDate+guid 去重）。
- lobste.rs（**已确认**）：主 feed `lobste.rs/rss` + tag `lobste.rs/t/ai,ml.rss`（**别用 top feed**，有跳转故障）。
- dev.to（**已确认**）：RSS `dev.to/feed/tag/ai` 为主 + API `dev.to/api/articles/latest?per_page=30` 补详情（别用默认按热度的 `/api/articles`）。

**B. use case 富矿（新增，专供 use_cases 表）**
- ZenML LLMOps Database `zenml.io/llmops-database`（snapshot diff）：1200+ 生产级 LLM 落地案例，公司/行业/架构/教训齐全，抽取近零成本。
- Anthropic 客户案例 `anthropic.com/customers`、OpenAI 客户故事 `openai.com/stories`（snapshot diff）：官方 use case 库，problem→solution→outcome 定式，outcome 有据。
- AWS ML Blog `aws.amazon.com/blogs/machine-learning/feed/`（**已核实** WP feed）：大量"某客户用 Bedrock/SageMaker 做了什么+效果数字"，量大，打分前关键词粗筛。
- Google Cloud Blog `cloudblog.withgoogle.com/rss/`（**已核实**）：AI/ML 客户故事，全站 feed 本地过滤 AI 关键词。
- VentureBeat AI `venturebeat.com/category/ai/feed/`、TechCrunch AI `techcrunch.com/category/artificial-intelligence/feed/`（**已核实**）：企业 AI 采用/融资/产品发布。

**C. 高信噪个人/社区源（新增，全部 Substack/WP 标准 feed）**
- Simon Willison `simonwillison.net/atom/everything/`（**已核实**）、Latent Space `latent.space/feed`、Interconnects `interconnects.ai/feed`。
- OpenRouter 模型清单 API `openrouter.ai/api/v1/models`（免 key，snapshot diff）：**最快的"新模型上线"探测器**，直接带定价字段。

**D. 中文源（实测后启用）**
- 量子位（**已确认** WP feed）：`qbitai.com/category/资讯/feed` 或站点 `/feed`。
- 36氪（**已确认**官方 RSS 中心）：`36kr.com/feed` 全站本地过滤，或 RSSHub `/36kr/news/latest`。
- 少数派 `sspai.com/feed`、爱范儿 `ifanr.com/feed`（**已确认** WP feed，全站过滤 AI）。
- InfoQ 中文（**已确认**仅 RSSHub）：`/infoq/topic/:id`，:id 为"AI&大数据"话题，H1 确认；**建议本地起 RSSHub docker**，别依赖公共 `rsshub.app`（限流）。
- 机器之心 ⚠️：先测官方 `jiqizhixin.com/rss` → 失败则对 `/articles` 列表页 HTML-diff（snapshot）→ 微信路由仅最后兜底。
- 新智元（微信兜底）⚠️：`rsshub.app/wechat/wasi/...`，依赖第三方 wasi 服务、脆弱，只做可选兜底并在源健康页监控。

**E. pricing/changelog HTML-diff**：OpenAI/Anthropic/Kimi/DeepSeek/阿里等的 pricing 与 changelog 页，H1 扩至 ≥10 页并把确切 URL 写入 sources.yaml。

**F. 付费（默认关）**：X 读取 `$0.005/条`，config 显式开启 + `max_reads_per_run` 才生效。

## 5. 架构、数据模型、sources.yaml schema

### 5.1 仓库结构

```
hermes/
├── hermes/
│   ├── __main__.py        # CLI: run/serve/status/sources/backfill/purge-source
│   ├── bootstrap.py       # 跨平台 Python/venv/依赖/路径逻辑(§14, 单测覆盖)
│   ├── config.py  db.py  llm.py(=Radar路由)  prompts.py  budget.py
│   ├── paths.py           # 用户数据目录/安装根常量(§14.4), 禁止依赖 cwd
│   ├── state.py           # §3 增量引擎(独立模块 + 完整单测)
│   ├── httpx_client.py    # 统一出网: 10s连接/60s读超时 + 退避重试 + monotonic 计时(§14.9)
│   ├── ingest/
│   │   ├── base.py        # 适配器基类: fetch_incremental(state)->items 统一契约
│   │   ├── hn.py arxiv.py hf.py github.py rss.py htmldiff.py snapshot.py
│   │   ├── youtube_rss.py bluesky.py devto.py reddit.py producthunt.py x_read.py
│   ├── analyze/ (score.py cluster.py usecase.py report.py)
│   ├── web/               # 本地 dashboard (FastAPI + 原生JS, 127.0.0.1 only, 只读)
│   └── notify.py
├── Hermes.command  hermes.bat   # 最薄启动壳(§14.6), 找到 Python 即移交 bootstrap.py
├── config.yaml  keys.yaml.example  models.yaml  sources.yaml
├── tests/                # §8 全部增量场景 + §10 压测
└── (数据/venv 不在此, 见 §14.4；reports/ 可在用户可见处)
```

### 5.2 数据模型

**建这些表**（Radar §5 子集 + Hermes 专属）：`sources`（slug UNIQUE）、`raw_items`、`items`、`clusters`、`cluster_items`、`costs`、`source_health`、`items_fts`、`fetch_state`（§3.1）、`snapshots`（§3.5）、`use_cases`。**不建** `briefs/brief_entries/renditions`（发布侧，Hermes 无对外发布）。

`raw_items` 关键增补（相对 Radar）：

```sql
-- 在 Radar raw_items 基础上增加/约束:
ALTER 概念: external_id TEXT, normalized_url TEXT, first_seen_at TEXT NOT NULL,
  analysis_status TEXT NOT NULL DEFAULT 'pending' CHECK(analysis_status IN ('pending','scored','skipped')),
  flags TEXT NOT NULL DEFAULT '[]',   -- future_dated/no_pubdate/discovered/baseline/content_updated
  immutable INTEGER NOT NULL DEFAULT 0;
CREATE UNIQUE INDEX ux_raw_extid ON raw_items(source_id, external_id) WHERE external_id IS NOT NULL;
CREATE UNIQUE INDEX ux_raw_url   ON raw_items(source_id, normalized_url) WHERE normalized_url IS NOT NULL;
```

```sql
CREATE TABLE use_cases (
  id INTEGER PRIMARY KEY, item_id INTEGER NOT NULL REFERENCES items(id),
  title TEXT NOT NULL, industry TEXT, task TEXT,
  tools TEXT NOT NULL DEFAULT '[]', outcome TEXT,
  maturity TEXT CHECK(maturity IN ('idea','demo','production','company')),
  extracted_at TEXT NOT NULL);
```

### 5.3 sources.yaml schema

```yaml
# 每源一条; incr_mode 与旧 kind 正交
- slug: hn                      # 稳定自然键(§3.9)
  adapter: hn                   # 对应 ingest/ 适配器
  incr_mode: timeline           # timeline | cursor | snapshot
  time_field_semantics: source_monotonic  # 声明水位字段语义(铁律1)
  overlap_hours: 12             # 默认12, 收录延迟大的源调大(§3.3)
  max_pages: 20                 # 默认20; 升序抓时截断安全(铁律3)
  ascending_supported: true     # 能否按时间升序/上下界过滤(决定截断是否安全)
  immutable: false
  guid_trusted: null            # 仅 rss 用
  archive_url: null             # RSS 空档补抓用(§3.6)
  identity_fields: [id]         # 仅 snapshot 用
  change_fields: []             # 仅 snapshot 用; trending 留空
  tier: C
  weight: 1.5
  params: {query: "AI OR LLM OR ...", min_points: 20}
```

## 6. 分析流水线

1. **打分**（cheap）：同 Radar §7 SCORER，category 枚举加 `use_case`。**丢弃规则（显式）**：仅 `relevance < 45` 丢弃，`newsworthiness` **不作丢弃条件**（本地宁多勿漏）；config 键 `discard_min_relevance: 45`。H2 金标准按此规则标注。
2. **聚类**（cheap）：同 Radar §7（FTS5 召回 + LLM 判定）。
3. **use case 抽取**（standard）：触发条件 `category ∈ {use_case, product, open_source}` 且 `relevance ≥ 60`（config `usecase_min_relevance: 60`，与丢弃线独立）。prompt：

```
SYSTEM (USECASE_EXTRACTOR):
判断给定内容是否描述具体 AI 应用案例(某人/公司用 AI 解决某问题)。
是 → {"is_use_case": true, "title": "谁用AI做了什么(一句中文)", "industry": "...",
  "task": "...", "tools": ["..."], "outcome": "源文明确写出的效果/数字, 无则null",
  "maturity": "idea|demo|production|company"}
否 → {"is_use_case": false}
铁律: outcome 只许引用源文明确写出的内容, 不得推断编造。
```

4. **运行报告（两层，关键）**：
   - **确定性层（代码模板，无 LLM 也必产出）**：本次窗口概览、新增统计、Top 事件簇（按 heat）、新 use case 列表、源健康与空档/停摆警告。§0 纪律4 与 §8 I2 的断言只针对这一层做字符串级校验。
   - **叙事层（premium，1 次调用，有 key 才有）**：导语、深读推荐及理由、趋势点评。无 key/`--no-llm` 时本层跳过并在报告注明"未启用 LLM 分析"。

## 7. 本地 dashboard

页面：**本次运行**（报告 HTML）、**事件流**（时间线，按 category/entity 筛）、**Use Case 库**（按行业/任务/成熟度筛+搜索——差异化页面）、**全文检索**（FTS5）、**源健康**（各源水位/上次状态/停摆/空档）。127.0.0.1 only，信息密度优先。生命周期见 §14.5。

## 8. 增量与幂等验收（tests/ 全自动化，均以 --no-serve 计；H1 硬门槛）

| 场景 | 模拟 | 必须行为 |
|---|---|---|
| I1 连续日运行 | mock 数据按天推进连跑 3 天 | 每次只入新窗口；0 重复；水位单调 |
| I2 跳空 | 第1天跑，第4天再跑 | 覆盖完整 3 天空档；RSS 窗口不足的源置 coverage_gap 并在报告确定性层标注 |
| I3 同日重跑 | 同天连跑两次 | 第二次新增≈0、LLM≈0、秒级 |
| I4 中断恢复(新→旧源) | 采集到一半 kill；**显式构造"先入最新页后中断"** | 已入页保留；水位**不动**；重跑续抓，无重复无丢失中间页 |
| I5 迟到条目 | 事后补插 published_at 在水位前 12h 内 | overlap 捞回 |
| I6 时区/时钟 | 5 种时区格式 + 系统时区改 UTC+8/UTC-5 各跑 + **含 null 时间条目** | 全库 UTC 一致；水位不受系统时区影响；null 时间条目用 first_seen_at 入库不推水位 |
| I7 cursor 失效 | 游标型返回 4xx | 回退 timeline 语义，不崩不重复 |
| I8 snapshot 增量 | 两次快照 3 新 2 掉；**含一个分数变化的 trending mock**；**首次快照走 baseline** | 只产出 3 新增；掉榜不产条目；分数变化不算新增(change_fields 空)；首跑 0 计入新增 |
| I9 --since 覆盖 | --since 早于水位 | 按 since 抓、去重兜底；结束后水位取 max **不回退** |
| I10 首次回填+中断 | 空库 7 天回填；**回填至第 3 天 kill 再重跑** | 回填按旧→新、每段推水位；重跑从当前水位续填直到覆盖 now 才 backfill_done=1；最终 7 天完整无重复 |
| I11 max_pages 截断 | 单窗口条目 > max_pages×page_size | 升序源连跑两次最终覆盖全部、水位单调；仅降序源置 coverage_gap 并下次抓洞 |
| I12 并发写+读 | 两 mock 源并发抓 + serve 同时读 | 零锁错、零空洞（WAL+单 writer 验证） |
| I13 静默停摆 | 200 空响应连续 3 次 | 触发"疑似停摆"告警；游标源强制校验抓取捞回真实新条目 |
| I14 未来时间 | 一条 published_at=now+30 天 | 入库打 future_dated；水位不被拖到未来；后续正常条目不丢 |

## 9. 里程碑与验收

| | 交付 | 验收 |
|---|---|---|
| **H0** | 骨架：CLI/paths/DB(WAL+单writer)/state.py/llm 路由+熔断/keys 探测/models.yaml | `make test-h0`（**均离线、无需真 key**）：migration 幂等且按 slug upsert；state.py 单测覆盖 I1/I3/I4/I6/I9/I10/I14；mock 供应商下预算设 $0.001→熔断异常抛出；mock 主选 503→切备选并留日志；keys.yaml 增删 key 后 run 开头激活清单正确变化；无 LLM key 时 run 完整走通（确定性报告产出、叙事层跳过） |
| **H1** | 全部 A/B/C 梯队适配器 + 增量实测 | §8 全场景绿；`≥40` 源 enabled（**计数口径**：GitHub releases 与 YouTube 各按 1 类计，独立站点/适配器源 ≥15）；pricing/changelog 扩至 ≥10 页且 URL 入 yaml；**真实网络验证**=间隔数小时的 ≥3 次真实 run，断言零重复、水位单调、无未捕获异常（真实增量不用伪造系统日期，伪造日期只用于 mock 测试）；单次日常 run ≤10 分钟 |
| **H2** | 分析流水线 + use case 抽取（**H2 起需 ≥1 真实 LLM key**） | 金标准 60 条判定一致率 ≥85%（按 §6 丢弃规则标注）；use case 抽取在 30 条人工核对样本上无编造 outcome |
| **H3** | 报告(双层) + dashboard + 一键体验 | **人类所在平台**实测"下载 zip→解压→双击→浏览器打开报告"全程无需终端知识（含首启 Gatekeeper/SmartScreen 通过、断网双击、填错 key 双击两个负例，见 §14）；**另一平台**用 CI（GitHub Actions windows-latest/macos-latest）跑 `python -m hermes run --dry-run --no-serve` 冒烟 + 启动脚本语法检查；关闭控制台后已打开的报告 HTML 仍完整可读 |
| **H4** | 硬化与交接 | I2/I5/I7/I8/I11/I13 极端场景绿；§10 的 P1/P2/P3 并入本里程碑执行；"30 天跳空"=把水位人工改到 30 天前再跑真实 run（写明步骤与断言）；`HANDOFF.md`：Radar 可复用模块及差异、**Reddit/PH 数据迁移排除脚本**（§11） |

## 10. 压测（并入 H4 验收）

- **P1 大新闻日**：mock 5× 量本地跑完 ≤25 分钟且预算熔断正确、pending 队列下次补齐。
- **P2 断网恢复**：采集中途断网，统一 client 超时+退避重试后续抓，无重复。
- **P3 睡眠唤醒**：采集中合盖 2 分钟后唤醒，run 在重试窗口内继续完成、不挂起（依赖 §14.9 的防睡眠+monotonic 计时+超时）。

## 11. 合规（本地个人用途的特殊性）

1. Hermes 定位**个人非商业研究工具**：故 Reddit 免费 API、Product Hunt 个人 token 可合规使用——**但这两个适配器移植进商业化 Radar 时必须停用**；且 §1 说"库被 Radar 复用"，因此**向 Radar 迁移/复用数据时，source 为 reddit/producthunt 的数据行必须一并排除**（HANDOFF.md 提供导出过滤脚本），不得随库带入商业用途。
2. 其余沿用 Radar §11：robots.txt、限速礼仪、不做登录墙对抗、不整段转载（本地库存原文仅自用，对外输出仍摘要+链接）。
3. X 读取按量源默认关，开启需 config 双确认（`enabled: true` + `max_reads_per_run`）。
4. LLM 后端：运行期只用各供应商正式开放平台 API；`models.yaml` 严禁出现 Kimi 订阅侧 coding endpoint（沿用 Radar §0.1）。

## 12. 人类准备清单

必需：一台 Win/macOS 电脑（bootstrap 自动装 Python 依赖，Python 本身按 §14.1-14.2 引导安装）。**H0-H1 可无 LLM key**（纯采集）；**H2 起需 ≥1 个真实 LLM key**。可选增强：GitHub/HF 免费 token、Reddit/PH 个人 key、TG bot（手机收摘要）。H3 双平台验收：人类在自己平台实测，另一平台走 CI（或人类提供第二台设备）。

## 13. 成本推演

纯采集 $0。含分析（默认预算帽 $1.5/run）：日常 run ≈ $0.2-0.5（cheap 档打分为主）；首次 7 天回填一次性 ≈ $1-3（超帽时向导提示上调，见 §3.7）。每天跑 ≈ **$10-20/月**，远低于 Radar（无多平台文案生成与 QA 终审）。

## 14. 本地一键体验规格（非终端用户双击即用，逐条实现）

### 14.1 Windows Python 探测
`hermes.bat` 依次探测 `py -3.13`/`py -3.12`/`py -3.11` → `python`，每个候选**实际执行** `-c "import sys; assert sys.version_info>=(3,11)"` 验证（微软商店的 App Execution Alias 桩会在此步失败/弹 Store，不能只看 `where`）。全失败：打印一句话指引，征得确认后 `winget install -e --id Python.Python.3.12`，或用默认浏览器打开 python.org 并提示"安装时勾选 Add python.exe to PATH"。

### 14.2 macOS Python 探测
`Hermes.command` 依次探测 `/Library/Frameworks/Python.framework/Versions/{3.13,3.12,3.11}/bin/python3`（python.org 官方 pkg）→ `/opt/homebrew/bin/python3` → `/usr/local/bin/python3` → 最后才 `/usr/bin/python3` 且**先确认 `xcode-select -p` 成功**再校验版本（避免触发 CLT 安装弹窗；CLT 自带 3.9 不满足）。全失败：`osascript` 弹窗指引去 python.org 下载 3.11+ pkg。

### 14.3 依赖安装（bootstrap 失败处理）
requirements 全量锁版本且保证 win/mac × x64/arm64 均有 wheel，`pip install --only-binary=:all:`（禁现场编译）。装前 3s 探测 pypi.org，失败自动切清华/阿里镜像（config 可覆盖）。全程 tee 到 `logs/bootstrap.log`。**任何失败窗口必须保留**（bat 用 `pause`，.command 用 `read -n1`），打印 ≤3 行中文诊断（网络/磁盘/Python 版本三类）+ 日志绝对路径。

### 14.4 路径（避开云同步与 cwd 陷阱）
venv 与数据库默认**不放仓库目录**：Windows `%LOCALAPPDATA%\Hermes\{venv,data}`，macOS `~/Library/Application Support/Hermes/{venv,data}`（天然不被 OneDrive/iCloud 同步）；`reports/` 的 md/html 可留用户可见处（纯文件无锁）。bootstrap 检测安装路径含 OneDrive/`com~apple~CloudDocs`/Dropbox 特征时打印警告。程序内所有路径基于 `paths.py` 的安装根/用户数据目录常量，**禁止依赖 cwd**。

### 14.5 dashboard 生命周期（解决"无常驻进程"矛盾）
每次 run 除 md 外渲染**自包含静态 HTML**（内联 CSS），浏览器**先打开它**——server 死掉报告仍可读，这是双击用户的保底。dashboard 在**前台控制台运行并阻塞**，窗口内常驻提示"关闭此窗口将退出浏览界面（今日报告已存为文件，不受影响）"；`serve --idle-timeout` 默认 2 小时无请求自动退出以兑现"无后台常驻"。用户 Ctrl+C/关窗即整体退出，不留后台进程。`--no-serve` 供测试/脚本。

### 14.6 启动壳与编码
`Hermes.command` 首行后 `cd "$(dirname "$0")"`；`hermes.bat` 用 `cd /d "%~dp0"`，所有路径展开加引号（兼容用户名/路径含中文空格）。`hermes.bat` 本体仅 ASCII（中文提示交给 Python 打印），开头 `chcp 65001 >nul` 且 `set PYTHONUTF8=1`。两壳保持最薄：找到 Python 即移交 `bootstrap.py`，跨平台逻辑全在 Python 内并单测。

### 14.7 首启向导
每问有明示默认值，连按回车即全默认开跑（回填 7 天、跳过可选 key）；非法输入重问不崩；Ctrl+C/关窗视为放弃、不留半初始化状态（该源 backfill_done 保持 0，下次重进向导）。可选增强：向导改在浏览器 `/setup` 页完成，与"最终界面在浏览器"一致。

### 14.8 分发与首启摩擦
- macOS：README/首启指引含带截图的 Gatekeeper 通过步骤，分 ≤14（右键→打开）与 15+（系统设置→隐私与安全性→仍要打开）两版，说明 TCC 弹窗点"允许"；打包脚本先 `chmod +x` 再压缩以保留可执行位。可选增强：$99/年账号做签名+公证 .app 彻底免弹窗。
- Windows：入口保持**纯文本 .bat**（误报率远低于打包 exe，**禁止用 PyInstaller/单文件 exe 替代 bootstrap**）；首启指引含 SmartScreen"更多信息→仍要运行"截图；首装 Defender 扫 venv 数千文件会慢，文案管理预期（"首次安装约 X 分钟"）。
- 错误呈现：顶层统一异常处理，完整 traceback 只进 `logs/hermes-YYYYMMDD.log`（轮转 14 天），控制台打 ≤3 行中文归因（DNS/超时→"网络问题"；401/403→"某 key 无效，检查 keys.yaml 第 X 项"；database is locked→"数据库疑似被云盘同步占用"）+ 日志路径；采集类错误不终止 run（单源失败记源健康页，整体继续）；Windows 异常退出前 `pause`。

### 14.9 网络/睡眠/端口
- 所有出网经 `httpx_client.py`：连接 10s / 读 60s 超时 + 指数退避重试 ≤3 次（P2 断网恢复的基础）；限速/计时一律 `time.monotonic`，禁墙钟差值（睡眠跨越会错乱）。
- run 期间防睡眠：`Hermes.command` 用 `caffeinate -i` 包裹进程；Windows 调 `SetThreadExecutionState(ES_CONTINUOUS|ES_SYSTEM_REQUIRED)`，run 结束释放。
- Playwright 懒安装：适配器标 `needs_browser: true`（htmldiff 优先纯 HTTP，仅确需 JS 渲染才标）；bootstrap 默认不装 Playwright，首次有 needs_browser 源被激活时才提示"需下载 Chromium 约 200MB [安装/本次跳过这些源]"，国内网络自动设 `PLAYWRIGHT_DOWNLOAD_HOST` 镜像。
- 端口与单实例：默认冷门端口（如 8321），被占则向上扫至多 10 个，浏览器开实际端口；`GET /api/health` 返回 `{app:"hermes",version,db_path}`，启动前探测已占端口是否同库 Hermes，是则不起新进程直接开浏览器；数据目录放 flock 锁，第二个 run 实例检测到锁给人话提示并退化为只开浏览器，**绝不并发写库**。
