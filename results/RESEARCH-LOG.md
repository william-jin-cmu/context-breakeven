# SKILL.state 复刻实验研究总结

日期: 2026-09-08 · 代码/数据: `~/cetus/dsh-skill-state`

## 1. 背景与动机

SKILL.state (arXiv 2608.26263, Google, EMNLP 2026) 主张: 不保留对话历史, 每一步把上下文换成一个显式、可变、结构化的 state 块。每步的 prompt = 任务 spec + 当前 state + 最新一条 observation, 模型的原始推理不保留。论文在 InterCode CTF (Gemini-3-Flash) 上把 43.2% 提到 54.2%, 未开源。

我们想验证两件事:
1. 这种"state 取代历史"能否在不掉准确率的前提下真省 token / 省钱。
2. 加一个渐进式披露的 `search_history` 工具 (默认只有 schema, 需要时回搜历史), 模型是否真会用、是否有增量价值。

## 2. 方法与实现

以 dsh (DeepSeek 官方 harness, @deepseek-ai/dsh) 为载体, 写了一个 cordis 插件 `dsh-skill-state`:

- **状态模型** (`state.ts`): `SkillState {task, plan, facts, files, done, log, issues, next, step}`, 字段按变化速率 slow→fast 排序, 为缓存对齐。`applyPatch` 做宽松类型强制。
- **压缩** (`index.ts`): 在 `agent/pre-step` 用 model-free 的 surfaceOp replace, 把上一条 assistant 之前的所有历史节点替换成一个 checkpoint 消息; 原始 trace 不删, 仍留在 session log 里供检索。
- **工具**: `update_state` (set/note), 以及 `search_history` (query 正则 或 step=N, max_chars 上限)。
- **失忆修复**: 检测到连续步骤没调 `update_state` 就注入提醒; 记录 assistant 文本。

三个对比臂:
- **tbmin** = dsh sdk-minimal, append-only, 无压缩 (官方 "minimal mode", ≈ 官方设置)。
- **tbstate** = state + search_history + 缓存对齐序列化。
- **tbstate-nosearch** = 纯 SKILL.state (插件 config `search:false`)。

## 3. 实验设置

- **模型**: DeepSeek V4 Flash, 官方 API, max effort, temp 1.0。
- **Benchmark**: Terminal-Bench 2.1 (91 任务), 经 harbor 运行, k=1。
- **官方基线**: V4 Flash 在 TB2.1 上 82.7 (即用 dsh minimal 跑出)。
- **环境坑**: Apple Silicon 上跑 amd64 镜像靠模拟, 明显偏慢, 导致大量 900s agent 超时; github 下载 uv 不稳 → 容器内预装 uv 0.9.5 + CPython 3.13; 少数 arm64 镜像单独构建 bundle。这些坑三臂一视同仁。
- **预算**: 50 USD 上限, 实际花费约 22 USD。

## 4. 结果

### 全部 89 题 (每臂用自己成功的 trial)

| 臂 | 通过 | 超时(900s) | 步数 | 每步 prompt | 缓存命中 | 每步输出 | 花费 |
|---|---|---|---|---|---|---|---|
| tbmin (append-only) | 59 (66.3%) | 16 | 4992 | 52.1k | 98.8% | 650 | $4.95 |
| tbstate (state+search) | 54 (60.7%) | 24 | 5631 | 12.8k | 50.9% | 1115 | $7.23 |
| tbstate-nosearch (纯 state) | 57 (64.0%) | 23 | 5743 | 13.9k | 49.4% | 1081 | $7.94 |

### 三臂都正常跑完的 54 题 (剔除超时干扰, 最公平)

| 臂 | 通过 | 每步 prompt | 未缓存 token | 每步输出 | 花费 |
|---|---|---|---|---|---|
| tbmin | 43 (79.6%) | 37.5k | 1.40M | 596 | $1.72 |
| tbstate | 44 (81.5%) | 10.8k | 14.2M | 947 | $2.92 |
| tbstate-nosearch | 43 (79.6%) | 10.1k | 12.2M | 1019 | $2.61 |

