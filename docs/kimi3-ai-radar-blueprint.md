# AI Radar（雷达日报）—— 交给 Kimi K3 Swarm 的完整建设指令

> **本文档的用法**：把整份文档原样交给 Kimi（kimi.com 的 K3 Swarm Max / Kimi Work / Kimi Code CLI 均可），并说一句："按这份蓝图从 M0 开始建设，每完成一个里程碑跑完验收测试再进入下一个。" 文档自包含：产品定义、已验证的外部事实、架构、数据模型、源清单、每个模块的规格与验收标准、swarm prompt 模板、压测场景、上线 checklist 全部在内。
>
> **建设与运行的分工**：**建设期**用 Kimi 订阅套餐（K3 Swarm Max / Kimi Code）读本蓝图、写代码、跑验收——订阅额度只花在建设上；**运行期**建成的系统通过 **LLM API 自主工作，且不锁定单一供应商**：LLM 层是多供应商路由（§2.2），Kimi API 为默认主选，DeepSeek/Qwen(DashScope)/GLM/Gemini 等按"每阶段最便宜够用"原则配置为备选与故障转移，全部走 OpenAI 兼容接口。注意：**建设期就需要至少一个真实 API key**（M0 起的验收测试要求系统真实调用自测），上线前至少配好主选+1 个备选供应商的 key。
>
> 文档内所有外部事实（API 价格、限额、平台政策）均于 **2026-07-23** 经多源交叉验证，标注在 §2。若开工时间距此超过 1 个月，Kimi 应先复核 §2 中标注 ⚠️ 的条目再动工。

---

## 0. 给 Kimi 的总指令

你是本项目的总工程师（orchestrator），可调度 sub-agent 并行完成子任务。目标：建成一个**7x24 全自动运行的 AI 领域双语情报系统**，每天自动完成"采集 → 打分 → 聚类 → 写作 → 质检 → 分发"全链路，人类每天只需 ≤5 分钟处理两个半自动平台的一键发布。

硬性纪律：

1. **按里程碑推进**（M0→M6，见 §12），每个里程碑有可执行的验收测试，不通过不得进入下一阶段。
2. **诚实报告**：任何验收不通过、任何外部 API 与 §2 记载不符，立即停下报告，不得默默绕过。
3. **合规红线**（见 §11）不可协商：不做反检测浏览器自动化、不绕过平台风控、不整段转载原文、该打的 AI 标注必须打。
4. **成本熔断**（见 §16）必须最先实现：任何 LLM 调用都要过成本表，日预算触顶自动降级。
5. 所有代码 Python 3.11+，SQLite 存储，单 VPS 可跑，不引入 Kafka/K8s 之类的重型件。

### 0.1 建设期操作要点（Kimi 订阅侧，2026-07-23 核验）

- **怎么开工**：Kimi Code CLI `/login` 用订阅账号 OAuth 登录即可（额度与网页版共享）；也可在 kimi.com 网页版 / Kimi Work 里以 K3 Swarm 直接执行本蓝图。完整 Agent Swarm 按官方 2026-05 文档需 **Allegretto 档及以上**（K3 发布后有第三方报道称低档位也有 2-4 并发的轻量 Swarm，以你账号页面实际提示为准）。
- **额度机制**：订阅额度统一池按 token 扣减、按月刷新；Kimi Code 权益另按 **7 天周期**刷新，叠加 5 小时滚动频控（约 300-1,200 次请求/5 小时、最多 30 并发，视档位）。Swarm 任务耗额度显著更快——建设时**逐里程碑推进比一次性全量并发更省额度**；验收测试可用 CLI 的 Print 模式（`kimi --print -p "..."`，官方支持脚本/CI 用法，退出码 0/1/75）无头执行。
- **⚠️ 合规红线（对建设者 Kimi 的硬性约束）**：订阅与开放平台 API 是**两套独立计费体系**，订阅费不含 API 调用。订阅侧的 coding endpoint（`api.kimi.com/coding/v1`）官方仅许可在受支持的编程工具内个人使用——**严禁把它配置成本系统运行期的 LLM 后端**。`models.yaml` 里只允许出现开放平台（`api.moonshot.ai`/`api.moonshot.cn`）及其他供应商的正式 API endpoint。

---

## 1. 产品定义

**一句话**：帮中文开发者/自媒体人/技术选型者追海外 AI 动态的双语情报雷达——每天早上 8 点一份中文日报（附英文原文链接），重大事件 24 小时内即时快讯，配一个可检索的 Web dashboard。

**内容形态与节奏**：

| 产物 | 节奏 | 内容 |
|---|---|---|
| 每日雷达日报 | 每天 08:00（北京时间） | 8-15 个事件簇：中文标题+双语摘要+为什么重要+原文链接 |
| 即时快讯 Flash | 触发式，每天 ≤3 条 | 重大发布/收购/开源（需 ≥2 独立源或官方一手源确认） |
| Dashboard | 实时 | 全量事件流、按类别/实体/时间检索、历史归档 |
| 周报 | 每周日 | 本周 Top10 + 趋势盘点（由日报数据自动汇总） |

**分类体系**（category 枚举）：`model_release`（新模型/权重）、`product`（产品/功能上线）、`open_source`（仓库/工具）、`research`（论文/技术博客）、`funding`（融资/收购）、`policy`（监管/政策）、`pricing`（价格/changelog 变更）、`drama`（行业动态/人事）。

**变现钩子**（本期只做埋点，不做支付系统）：免费层 = 日报公开发布；付费层入口 = dashboard 的"自定义关注赛道/关键词订阅 + 全量历史检索 + API"，页面预留订阅按钮位。

---

## 2. 已验证的外部事实与硬约束（2026-07-23 核验）

**这一节是整个设计的地基，每一条都改变了架构决策。**

### 2.1 分发渠道

