# Tier 1 计划: 让可变结构化 state 也命中缓存 (position-independent KV)

目标: 证明"结构化 state + 内容寻址/位置无关的 KV 缓存"能同时拿到短 prompt 和高命中,
从而在成本上追平甚至打赢裸 append-only。Tier 0 已证明纯客户端布局不够 (58% vs 98%),
瓶颈在每步重编码的可变 CURRENT STATE 尾巴 —— 这正是 Tier 1 要缓存的东西。

## 选型 (2026-09 调研结论)

- **缓存底座: MiniPIC** (arXiv 2606.13126, 基于 vLLM 0.15.01 的 IBM fork, ~78 LOC 核心改动)。
  存未旋转 K, 在注意力 kernel 里按每请求逻辑位置动态施加 RoPE, 位置无关。
  三个用户原语: Padding (对齐 KV block 边界)、SSep (span 分隔, 重置 hash 链→独立缓存)、
  PDep (强制依赖前文, 防假命中)。这套原语和 state schema 天然对齐。
  **关键: MiniPIC 论文明确没测精度 (自称 span 近似完整因果注意力会掉精度, 留作 future work) —— 这就是本工作的切口。**
- **对比基线: LMCache/CacheBlend** (separator-string 模式, 重算比例旋钮 0.15)。
  注意: 官方标 deprecated, 且 V1 connector 非前缀复用坏 (Issue #3238, 实测 2451 token 只命中 24)。仅作对照, 不做主力。
- **模型: 先 Llama-3-8B (MiniPIC 验证过, 降系统风险), 再换 Qwen3-8B 做 agentic eval。** 标准 RoPE, 单 24GB 卡能装。
- **宿主: Linux + NVIDIA (RTX 4090/A100)。** 本机 M1 Pro 跑不了。租用 ~$30-80。

## SkillState → span 映射设计

每步 prompt 切成有序 span, 标注复用策略:

| 段 | 内容 | 变化速率 | 复用策略 |
|---|---|---|---|
| S0 | 系统提示 / SKILL.state 协议 | 永不变 | 独立 span (SSep), 永久缓存 |
| S1 | task 原文 | 永不变 | 独立 span (SSep) |
| S2..Sk | facts 每条一个 span | 慢变, 会重排 | **每条独立 SSep span —— Tier 1 核心收益**: 没变的 fact 无论位置怎么移都命中 |
| Sk+1 | plan / done / files (稳定列表项) | 慢变 | 每项或整块 SSep span |
| Sh | append-only history 日志 | 只增 | 已是稳定前缀, 普通 prefix cache 即可; 可整块一个 span |
| Sobs | 最新一步的 assistant + tool 输出 | 每步全新 | PDep (依赖全部前文, 必然重算, 不可缓存) |

要点: Tier 0 里 S2..Sk 那段可变尾巴每步整体重编码 (miss ~3400/步); Tier 1 让没变的 fact span
按内容命中, 把 miss 压向"仅新增/改动的 fact + 新 observation", 理论上逼近裸 append-only 的 miss。

## 回本算术 (来自 Tier 0 实测每步毫美元)

| 臂 | 未缓存项 | 缓存项 | 输出项 | 合计 |
|---|---|---|---|---|
| tbmin 裸 append-only | 0.069 | 0.431 | 0.169 | 0.669 |
| Tier 0 append | 0.549 | 0.076 | 0.256 | 0.882 |
| **假想完美 Tier 1** | ~0.17 | 0.076 | 0.256 | **~0.50** |

裸 append-only 大头是 30794 token/步的缓存费 (0.431); Tier 1 只在 ~5400 token 上付缓存费。
若 Tier 1 把 miss 压到接近 tbmin 水平, 就可能反超。输出项 0.256 (每步多写 update_state) 是 Tier 1 治不了的税, 会吃掉部分赢面。

## 里程碑

1. **本地 (免费, 不依赖 GPU)**: 读 MiniPIC 代码; 实现 plugin `layout:'span'` 渲染器 (按上表切 span, 分隔符可配);
   写 dsh 指向远程 OpenAI 兼容端点的 provider 配置; 准备 eval 脚本。
2. **上机 bring-up**: 起 GPU; 编译 IBM vLLM fork + MiniPIC; serve Llama-3-8B; 验证普通 prefix cache 正常;
   把 span 渲染接进去, 验证"改一条 fact 只重算该 span"。
3. **精度关 (成败点)**: 同一批 prompt, 对比 MiniPIC span-reuse vs 全量重算的 logits/答案, 量掉多少精度。
4. **agentic eval**: TB2.1 pilot (10-20 题) × 臂 {裸 append-only, Tier0 append, Tier1 span-reuse}, 换 Qwen3-8B;
   测通过率 (精度中性?) + 每步 miss/cache/成本。出 accuracy vs cost/step 三点图。

## 风险

- **近似 KV 掉精度** (里程碑 3): 最大风险, MiniPIC 自己没测。掉太多就退回"划定边界"结论。
- **IBM vLLM fork 编译**: 特定 commit, 可能磨时间; 编译好后存持久卷。
- **输出税**: 每步 update_state 的输出 token Tier 1 治不了。
- **span 粒度**: fact 太碎 → span 太多, block 对齐/元数据开销上升; 需调 fact 合并粒度。