54 题里仅 8 题三臂结果不一致, 且互有胜负, 无系统性倾向。

## 5. 核心结论

1. **准确率中性**。共同完成的题上 43/44/43, 差异在噪声内。论文在 InterCode CTF 上 +11 点的提升, 在 TB2.1 + dsh + V4 上没有复现。
2. **token 省了, 钱反而多了**。每步 prompt 降到约 0.28 倍, 但 baseline 有 98.8% 前缀缓存命中 (缓存价 0.014/M 几乎免费), 而 state 臂每步多写约 400 输出 token 的 state 更新, 且 state 内容每步变化使命中掉到约 50%, 未缓存 token 反涨约 10 倍。总账 +50%~+70%。
3. **更慢、更多超时**。state 臂每步模型时间约 7.9s vs 5.2s, 步数多 15%~20%, 900s 超时从 16 涨到 23~24。全量准确率的差距基本就是超时数的差距。
4. **search_history 无增量价值**。有 search 和无 search 准确率相同, 却更碎更贵。

## 6. 为什么 search_history 没用 (trace 分析)

对 tbstate 的 88 个 session 统计 420 次 search_history 调用:

- **四分之三是"回忆自己第 N 步做了什么"**: 315 次是 `step=N` 定点回溯, 仅 105 次是正则/语义检索; 378 次检索到的是原始工具输出, 只有 42 次检索到 state 快照。即模型主要在捞被删掉的原始输出——这正是 append-only 基线免费保留的东西。
- **搜索集中在后期**: early/mid/late = 95/143/182, 越接近末尾搜得越勤, 是"卡住了"的信号, 不是高效规划。
- **反复重搜**: 25 个任务共 96 次"同一查询只改 max_chars 再搜一遍" (schemelike 反复搜 step 128/162; crack-7z-hash、count-dataset-tokens 把 max_chars 从 6000 加到 40000)。捞到了内容但读不出所以然, 只能加大窗口再捞。
- **检索本身几乎不失败**: 420 次里约 373 次返回实质内容。所以"没用"不是检索质量问题。

**根本原因**: Terminal-Bench 是紧耦合调试任务, 下一步高度依赖上一条命令的完整原始输出和当时的推理。state 摘要丢了细节, 推理更是被永久删除。模型被迫频繁 search 去补, 但 search 能补回输出、补不回推理。渐进式披露的前提"schema 足够驱动决策、历史偶尔取回"在这类任务上不成立: 需要的不是 schema + 按需搜, 而是历史本身。而历史一旦廉价缓存, 保留它比删掉再搜回来又便宜又准。

## 7. 适用边界

SKILL.state / 上下文压缩类方法真正能赢的场景: **历史很长、但后续步骤只依赖少量结构化事实、且服务栈没有廉价前缀缓存**。Terminal-Bench + DeepSeek 缓存这两条都不满足。宣称的 token 节省很大程度是**计费模型的产物, 不是计算的节省**; 一旦有 prefix caching, 收益会反转。原论文恰好在"没有廉价缓存"的评测环境里测, 所以这个反转被隐藏了。

## 8. 后续方向: 让缓存适配可变 state (把负结果翻成正结果)

现在拿不到缓存, 是因为可变 state 块夹在 prompt 中间, 破坏了前缀。若设计一种**按内容寻址、位置无关的模块化 KV 缓存**, 让 state 的每个字段成为可复用 KV 模块 (慢变字段复用、快变字段重编码, 配 RoPE 重定基 + 跨模块注意力修正), 就能同时拿到短 prompt 和高命中。

关键洞察: SKILL.state 的结构化 schema 表面是缓存负担, 反而是缓存的礼物——它给了天然分块边界和变化速率分层。方法与系统在此互相成就 (co-design)。