| 渠道 | 事实 | 架构决策 |
|---|---|---|
| **Telegram** | Bot API 完全免费，频道推送无总量限制 | ✅ 全自动，主力免费渠道 |
| **X (Twitter)** | ⚠️ 2026-02 起 API 转按量计费，免费层对新开发者关闭。纯文字帖 $0.015/条，**含链接帖 $0.20/条**，读取 $0.005/条。自动发帖合规但**必须启用 Automated account label** 并关联人工账号。账号侧：未认证账号 50 条原创/天 | ✅ 全自动，但省钱策略：thread 正文纯文字（不带链接），只在收尾帖放 1 个 dashboard 链接。日成本 ≈ $0.11-0.35 |
| **Email** | Buttondown 有完整 REST API（创建/定时/发送），官方称全套餐可用（含免费 100 订阅者档）；⚠️ 有第三方称部分功能移入付费墙，注册后先实测 API 发信。Substack 无发布 API，排除 | ✅ 全自动（Buttondown） |
| **小红书** | ❌ 官方开放平台仅对企业电商场景开放，个人无发布 API。浏览器自动化发布 = 真实封号风险（2025 封号潮、AI 查重、相似度>70% 判矩阵刷量；平台起诉绕过技术措施方 2025 年终审判赔 490 万）。第三方矩阵工具（蚁小二 998 元/月等）本质也是模拟操作，同源风险。规格：标题 ≤20 字、正文 ≤1000 字、图 ≤18 张、推荐 3:4 竖版 1080×1440 | ⚠️ **一键队列**：系统全自动产出卡片图+文案+标签，推送到管理群，人在 App 里一键发布（<2 分钟/天）。**禁止**做反检测自动化 |
| **微信公众号** | ⚠️ 2025-07 起个人主体账号的发布接口（freepublish）被回收；个人订阅号无法认证；**草稿箱 API（draft/add）个人订阅号仍可用** | ⚠️ **半自动**：排版好的 HTML 自动推入草稿箱，人在后台/公众号助手点群发（<1 分钟/天） |
| **Threads** | ✅ 官方 API 免费；**只发自己账号无需完整 App Review**（Meta 开发者后台建 app 启用 Threads use case + `threads_content_publish`，自己账号授权即可）；支持文字/单图/轮播(2-20 项)；限 250 条/天/账号；图片必须公网可访问 URL（API 拉取，不支持直传）；API 无定时参数，由本系统服务端定时触发 | ✅ 全自动 |
| **Instagram** | ⚠️ 官方 Content Publishing API 免费，但须 **Professional 账号**（Creator/Business）；走 2024 起的 Instagram Login 路线**无需关联 Facebook 主页**；把自己账号加为 app 测试者即可发自己账号（免 App Review）；限 100 条/天；轮播 API 上限 10 项；图片**仅 JPEG** 且需公网 URL | ✅ 全自动（一次性账号设置后） |
| **Bluesky / Mastodon** | ✅ 完全开放免费无审核（Bluesky 按积分约 1.1 万帖/天上限；Mastodon 默认 300 帖/3 小时），Bluesky 图片可直传 blob | ✅ 全自动（发英文版，触达海外受众） |
| **LinkedIn** | ⚠️ `w_member_social` 自助可得（Share on LinkedIn 产品自动启用），但建 app 需关联一个公司主页做验证（可自建一个）；实测约 100-150 次/天 | ✅ 全自动（**可选渠道**，config 开关默认关） |
| **Facebook 主页** | ⚠️ 技术可行但 app 不过 App Review + 商业验证时帖子**仅管理员可见**；个人 profile 的 API 发帖 2018 年起已不可行 | ❌ 本期不做（个人开发者性价比低，订阅涨了再议） |
| **抖音** | ❌ 官方 2024-07 已全面关闭"代投稿"API（个人/企业都不能静默发布），仅剩拉起 App 人工确认的分享 SDK | ⚠️ 一键队列可选：素材备好人工发 |
| **即刻/知乎** | 无官方发布 API，逆向方案违反平台规则 | ❌ 本期不做（文案在队列里附上，人愿意贴就手动贴） |

### 2.2 LLM 层：多供应商路由（Kimi 为默认主选，不锁定）

**原则**：运行期的每个流水线阶段绑定一个**逻辑档位**而非具体模型——`cheap`（海量打分/聚类）、`standard`（摘要/平台文案）、`premium`（QA 终审/主编）。档位到具体模型的映射写在 `models.yaml`，每个档位配**主选 + ≥1 个备选**（不同供应商），全部走 OpenAI 兼容接口，切换只改配置不改代码。主选连续失败或熔断时自动故障转移到备选，全部失败才进降级模式（§10）。

**候选池**（均为 OpenAI 兼容或有兼容层；⚠️ 具体价格由 Kimi 在 M0 阶段逐一核实当日现价后写入 `models.yaml` 的 pricing 字段，不得沿用本文档记忆值）：cheap 档候选 kimi-k2.5、DeepSeek chat 系、Qwen Flash/Turbo（DashScope）、GLM Flash 系（有免费档）、Gemini Flash 系；standard 档候选 kimi-k2.6、DeepSeek、Qwen Plus；premium 档候选 kimi-k3、各家旗舰。成本记账（§16）按 `costs` 表统一折算 USD，与供应商无关。

以下为**默认主选 Kimi** 的已验证事实：

| 项 | 事实 |
|---|---|
| 模型 | 旗舰 `kimi-k3`（$3/$15 每百万 token，缓存命中 $0.30；国内 ¥20/¥100，缓存 ¥2；1M 上下文）；`kimi-k2.6`（$0.95/$4.00，缓存 $0.16）；`kimi-k2.5` 低价档（$0.60/$2.50-3.00，缓存 $0.10）。K2 老 preview/thinking 系列已于 2026-05 退役 |
| 速率 | 按累计充值分 Tier：**Tier 1（累计 $10）= 200 RPM / 50 并发**；Tier 2（累计 $100）= 5,000 RPM / 200 并发。⚠️ 开工前在控制台确认本账号实际 Tier |
| 兼容性 | 完全兼容 OpenAI SDK（base_url = `https://api.moonshot.ai/v1`，国内 `api.moonshot.cn/v1`）。支持 JSON mode / 结构化输出 / tool calls |
| 缓存 | **自动前缀缓存**，无需配置——所有 swarm agent 的 system prompt 必须字节级稳定（变量放 user message），缓存命中省 80-95% 输入成本 |
| Batch | 有 `/v1/batches` 端点但**无折扣**，本项目用实时并发即可 |
| Embedding | ❌ 官方无向量 API。v1 用 SQLite FTS5 BM25 召回 + LLM 判定聚类，不引入向量库 |