- **相关工作**: PromptCache (位置无关模块 KV, 但针对静态模块) / CacheBlend (选择性跨块重算, 不支持 V4 混合稀疏注意力、近似有质量风险) / SGLang RadixAttention (仍是前缀, 解决不了中间 mutation)。新意 = 把模块化缓存用到一个亲手设计成缓存友好的、每步 mutate 的结构化 state 上。
- **成败关键实验**: 近似 KV 复用会不会掉准确率。必须证明模块缓存重建的 KV 与全量重算精度一致 (或差距在误差棒内)。
- **核心图**: accuracy vs 每题成本/延迟, 三点——append-only+前缀缓存 / state+前缀缓存(负结果) / state+schema 模块缓存(目标落到左下角)。
- **落地**: 先用开源标准注意力模型 (Qwen3-8B / Llama) 在本地 vLLM 上原型, V4 的 NSA 稀疏注意力放 future work; 系统侧扩一个 PromptCache 式模块 KV 表, 不自研推理引擎。评测这一半 (harness/任务集/trace 工具/基线数据) 已现成。

## 9. 发表判断

- 作为单纯"复刻 + 负结果", 太薄, 有硬伤 (k=1 无误差棒、单模型、amd64 模拟污染准确率、单 benchmark 未复现 82.7)。
- 重写 thesis 为"上下文压缩的收益取决于服务栈缓存经济学", 加缓存开关交叉实验 + 误差棒 + 一个开源模型, 可做扎实的 workshop 论文或高传播力技术报告。
- 若再做出第 8 节的 schema-aware 模块缓存并证明不掉点, 则升级为方法+系统协同设计的主会级贡献。

## 附: 复现

```
cd ~/cetus/dsh-skill-state
python3 scripts/compare.py \
  full-tbmin-r1+full-tbmin-fix1 \
  full-tbstate-r1+full-tbstate-fix1 \
  full-tbstate-nosearch-r1+full-tbstate-nosearch-fix1
```
数据在 `jobs/`, session 逐步 trace 用 `scripts/trace.py <session.jsonl>`。

## 10. Tier 0 实验结果 (append-only 布局, 2026-09-08)

改插件加了 `layout: 'append'`: 把 state 块重排成 [稳定 preamble → 固定 task → append-only history → 一小段可变 CURRENT STATE 尾巴], 全量渲染日志不前截断, 让 history 成为纯增长前缀。新 profile `tbstate-append` (search 关, 仅布局变化)。本地验证连续两步公共前缀从 494 字符 (inline, 分叉在 facts) 提到 698 (append, 分叉在新日志行之后)。

20 题试跑 (k=1, V4 Flash, -n 2, setup-timeout×4; 因宿主另一 bench 抢 CPU, 初期 setup 超时, 调低并发+提高 setup 超时后正常; 7 个 agent 900s 超时)。三臂同 20 题的每步经济性:

| 臂 | 缓存命中 | 未缓存/步 | 缓存/步 | 输出/步 | 每步成本(m$) |
|---|---|---|---|---|---|
| tbmin 裸 append-only | 98% | 490 | 30794 | 603 | 0.669 |
| inline state (朴素 SKILL.state) | 48% | 4314 | 4020 | 1094 | 0.967 |
| append state (Tier 0) | 58% | 3923 | 5423 | 916 | 0.882 |

**结论:**
1. Tier 0 布局有效但有限: 命中 48%→58% (+10 点), 每步成本比朴素 state 降约 9%。移动可变字段到末尾是免费的真实改进。
2. 仍完败于裸 append-only: Tier 0 每步 0.882m 比 tbmin 0.669m 贵约 32%。布局只缩小差距, 远未追平。
3. 机制量化 (即王润基群里的预言): 裸 append-only 每步有 30794 token 命中缓存 (整段逐字历史是稳定前缀), 压缩后只有约 5400。压缩把可缓存前缀砍掉约 6 倍, 廉价缓存 API 上这部分丢失的缓存比省下的 token 更贵。
4. 定论: 廉价缓存 API 上, 解收敛到 append-only; 任何为压 token 数做的客户端压缩都是负优化, 因为它摧毁了让 baseline 近乎免费的缓存。Tier 0 是压缩思路的最优版本, 依然输。
5. 压缩不亏的 regime 只剩两个: 超长 horizon 下裸历史塞不进窗口; 无前缀缓存或按 token 计费的服务。TB2.1 + DeepSeek 都不满足。

## 11. Tier 1 实验结果 (position-independent KV, MiniPIC fork, 2026-09-08)

在 RunPod RTX A6000 上起 IBM vLLM span-semantics fork (commit 6631ff3, 纯 Python+Triton, 用 VLLM_USE_PRECOMPILED 复用内核)。机制: block 以 PLUS token (id 10) 开头时其 block hash 不依赖父块 (内容寻址), 故未变的 span 无论位置都能命中; 末段用 CROSS token (id 31) 依赖全部前文。把 268 个真实 Tier-0 state prompt 重放, 三臂比缓存命中 (/metrics token 计数), 并做精度门 (span-reuse 的 block attention vs 全注意力的贪心续写一致率)。

**成本 (缓存命中):**
| 模型 | append_text | span_text | span_reuse(block attn) |
|---|---|---|---|
| Qwen3-8B | 77% | 74% | 74% |
| Tulu3-Block-FT (为 block attention 微调) | 94% | 73% | 73% |

span_reuse 绝对复用的 KV 略多 (559k vs 537k), 但每 span 的 block 对齐 padding (+30k prompt) 把百分比优势吃掉。append-only 大幅领先。

**精度门 (span-reuse vs 全注意力一致率):**
- Qwen3-8B (未微调): 7.7% —— block attention 直接摧毁输出。
- Tulu3-Block-FT (已微调): 35% (exact 1/30) —— 即便是为 block attention 微调的模型, 在我们"很多小 span"的结构化 state 上仍严重退化 (它是为少量 RAG 文档微调的, 不是 agent state)。

**Tier 1 结论: 负。** 三条叠加:
1. 无成本收益: append-only 94% 远高于 span/span-reuse 73%。位置无关复用帮不上, 因为 agent state 每步改动太多; append-only 把稳定可缓存前缀最大化才是赢家。
2. block attention 需要专门微调的模型 (vanilla Qwen3 → 7.7% 乱码)。
3. 即便微调模型, 在结构化 state 上也只有 35% 一致 (微调面向 RAG 文档, 非多小 span)。

与 Tier 0、王润基的判断完全一致: 在有前缀缓存的世界里, append-only 赢; 客户端布局 (Tier 0) 和协同设计的位置无关 KV (Tier 1) 都打不过它。这条路到此为止, 除非换成"历史塞不进窗口"或"无缓存/按 token 计费"的 regime。实验总花费: DeepSeek API ~$22 + RunPod GPU ~$1 (A6000 1.8h)。

## §12 Phase 0 — cost break-even law (2026-09-09)

Closed form for "when does structured state beat append-only". Per step each arm uses `u` uncached (miss), `h` cached (hit), `o` output tokens; prices `p_m,p_c,p_o`; cache discount `r=p_c/p_m`, output ratio `ρ=p_o/p_m`. State wins iff `C_s<C_b`, i.e.

    r > r* = [ (u_b - u_s) + ρ·(o_b - o_s) ] / (h_s - h_b)

Across-task per-step means (full 89-task run): append-only u=588 h=35990 o=687; pure-state u=4739 h=4548 o=1047; ρ=2 ⇒ **r* = 0.155**. DeepSeek charges r=0.014/0.14=**0.10 < 0.155 ⇒ append-only wins**. Because h_b≫h_s and u_s>u_b, o_s>o_b, r* stays strictly positive: the cheaper the cache, the more decisively append-only wins (opposite of the token-count intuition).

Full-run across-task mean ± 95% CI (n=88): append-only hit 97.3±0.5%, 0.779±0.096 m$/step, model-time 5.8±0.7s; inline state 49.8±1.8%, 1.038±0.129 m$, 8.7±1.9s; pure state 48.7±1.3%, 1.020±0.097 m$, 8.6±1.0s. Accuracy gap is a throughput confound: on the 54 tasks all arms completed, pass = 43/44/43 (neutral); the state arms' lower full-run pass is caused by +2.8s/step model time → more 900s timeouts (23-24 vs 16), not worse reasoning.