**默认档位映射**（models.yaml 初始值，可换）：`cheap` → `kimi-k2.5`（打分/聚类/巡检）；`standard` → `kimi-k2.6`（摘要/平台文案）；`premium` → `kimi-k3`（QA 终审/主编，每天调用最少、质量要求最高）。本文档后文出现的具体模型名均指这个默认映射。

### 2.3 数据源（全部不依赖 X）

| 源 | 状态 | 访问方式 |
|---|---|---|
| Hacker News | ✅ 免费无鉴权 | Algolia API（`hn.algolia.com/api/v1/search_by_date`，支持 `points>N` 过滤，~1 万次/小时）+ Firebase API 兜底 |
| Hugging Face | ✅ 免费 | `huggingface.co/api/models?sort=trendingScore&direction=-1`（含 downloads/likes/createdAt；带免费 token 1000 次/5 分钟）；另抓 `huggingface.co/papers` 每日精选论文（替代生扫 arXiv） |
| GitHub | ✅ 可行 | Search API `q=topic:llm created:>DATE sort:stars`（个人 token 30 次/分钟）+ 抓 `github.com/trending` 页面（无官方 API，HTML 多年稳定但要有失败告警） |
| arXiv | ✅ 免费 | 官方分类 RSS（`rss.arxiv.org/rss/cs.AI` 等）为主；API 补充，**遵守 1 请求/3 秒** |
| 官方博客 RSS | ✅ | OpenAI `openai.com/news/rss.xml`、DeepMind `deepmind.google/blog/feed/basic/`、HF `huggingface.co/blog/feed.xml` |
| 无 RSS 的官方博客 | ⚠️ | Anthropic/Mistral/Meta AI/xAI 无官方 feed → 订阅 [Olshansk/rss-feeds](https://github.com/Olshansk/rss-feeds)（GitHub Action 每小时生成），**同时自建 HTML-diff 兜底**（该项目挂了就切换） |
| 聚合 newsletter | ✅ | TLDR AI（`tldr.tech/api/rss/ai`）、Smol AI news（`news.smol.ai/issues/` 网页存档 + buttondown RSS）——作为"二级验证源"提升召回与佐证 |
| SaaS pricing/changelog | ✅ 自建 | HTML 快照 diff + LLM 解析变更（本系统的差异化卖点之一） |
| Reddit | ❌ v1 排除 | 2026-05 起无鉴权 .json 返回 403；免费 API 需预审批且限非商业 |
| Product Hunt | ❌ v1 排除 | API 个人 token 限非商业用途，本项目有商业化意图，不碰 |

---

## 3. 系统架构

```
┌──────────── L1 采集 ingest（每30分钟） ────────────┐
│ api_fetcher(HN/HF/GitHub/arXiv) rss_fetcher(~60源) │
│ htmldiff_fetcher(changelog/pricing ~40页)          │
└──────────────────────┬─────────────────────────────┘
                       ▼ raw_items（URL/hash 精确去重）
┌──────────── L2 打分 score（swarm, k2.5）───────────┐
│ 关键词预过滤(代码,零成本) → 每条1个agent:           │
│ 相关性0-100/新闻价值0-100/类别/实体/一句话摘要      │
└──────────────────────┬─────────────────────────────┘
                       ▼ items（低分丢弃）
┌──────────── L3 聚类 cluster（k2.5）────────────────┐
│ FTS5 BM25召回近72h相似簇top5 → agent判定:           │
│ 同事件并入 / 新开簇；簇热度=Σ源权重×跨源数×新鲜度   │
└──────────────────────┬─────────────────────────────┘
              ┌────────┴────────┐
              ▼ 热度≥阈值(即时)  ▼ 每日07:10
     ┌─ Flash 快讯 ─┐   ┌── L4 日报编译（k2.6+k3）──┐
     │ ≥2独立源确认  │   │ 选簇排序 → 每簇:双语标题+  │
     │ 每天≤3条      │   │ 摘要+why-it-matters+源引文 │
     └──────┬───────┘   └────────────┬──────────────┘
            │                        ▼
            │          ┌── L5 平台变体工厂（k2.6, swarm）──┐
            │          │ X thread/TG/Email/小红书卡片/     │
            │          │ 公众号HTML/dashboard JSON 并行生成 │
            │          └────────────┬──────────────────────┘
            │                       ▼
            │          ┌── L6 QA 门（k3, 独立agent）───────┐
            │          │ 每条论断↔源文引文核对; 数字溯源;   │
            │          │ 字数/格式lint; 不过→重写1次→丢弃  │
            │          └────────────┬──────────────────────┘
            ▼                       ▼
┌──────────────── L7 分发 publish ──────────────────────────┐
│ 全自动: Telegram / X / Threads / Instagram / Bluesky /    │
│   Mastodon / Buttondown邮件 / dashboard+RSS (LinkedIn可选)│
│ 一键队列: 小红书卡片图+文案 / 公众号草稿箱 → 推送管理群    │
└──────────────────── L8 运维 ──────────────────────────────┘
  源健康巡检 / 成本表+熔断 / 重试队列 / 降级模式 / 每日自检报告
```

**swarm 并发规范**：`asyncio` + `Semaphore(CONCURRENCY)`（默认 40，按主选供应商的并发上限配置）；单调用超时 60s；失败指数退避重试 3 次（2s/4s/8s）；重试耗尽 → 按 `models.yaml` 故障转移到同档位备选供应商；所有调用记入 `costs` 表（含供应商/模型维度）。system prompt 全部放常量文件保证前缀缓存命中（Kimi 为自动前缀缓存；其他供应商按各自缓存机制适配）。

---

## 4. 仓库结构

```
ai-radar/
├── radar/
│   ├── config.py            # 读 .env + config.yaml + models.yaml
│   ├── db.py                # SQLite 连接、migration、FTS5
│   ├── llm.py               # 多供应商路由: OpenAI兼容客户端/档位映射/
│   │                        #   故障转移/并发/重试/成本记账/熔断
│   ├── prompts.py           # 全部 system prompt 常量（字节级稳定）
│   ├── ingest/
│   │   ├── api_sources.py   # HN/HF/GitHub/arXiv 适配器
│   │   ├── rss_sources.py   # feedparser 通用适配器
│   │   └── htmldiff.py      # 页面快照+diff+LLM解析
│   ├── pipeline/
│   │   ├── score.py         # L2 打分 swarm
│   │   ├── cluster.py       # L3 聚类
│   │   ├── brief.py         # L4 日报编译 + flash 判定
│   │   ├── render.py        # L5 平台变体 + 卡片图渲染(Playwright)
│   │   └── qa.py            # L6 质检门
│   ├── publish/
│   │   ├── telegram.py      # 频道推送 + 管理群一键队列
│   │   ├── x_api.py         # thread 发布(纯文字+尾帖链接)
│   │   ├── threads_meta.py  # Meta Threads: 文字+轮播(复用卡片图)
│   │   ├── instagram.py     # IG 轮播(卡片转JPEG, ≤10张)
│   │   ├── bluesky_masto.py # Bluesky(blob直传) + Mastodon, 英文版
│   │   ├── linkedin.py      # 可选, config 开关默认关
│   │   ├── buttondown.py    # 邮件
│   │   ├── wechat_draft.py  # 公众号草稿箱 API
│   │   └── site.py          # dashboard JSON + RSS 输出 + 卡片图公网托管
│   ├── ops/
│   │   ├── health.py        # 源健康巡检/自动禁用
│   │   ├── budget.py        # 成本熔断
│   │   └── report.py        # 每日自检报告
│   └── scheduler.py         # APScheduler 全部任务编排
├── web/                     # dashboard 静态站(原生HTML/JS + FastAPI只读API)
├── templates/cards/         # 小红书卡片 HTML 模板 ×5 套轮换
├── config.yaml              # 阈值/预算/渠道开关
├── models.yaml              # 档位→模型映射: 主选/备选/base_url/现价(M0核实)
├── sources.yaml             # 源注册表(§6)
├── tests/                   # 各里程碑验收测试 + 压测回放
│   ├── fixtures/bignews_day/  # 合成大新闻日数据集
│   └── test_stress_replay.py
├── scripts/                 # init_db / backfill / run_once / stress_replay
├── .env.example
├── Dockerfile / docker-compose.yml / Caddyfile
└── Makefile                 # init/dev/test/deploy/backfill
```

## 5. 数据模型（SQLite DDL）

```sql
CREATE TABLE sources (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL
    CHECK(kind IN ('api','rss','html_diff')),
  url TEXT NOT NULL, tier TEXT NOT NULL DEFAULT 'B',   -- A官方一手 B权威/聚合 C社区
  weight REAL NOT NULL DEFAULT 1.0, enabled INTEGER NOT NULL DEFAULT 1,
  fail_count INTEGER NOT NULL DEFAULT 0, last_ok_at TEXT, last_error TEXT);

CREATE TABLE raw_items (
  id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL REFERENCES sources(id),
  external_id TEXT, url TEXT, title TEXT, content TEXT, author TEXT,
  published_at TEXT, fetched_at TEXT NOT NULL, content_hash TEXT NOT NULL,
  UNIQUE(source_id, content_hash));

CREATE TABLE items (
  id INTEGER PRIMARY KEY, raw_id INTEGER NOT NULL UNIQUE REFERENCES raw_items(id),
  relevance INTEGER NOT NULL, newsworthiness INTEGER NOT NULL,
  category TEXT NOT NULL, entities TEXT NOT NULL DEFAULT '[]',  -- JSON数组
  summary_one_line TEXT, scored_at TEXT NOT NULL, model TEXT NOT NULL);

CREATE TABLE clusters (
  id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, title TEXT NOT NULL,
  category TEXT NOT NULL, heat REAL NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'open'
    CHECK(status IN ('open','flashed','briefed','archived')),
  rep_item_id INTEGER REFERENCES items(id));

CREATE TABLE cluster_items (
  cluster_id INTEGER NOT NULL REFERENCES clusters(id),
  item_id INTEGER NOT NULL REFERENCES items(id),
  PRIMARY KEY (cluster_id, item_id));

CREATE TABLE briefs (
  id INTEGER PRIMARY KEY, date TEXT NOT NULL,
  kind TEXT NOT NULL CHECK(kind IN ('daily','flash','weekly')),
  status TEXT NOT NULL DEFAULT 'draft', created_at TEXT NOT NULL);

CREATE TABLE brief_entries (
  id INTEGER PRIMARY KEY, brief_id INTEGER NOT NULL REFERENCES briefs(id),
  cluster_id INTEGER NOT NULL REFERENCES clusters(id), rank INTEGER NOT NULL,
  headline_zh TEXT NOT NULL, headline_en TEXT,
  summary_zh TEXT NOT NULL, why_matters_zh TEXT NOT NULL,
  source_urls TEXT NOT NULL,   -- JSON数组, ≥1
  quotes TEXT NOT NULL);       -- JSON数组: 支撑摘要的原文引文

CREATE TABLE renditions (
  id INTEGER PRIMARY KEY, brief_id INTEGER NOT NULL REFERENCES briefs(id),
  platform TEXT NOT NULL,      -- telegram|x|email|xhs|wechat|site
  body TEXT NOT NULL, media_dir TEXT,
  status TEXT NOT NULL DEFAULT 'draft'
    CHECK(status IN ('draft','qa_passed','queued','published','failed','skipped')),
  published_at TEXT, external_url TEXT, error TEXT);

CREATE TABLE costs (
  date TEXT NOT NULL, model TEXT NOT NULL, calls INTEGER NOT NULL,
  in_tokens INTEGER NOT NULL, cached_tokens INTEGER NOT NULL,
  out_tokens INTEGER NOT NULL, usd REAL NOT NULL,
  PRIMARY KEY (date, model));

CREATE TABLE source_health (
  source_id INTEGER NOT NULL, date TEXT NOT NULL,
  ok_runs INTEGER, fail_runs INTEGER, items INTEGER, avg_latency_ms INTEGER,
  PRIMARY KEY (source_id, date));

CREATE VIRTUAL TABLE items_fts USING fts5(title, summary_one_line, entities);
```

## 6. 源注册表 sources.yaml（初始清单）

```yaml
# tier: A=官方一手(weight 3.0) B=权威媒体/聚合(2.0) C=社区(1.0)
api:
  - {name: hn-ai, kind: api, adapter: hn_algolia, tier: C, weight: 1.5,
     params: {query: "AI OR LLM OR GPT OR Claude OR Gemini OR Kimi OR agent",
              min_points: 20, window_min: 40}}
  - {name: hf-trending-models, adapter: hf_models, tier: B,
     params: {sort: trendingScore, limit: 100}}
  - {name: hf-daily-papers, adapter: hf_papers, tier: B}   # 替代生扫arXiv
  - {name: github-new-ai-repos, adapter: gh_search, tier: C,
     params: {topics: [llm, ai-agent, rag, mcp], min_stars: 50, created_days: 7}}
  - {name: github-trending, adapter: gh_trending_scrape, tier: C,
     params: {langs: [python, typescript, rust], alert_on_parse_fail: true}}
  - {name: arxiv-rss, adapter: rss, tier: C, weight: 0.8,
     url: "https://rss.arxiv.org/rss/cs.AI"}   # cs.CL cs.LG 同法各一条
rss:  # A 级官方
  - {name: openai-news,    url: "https://openai.com/news/rss.xml", tier: A}
  - {name: deepmind-blog,  url: "https://deepmind.google/blog/feed/basic/", tier: A}
  - {name: hf-blog,        url: "https://huggingface.co/blog/feed.xml", tier: A}
  # A 级官方但无官方feed → Olshansk 生成 + html_diff 兜底
  - {name: anthropic-news, url: "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_anthropic_news.xml", tier: A, fallback: html_diff}
  - {name: mistral-news,   url: "<Olshansk feed_mistral>", tier: A, fallback: html_diff}
  - {name: meta-ai-blog,   url: "<Olshansk feed_meta_ai>", tier: A, fallback: html_diff}
  - {name: xai-news,       url: "<Olshansk feed_xai>", tier: A, fallback: html_diff}
  # B 级聚合(二级验证源)
  - {name: tldr-ai,  url: "https://tldr.tech/api/rss/ai", tier: B}
  - {name: smol-ai,  url: "https://buttondown.com/ainews/rss", tier: B}
  # Kimi 应再补 ~40 条: 各大实验室工程博客/主流AI媒体/知名个人博客(如 simonwillison.net/atom/everything/)
html_diff:  # 差异化卖点: pricing/changelog 监控, 每6小时一轮
  - {name: openai-pricing,    url: "https://openai.com/api/pricing/", tier: A}
  - {name: anthropic-pricing, url: "https://www.anthropic.com/pricing", tier: A}
  - {name: kimi-pricing,      url: "https://platform.kimi.ai/docs/pricing", tier: A}
  # Kimi 应补齐 ~40 页: 主流模型厂商+主流AI SaaS 的 pricing/changelog/docs 页
  # 抓取前检查 robots.txt, Disallow 的页面跳过并记录
```

## 7. 流水线规格与 swarm prompt 模板

所有 prompt 存 `radar/prompts.py` 常量。**system prompt 不得包含任何动态内容**（日期、条目都放 user message），保证前缀缓存命中。所有 agent 输出用 JSON mode + schema 校验，解析失败重试 1 次。

### L2 打分（k2.5，每条一个调用）

```
SYSTEM (SCORER):
你是 AI 领域资讯打分器。对给定条目输出 JSON:
{"relevance": 0-100 与AI/LLM/agent领域的相关度,
 "newsworthiness": 0-100 新闻价值(官方发布/首次披露/重大变更高分; 教程/旧闻炒冷饭/营销软文低分),
 "category": "model_release|product|open_source|research|funding|policy|pricing|drama",
 "entities": ["公司/模型/产品名", ...最多6个, 用官方英文名],
 "summary_one_line": "一句中文陈述事实, ≤40字, 不加评价"}
只依据给定文本, 不引入外部知识判断真伪。

USER: 标题: {title}\n来源: {source_name}({tier})\n正文摘录: {content[:1500]}
```

丢弃线：`relevance < 55 or newsworthiness < 35`（config.yaml 可调）。预过滤：进入 LLM 前先用关键词/黑名单（招聘帖、纯营销）过滤掉 ~30%，零成本。

### L3 聚类（k2.5）

对每条新 item：FTS5 用 `title + entities` 召回近 72h 内 BM25 top5 个簇（取簇代表条目），召回为空直接开新簇；否则：

```
SYSTEM (CLUSTER_JUDGE):
判断"新条目"与各"候选簇"是否报道同一事件(同一次发布/同一笔融资/同一变更)。
同主题不同事件≠同一事件。输出 {"same_event_cluster_id": <id或null>}

USER: 新条目: {title} | {summary_one_line}\n候选簇:\n1. [id=..] {cluster_title}: {rep_summary}\n...
```

簇热度：`heat = Σ(source_weight) × ln(1+跨源数) × 时间衰减(半衰期24h)`。**簇内 LLM 判定上限 30 条**，超出的条目仅按 URL/标题精确匹配挂靠，不再调 LLM（大新闻日防爆算量）。

### Flash 快讯判定（代码规则，不是 LLM）

`heat ≥ FLASH_THRESHOLD` 且（`≥2 个不同 tier-A/B 源` 或 `1 个 tier-A 官方一手源`）且 当天已发 flash < 3 → 触发。生成后走同一 QA 门再发。

### L4 日报编译（07:10）

选簇：近 24h `status='open'` 按 heat 排序取 top 8-15。每簇一个 k2.6 agent：

```
SYSTEM (SUMMARIZER):
为中文技术读者写日报条目。输出 JSON:
{"headline_zh": "≤30字中文标题, 事实性, 不标题党",
 "headline_en": "原事件英文短标题",
 "summary_zh": "2-4句中文摘要, 覆盖: 谁/发布了什么/关键参数或数字",
 "why_matters_zh": "1-2句'为什么值得关注', 面向开发者视角",
 "quotes": ["支撑摘要中每个关键事实/数字的原文引文, 逐条摘录", ...]}
铁律: summary_zh 中出现的每个数字/专有名词必须能在 quotes 里找到出处;
原文没有的信息宁可不写; 不确定就删。

USER: 事件簇条目(含各源标题+摘录+URL): {...}
```

最后 `kimi-k3` 当一次"主编"：给全部条目排序、写日报导语（3 句）、去除条目间重复。

### L5 平台变体（k2.6，并行 fan-out）

| 平台 | 规格 |
|---|---|
| Telegram | 单条消息，HTML 格式，全部条目+链接，头部导语 |
| X thread | 开头帖(hook)+每事件1帖(≤270字符, **纯文字禁链接**)+收尾帖(1个dashboard链接+订阅引导)。中文为主，专有名词保留英文 |
| Email | Buttondown markdown：完整日报+链接 |
| 小红书 | 封面卡(当日最大新闻做钩子, 标题≤20字)+内页卡≤8张(每张1-2个事件)+文案(≤1000字含话题标签#AI日报 等5-8个)。卡片=HTML模板(templates/cards/ 5套轮换)经 Playwright 截图为 1080×1440 PNG。**文案末尾自动附「内容由AI辅助生成」** |
| Threads | 主帖(当日头条钩子+封面卡1张)+轮播帖(复用小红书内页卡2-10张)或纯文字事件流；中文；图片经 dashboard 静态目录出公网 URL |
| Instagram | 轮播 ≤10 张：封面卡+内页卡（复用小红书卡片，**转 JPEG**）；caption ≤2200 字符含 5-10 个 hashtag；公网 URL 同上 |
| Bluesky/Mastodon | **英文版**（触达海外受众）：头条 thread（headline_en+一句话+链接），Bluesky ≤300 字符/帖、Mastodon ≤500 |
| LinkedIn(可选) | 单帖：当日 Top3 职业向摘要+dashboard 链接 |
| 公众号 | 内联样式 HTML（微信编辑器兼容：无外部CSS/JS，图片转 base64 或先传素材库） |
| Dashboard | brief_entries 直接出 JSON + 站点 RSS |

### L6 QA 门（k3，独立 agent，逐平台 rendition 检查）

```
SYSTEM (QA_GATE):
你是事实核查员, 立场是怀疑一切。对给定成稿逐条检查:
1. 每个事实性论断/数字能否在所附 quotes/源文摘录中找到依据 → 找不到即 FAIL
2. 标题是否夸大(源文没有"最强/碾压/革命"级措辞而成稿有 → FAIL)
3. 平台硬规格: 小红书标题≤20字/正文≤1000字; X单帖≤270字符; 公众号无外链脚本
4. 敏感内容: 涉政治敏感/医疗建议/投资建议措辞 → FAIL
输出 {"pass": bool, "failures": [{"entry": n, "reason": "...", "fix_hint": "..."}]}

USER: 成稿: {rendition}\n各条目源引文: {quotes...}
```

FAIL → 带 fix_hint 重写 1 次 → 仍 FAIL → 该条目从该平台稿中移除并记日志（整份日报不因单条卡死）。**QA 通过前任何稿件不得进入发布队列**（DB 状态机强制：只有 `qa_passed` 能变 `queued`）。

## 8. 发布适配器细则

**Telegram（全自动）**：`sendMessage` 到公开频道；flash 即时发；失败重试 3 次后进死信并通知管理群。

**X（全自动）**：官方 API v2 按量计费。开发者侧一次性人工设置：启用 pay-per-use、开 Automated label、bio 关联人工账号。发布器强制校验：thread 正文帖不含 URL（含则 QA 已拦，双保险），仅尾帖 1 链接；每日发帖上限 15 条（config），超出丢队列次日。**日成本核算入 costs 表**（$0.015×文字帖 + $0.20×链接帖）。

**Buttondown（全自动）**：`POST /v1/emails`。M4 验收时先实测免费档 API 是否可发（§2 有出入警告），不可用则降级方案 = 生成 .eml 内容推管理群人工转发，并在报告中说明。

**Threads（全自动）**：一次性人工设置：Meta 开发者后台建 app → 启用 Threads use case → 用自己账号授权拿长效 token（只发自己账号无需完整 App Review）。发布：两步容器流程（`POST /{id}/threads` 建容器 → `threads_publish`），轮播用 `is_carousel_item`；图片 URL 指向 dashboard 静态目录（`site.py` 负责先落地公网可访问的 HTTPS 地址）。每次发布前查 `threads_publishing_limit` 防超限（250/天，正常远用不满）。

**Instagram（全自动，一次性设置最多）**：账号转 Professional（Creator）→ Instagram Login 路线建 app → 自己账号加为测试者。两步容器 → `media_publish`；轮播 ≤10 项、**仅 JPEG**（`render.py` 对 IG 输出 JPEG 版卡片）；发布前查 `content_publishing_limit`（100/天）。账号设置未完成时适配器置 `skipped` 并在自检报告持续提醒，不阻塞其他渠道。

**Bluesky / Mastodon（全自动）**：Bluesky 用 atproto `createRecord`（图片 blob 直传，无需公网 URL）；Mastodon 用 `/api/v1/statuses`（实例默认 300 帖/3 小时）。发英文版内容，账号注册和 token 获取零门槛。

**LinkedIn（可选，默认关闭）**：`w_member_social` + `/rest/posts` 发个人帖。前置：建一个 LinkedIn 公司主页给 app 做验证。config `channels.linkedin.enabled: false` 起步，账号就绪后打开。

**小红书（一键队列，不可全自动）**：08:05 机器人向管理群发：卡片图相册 + 可复制文案 + 标签。人打开小红书 App → 相册选图 → 粘贴 → 发布。**发布时间由人自然抖动，内容为原创摘要（非搬运），单账号运营，模板每日轮换**——这些是降低风控概率的合规手段，而非对抗手段。冷启动：前 2 周由人手动编辑标题/首图再发（既养号又收集人工修改数据用于改 prompt）。

**公众号（半自动）**：`draft/add` 推入草稿箱（个人订阅号可用），机器人在管理群发"草稿已就位"+预览摘要，人在公众号助手 App 点群发。若 draft API 也被回收（政策风险），降级 = 生成排版 HTML 文件推管理群，人用 doocs/md 编辑器粘贴，蓝图不因此阻塞。

**Dashboard（全自动）**：FastAPI 只读 API + 静态前端（原生 JS，无构建链）；页面：今日日报 / 历史归档 / 按类别与实体筛选 / 全文检索（FTS5）/ RSS 输出 / 订阅按钮位。部署：Docker + Caddy 自动 HTTPS，绑定子域名。

## 9. 调度表（Asia/Shanghai）

| 任务 | 节奏 |
|---|---|
| api/rss 采集 → 打分 → 聚类 | 每 30 分钟（整链，带互斥锁防重入） |
| html_diff 采集 | 每 6 小时 |
| flash 判定 | 每次聚类后 |
| 日报编译 → 平台变体 → QA | 07:10 |
| 全自动渠道发布 | 08:00 |
| 一键队列推送管理群 | 08:05 |
| 每日自检+成本报告 → 管理群 | 22:00 |
| 源健康周报 + 周报编译 | 周日 20:00 |
| DB 备份（本地+对象存储） | 每天 03:00 |

## 10. 运维与自愈

- **源健康**：连续 fail_count ≥ 5 → 自动 `enabled=0` + 管理群告警；每日自检报告列出 24h 零产出的源。`gh_trending_scrape` 解析出 0 条视为解析失败（页面改版信号），告警而非静默。
- **重试与死信**：所有外呼（采集/LLM/发布）统一重试 3 次指数退避；仍失败进 `dead_letter` 表，自检报告汇总。
- **降级模式（三级）**：① 主选供应商连续失败 → 自动故障转移到同档位备选供应商（models.yaml），管理群通知；② 全部供应商不可用 >30 分钟 → 进入 degraded：日报改为"纯链接榜单"（按 heat 排序的标题+链接，模板生成零 LLM），照常发布并注明"简版"；③ 恢复后自动回主选。**宁可发简版，不可断更。**
- **每日自检报告**（发管理群）：昨日 items/簇/发布状态、各渠道成败、成本合计与预算余量、源健康 Top 问题、QA 拦截数。

## 11. 合规红线（不可协商）

1. **不做反检测浏览器自动化**：不伪造指纹、不绕过 navigator.webdriver 检测、不模拟人工轨迹去骗小红书/知乎/即刻的风控。这些平台就是半自动/不做。
2. **版权**：只发转述摘要+原文链接，不整段翻译转载正文；引文（quotes）仅内部核查用，不对外发布超过合理引用长度的原文。
3. **AI 标注**：小红书文案自动附"内容由 AI 辅助生成"；X 启用 Automated label；公众号文末注明。
4. **爬虫礼仪**：html_diff 前查 robots.txt，Disallow 跳过；arXiv 1 req/3s；HF 带 token；总并发对单域名 ≤2。
5. **不碰**明确限非商业的 API（Reddit 免费档、Product Hunt 个人 token）。
6. **内容安全**：政治敏感/医疗/投资建议类内容 QA 门直接拦截；本产品只做技术情报。
7. **LLM 后端合规**：运行期只用各供应商的正式开放平台 API；不得把 Kimi 订阅侧 coding endpoint（`api.kimi.com/coding/v1`）或任何消费端订阅通道接入 `llm.py`（见 §0.1）。

## 12. 里程碑与验收测试

| | 交付 | 验收（Kimi 自测，全部通过才可进入下一里程碑） |
|---|---|---|
| **M0** | 骨架：repo/DB/调度器/llm.py 多供应商路由（含成本记账+熔断）/config；**核实各候选供应商当日现价写入 models.yaml** | `make init && make test-m0`：migration 幂等；打 1 个测试 LLM 调用后 costs 表有记录（含供应商维度）；把日预算设为 $0.001 再调用 → 熔断异常正确抛出；mock 主选 503 → 自动切换到备选供应商并在日志留痕 |
| **M1** | 采集层全量源 + 健康监控 | 连续跑 48h：≥45 个源正常、raw_items ≥300 条、源失败率 <5%、无未捕获异常；人为改坏 1 个源 URL → 5 轮后自动禁用+告警 |
| **M2** | 打分+聚类 swarm | 人工标注 60 条金标准（Kimi 先出候选人工确认）：打分保留/丢弃判定一致率 ≥85%；对 fixtures 大新闻日回放：同事件合并率 ≥90%，top10 簇无跨事件误并 |
| **M3** | 日报编译+QA 门 | 连续 3 天生成日报：每条目 ≥1 源链接且 quotes 可在源文中逐字定位（脚本自动核验子串匹配）；故意注入 1 条带虚构数字的条目 → QA 门必须拦截 |
| **M4** | 全自动渠道（TG/X/Threads/IG/Bluesky/Mastodon/Email/站点） | dry-run 打印完整 payload 人工过目一次 → 实发：TG 频道收到；X 发出 1 个测试 thread（确认 Automated label 已启用、纯文字帖计费 $0.015）；Threads 发 1 条带图测试帖且 `threads_publishing_limit` 可查；IG 账号就绪则发 1 组轮播测试（未就绪记 skipped 不阻塞）；Bluesky/Mastodon 各发 1 条英文测试帖；Buttondown 实测发信（不可用则触发降级方案并记录）；dashboard 可访问、RSS 可订阅、卡片图公网 URL 可直接打开 |
| **M5** | 一键队列（小红书/公众号） | 卡片 PNG 尺寸 1080×1440、文字无溢出（截图+边界检测脚本）；标题 ≤20 字、正文 ≤1000 字断言；管理群 60s 内收到完整队列；公众号草稿箱出现当日草稿 |
| **M6** | 压测回放+运维硬化 | §13 全部场景通过；连续 7 天无人工干预稳定运行（一键队列除外）后方可宣布上线 |

## 13. 压测与推演场景（tests/ 中全部实现为可重复运行的回放测试）

| 场景 | 注入 | 必须的系统行为 |
|---|---|---|
| S1 大新闻日 | fixtures 合成 5× 日常量（2,000 raw items，其中 1 个事件被 200 条重复报道） | 全链路 <25 分钟跑完；巨簇 LLM 判定封顶 30 次；当日成本 <$6；flash 只发 1 条不刷屏 |
| S2 源腐烂 | 随机关停 20% 源 + 1 个 feed 返回垃圾 HTML | 日报照常产出；坏源 5 轮后自动禁用；自检报告准确列出 |
| S3 幻觉注入 | 在簇数据中注入含虚构数字/虚构融资额的条目 | QA 门拦截率 100%（quotes 子串核验兜底） |
| S4 LLM 断供 | 先 mock 主选供应商 503（备选正常）；再 mock 全部供应商 503 持续 40 分钟 | 阶段一：自动故障转移到备选，产出质量不降级，管理群收到切换通知；阶段二：30 分钟后切"纯链接简版"照常发布，恢复后自动回主选 |
| S5 成本失控 | 把打分丢弃线调坏（全量入 LLM）+ 5× 流量 | 日预算 $8 熔断触发，停 LLM、发简版、管理群告警 |
| S6 发布失败 | mock TG/X API 间歇 500 | 重试 3 次→死信→告警；其余渠道不受影响；无重复发布（幂等键：brief_id+platform） |
| S7 冷启动 | 空库跑 backfill 7 天 | 首份日报可发布水准；聚类不把 7 天旧闻误判为今日新闻（published_at 参与判定） |
| S8 重复风暴 | 同一 URL 被 8 个源转载 | 精确去重+聚类后日报中只出现 1 条目 |

## 14. 上线 checklist 与人类一次性准备清单

**人类需提供（.env）**：

| 项 | 说明 |
|---|---|
| `KIMI_API_KEY`（主选） | platform.kimi.ai 注册并充值：≥$10 到 Tier 1（50 并发）可跑，**建议累计 $100 到 Tier 2（200 并发）**；控制台确认实际 Tier |
| 备选供应商 key ≥1 个 | DeepSeek / DashScope(Qwen) / GLM / Gemini 任选，充最低额度即可（只做故障转移与低价档；models.yaml 里配置） |
| `X_API_*` | X 开发者账号开通 pay-per-use；账号设置里启用 Automated label 并关联人工主账号 |
| `TG_BOT_TOKEN` + 频道/管理群 ID | @BotFather 建 bot；建公开频道（对外）+私有管理群（一键队列/告警），bot 均设管理员 |
| Meta 开发者 app（Threads/IG） | developers.facebook.com 建 app：启用 **Threads use case**，自己账号授权拿长效 token（免完整审核）；IG：账号转 **Professional**，走 Instagram Login 路线并把自己账号加为测试者。产出 `THREADS_TOKEN`、`IG_TOKEN` |
| Bluesky / Mastodon 账号 | 注册 + app password / token，零门槛 |
| LinkedIn（可选） | 建一个公司主页给 app 做验证后开 `w_member_social`，不急可后补 |
| `BUTTONDOWN_API_KEY` | 免费档注册，M4 时实测 |
| `GITHUB_TOKEN` / `HF_TOKEN` | 免费个人 token（只读公开数据） |
| `WECHAT_APPID/SECRET` | 公众号后台开发者设置；服务器 IP 加白名单 |
| VPS | 2C4G，Ubuntu 22.04 + Docker；子域名 DNS 指向；Caddy 自动 HTTPS。（面向国内用户访问且无备案 → 部署海外节点） |
| 小红书账号 | 实名认证；**冷启动前 2 周人工先发 3-5 篇度过新手期** |

**上线流程**：M6 通过 → 软启动 1 周（只发私有 TG 频道，人每天抽查）→ 公开发布 → 前 2 周小红书由人工润色后发 → 全速运行。

## 15. 每日人工 SOP（≤5 分钟）

08:05 管理群收到队列 → ① 小红书：存图→App 发布（2 分钟）；② 公众号：助手 App 点群发（30 秒）；③ 扫一眼日报有无离谱内容（1 分钟，有问题回 `/retract <entry>` 指令，bot 删除对应条目并重发全自动渠道）。22:00 瞄一眼自检报告（30 秒）。

## 16. 成本预算与熔断

**推演口径**（日常日 ~500 raw items → ~350 进 LLM）：

| 项 | 量 | 估算 |
|---|---|---|
| L2 打分 (k2.5) | 350 次 × (~800 in 多为缓存 / 150 out) | ~$0.3/天 |
| L3 聚类 (k2.5) | ~150 次 × 1.5k tokens | ~$0.2/天 |
| L4+L5 写作 (k2.6) | ~40 次 × (3k in / 800 out) | ~$0.3/天 |
| L6 QA + 主编 (k3) | ~10 次 × (8k in / 1k out) | ~$0.4/天 |
| **LLM 合计** | | **~$1.2/天 ≈ $36/月**（大新闻日峰值 ~$6） |
| X 发帖 | ~10 文字帖 + 1-4 链接帖/天 | ~$10-15/月 |
| Threads / IG / Bluesky / Mastodon / TG | 官方 API 全部免费 | $0 |
| VPS + 域名 | | ~$8/月 |
| Buttondown | ≤100 订阅者 | $0 起 |
| **总计** | | **≈ $55-60/月 ≈ ¥400/月**（多供应商路由把 cheap 档换成更低价模型还能再降） |

**熔断阈值（config.yaml）**：LLM 日预算 soft $4（告警）/ hard $8（停 LLM 转简版）；X 日发帖上限 15 条；月总预算 $80 触顶全线转免费渠道（TG/站点）。

**盈亏平衡**：按付费订阅 ¥30-50/月计，8-13 个付费用户覆盖全部成本。

---

## 17. 给 Kimi 的收尾要求

M6 通过后，产出三份文档进 repo：`OPERATIONS.md`（运维手册：告警含义、常见故障处置、降级/恢复、备份还原）、`PROMPTS_CHANGELOG.md`（prompt 每次改动记录 + 金标准回归结果）、`LAUNCH_REPORT.md`（各里程碑验收结果、压测数据、实际成本 vs 预算）。之后每周日随周报向管理群提交一份系统周报（成本/质量/源健康/建议优化项），等待人类批复后才可执行任何 prompt 或阈值的变更。