**Two-axis law.** Evaluate any context scheme on (1) *price* — under prefix caching the billed quantity is uncached re-encodes + output, not total tokens, so append-only is optimal whenever history is a growing prefix; (2) *space* — the window is finite and decode attention grows with length, so compression becomes necessary once history overflows the window. Compression is justified by the space axis alone. SKILL.state is a window-fit mechanism mis-sold as a cost optimization.

Artifacts: paper/main.tex (arXiv draft) + paper/figs/{fig1_fullrun,fig2_breakeven,fig3_tier1}.pdf; tier1/analysis.py (numbers + r*), tier1/figs.py (figures). Phase 1 seed-variance run (3 arms × 10 tasks × k=3) running in background for error bars.

## §13 Phase 2 — two new insights from existing data (2026-09-09)

**(1) The verdict is provider-dependent.** r*=0.155 is a price threshold, so the same trajectory wins or loses by price sheet alone. Holding our per-step token counts fixed and applying 2026 prices: DeepSeek (r=0.10) append 0.779 vs state 1.020 m$/step → append (1.31x); Anthropic (r=0.10) → append (1.37x); Gemini Flash (r=0.25) append 0.925 vs state 0.755 → **STATE wins (0.82x)**; OpenAI mini (r=0.50) append 3.200 vs state 1.680 → **STATE wins (0.53x, ~2x cheaper)**. So "compaction saves money" is true on weak-cache providers (Gemini/OpenAI) and false on aggressive-cache ones (DeepSeek/Anthropic); the 6.5:1 cache discount is the dividing line. (tier1/provider_map.py, fig5_providers.pdf)

**(2) A task-length crossover even on cheap cache.** Per-step cost vs step index (paired per task, full run): append grows 0.018 m$/step (cached prefix lengthens), state grows 0.012 m$/step (bounded block) but starts higher (intercept 0.27 vs 0.71). They cross at **t*≈68 steps** — beyond that horizon append is more expensive per-step even at r=0.10, because a 10x discount on an ever-growing prefix still accumulates. TB2.1 task lengths: median 52, p75 86, p90 109, **32.6% exceed 68 steps**. Cumulatively append still wins at observed lengths (0.77x at step 60) — early steps much cheaper, need sustained deficit to flip running total. This locates where the "space axis" starts to bite: before the window limit, at the point accumulated cheap reads overtake a compact rewrite. (tier1/step_breakeven.py + tasklen.py, fig4_length.pdf)

**Refined two-axis law:** compression is justified if ANY of: weak cache (r>r*), long horizon (t>t*), or window overflow. All three fail (aggressive cache + moderate horizon + fits window) → append strictly dominates = the regime today's benchmarks inhabit, why the token-savings intuition went unchallenged. Paper (paper/main.tex → main.pdf, 9pp) updated with §5.1 providers + §5.2 length + revised abstract/law/conclusion; figs 4,5 added. No GPU re-rented.

## §14 Real Sept-2026 prices + V4.1/降价 (2026-09-09, corrects §13)

§13's "state wins on OpenAI/Gemini (r=0.25/0.5)" was based on stale/assumed prices — RETRACTED. Real Sept-2026 survey (benchlm.ai, morphllm, cloudzero): the market converged to cache-hit = 0.1x base input (r=0.10) for OpenAI (GPT-5.6, cached 0.1x), Gemini (3.8 Flash 0.75/0.075/3.75), Anthropic (Sonnet 5 3/0.30/15). DeepSeek cut its V4-Flash cache hit to 0.0028 (0.14/0.0028/0.28 → r=0.02); V4-Pro 0813 0.435/0.003625/0.87 → r=0.008. V4.1 is still beta/leaked, no public price → used post-cut V4-Flash as proxy.

r* is provider-specific via ρ=po/pm: DeepSeek ρ=2→r*=0.155; OpenAI/Gemini/Anthropic ρ=5→r*=0.189. ALL providers' r (0.008–0.10) < r* → **append-only wins on every current provider** (1.37x on r=0.10 providers, 2.6–3x on DeepSeek). Verdict table (append vs state m$/step, per-step means): V4-Flash 0.375/0.969; V4-Pro 0.984/2.989; GPT-5.6 30.49/41.72; Gemini 5.72/7.82; Sonnet 22.87/31.29.

**ctx-length balance point H*** (fixed trajectory, vary price): at r=0.10 → H*≈131k tokens (OpenAI 48% of 272k window, Gemini 13% of 1M, Anthropic 65% of 200k). **DeepSeek post-cut r=0.02 → NO crossover: append-only cheaper at every length** (append's per-step slope never overtakes state's once cache that cheap). So the price cut erased the length-axis case for compression — the r→0 limit (rjgg) now nearly realized in market. Earlier "V4 Flash H*≈87k" was at the OLD r=0.10; at current r=0.02 it's "never". Paper §5.1/§5.2 tables+figs 5/6 + abstract/law/conclusion updated; scripts tier1/ctx_balance_real.py + figs_real.py.

## §15 Phase 1 seed-variance DONE (2026-09-09)

3 arms × 10 tasks × k=3 = 90 trials (jobs/seed-{tbmin,tbstate-nosearch,tbstate-append}-k3). Pass signal = verifier_result.rewards.reward; cost = agent_result.cost_usd. Mean per-task pass ±95% CI: append 76.7±24.0%, pure-state 70.0±24.7%, Tier0 70.0±24.7% — **CIs overlap almost fully → accuracy-neutral confirmed with error bars**. Apparent gaps trace to 1-2 flaky tasks splitting across seeds (db-wal 1/3 vs 0/3, git-multibranch/cobol 3/3 vs 2/3); within-task seed variance > between-arm diff. $/task: append 0.105, state 0.139 (+32%), Tier0 0.151 (+44%) — cost ordering robust, matches full run. Lesson: pass-rate too noisy at n=10 to separate arms; cost is the reliable signal. Paper §4 seed paragraph + Limitations updated; main.pdf re-artifacted. tier1/seed_stats.py.

## §16 Phase 3 — generality: 2nd model family + 2nd benchmark (2026-09-09, running)

Author set: Qiu (William) Jin (no affiliation). Keys available: DeepSeek, Gemini, RunPod (no OpenAI/Anthropic). DeepSeek spend $25.39 of $50 cap before Phase 3; projected Phase 3 ≈ $13 (Gemini) + ~$3 (SWE on DeepSeek).

**(a) 2nd model: Gemini 3.5 Flash** (r=0.10: $1.50 / $0.15 cached / $9.00). Why not 3.8: raw API test, 4 identical 12k-token prefixes → `cachedContentTokenCount` never present on gemini-3.8-flash (launched 2026-09-02, implicit caching not live/reported yet); gemini-3.5-flash reports `cached=8170` on the 3rd call. Gemini 3/3.1 implicit-cache minimum = 4096 tokens. dsh wiring: sdk-minimal is a standalone composition (does NOT layer dsh-base) with only llm-deepseek → profile must `insert` `@deepseek-ai/dsh-llm-pi-ai` with `config.providers.google = {apiKeyEnv: GEMINI_API_KEY, models:[{id: gemini-3.5-flash, name, contextWindow, maxTokens, input:[text]}]}`; route key `google` reuses pi-ai's native Gemini provider (cachedContentTokenCount → cacheReadTokens); default-model `provider: google`. Verified end-to-end through dsh: steps 2–4 report cacheRead≈8.15k. Harness now forwards GEMINI_API_KEY. Run: 10-task TB2.1 seed subset × {tbmin-gemini, tbstate-nosearch-gemini} × k=1 (scripts/run_gemini.sh → jobs/gem-*-k1).

**(b) 2nd benchmark: SWE-bench Verified** (harbor hub; 348 tasks landed in data/swebench/swe-bench-verified). 22-task diverse subset (tier1/swe-subset.txt; per-repo cap so django doesn't dominate). swebench images are x86_64-only → on Apple Silicon need `DOCKER_DEFAULT_PLATFORM=linux/amd64` (harness auto-selects the amd64 dsh bundle inside the emulated container). Smoke psf__requests-1142: dsh installed, agent ran 59+ steps under emulation. Run: × {tbmin, tbstate-nosearch} × k=1, -n 2, setup-timeout ×4 (scripts/run_swe.sh → jobs/swe-*-k1), auto-launched after smoke.

Analysis: tier1/phase3_stats.py (pass ±CI, hit%, $/task at each provider's list price, state/append ratio; law predicts ratio >1 at r=0.10). Gotchas: macOS lacks `timeout`; zsh treats `$1:generateContent` as a `:g` modifier → use `${1}`.

### §16.1 Gemini 3.5 Flash interim findings (18/20 trials, 2026-09-09 ~20:30)

**Cache reliability is a third input to the law.** Gemini's implicit cache is best-effort: token-weighted realized hit on append-only = **89.7%** (DeepSeek deterministic prefix cache: 97–99%). Structure: prompts <20k tokens → 48.6% hit with **49% of steps zero-hit**; prompts >20k → 88–94%, ~0 zero-hit. Short tasks (kv-store-grpc, prove-plus-comm) get 0% cache → full price. Per-task unweighted mean hit (44%) is misleading; bill-weighted is 89.7%.

**Realized r_eff = 0.193 vs r* = 0.201 (ρ=6 for Gemini) → knife-edge**, and observation matches: state cheaper on only 2/8 paired tasks; excluding the single outlier, append is 2.83× cheaper ($1.20 vs $3.41); aggregate 0.79× (state cheaper) is entirely driven by db-wal-recovery (append $5.03 = 81% of append total).

**The outlier is a runaway trajectory**: append arm 281 steps → 900s AgentTimeoutError, max prompt 197k, 21.5M cumulative prompt tokens, both arms fail. With realized hit 89.7%, Gemini's length crossover is **H*≈66k** (vs 117k at 99% hit, 131k nominal) — 197k ≫ 66k, so state winning there is exactly what the law predicts. Append-only's cost on runaway loops grows ~quadratically; compression bounds it.

Interpretation for the paper: same nominal r=0.10, different realized economics. Deterministic prefix cache (DeepSeek) → append wins decisively; best-effort implicit cache (Gemini) → r_eff≈r*, verdict task-dependent, flipping on long/runaway tasks. State per-step cost on Gemini ≈ 19.7 m$ (ρ=6 makes state's extra output expensive). Pass rates noisy/overlapping (60±32 vs 62±36).

### §16.2 Gemini 3.5 Flash FINAL (20/20, 2026-09-09 ~21:00)
Paired 10 tasks: append pass 60±32%, token-weighted hit 89.4%, $7.32 total; state pass 50±33%, hit 9.8%, $6.59; aggregate ratio 0.90x (state cheaper) — but state cheaper on only 2/10 tasks; excluding db-wal-recovery runaway (append 281 steps→timeout, 197k prompt, $5.03=69% of arm) append is 2.22x cheaper ($2.29 vs $5.08). r_eff=0.195 vs r*=0.201 → knife-edge, as predicted. Realized-hit H*≈66k. Gemini spend $13.91 (list). Paper: new §Result 5 (sec:general) with fig7_gemini.pdf, contribution bullet 6, Limitations updated. SWE subsection placeholder pending.

### §16.3 SWE-bench Verified FINAL (44/44, 2026-09-09 22:59)
22 tasks × {append, pure state}, DeepSeek V4 Flash, k=1, no timeouts. Pass 21/22 both (same task fails: astropy-14365). Hit 97.4% vs 49.9% (token-weighted 98.2/50.4). $/task 0.042 vs 0.089 → **state 2.09x more expensive** ($0.93 vs $1.95 total); state cheaper on 5/22 (all tiny margins). r_eff=0.116 < r*=0.155 → append, as predicted (deterministic cache keeps r_eff≈nominal, unlike Gemini). Steps median 61 vs 68; model-time/step 2.2 vs 3.6s. Paper §sec:swe filled (tab:swe, fig8_swe.pdf), abstract + contribution 6 updated. **Total API spend $42.24 / $50 cap** (DeepSeek $28.33 + Gemini $13.91). ALL PHASES (0,1,2,3) COMPLETE. Paper ~13pp, 8 figures.
