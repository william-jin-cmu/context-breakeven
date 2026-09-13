# context-breakeven

**When Does Structured State Beat Append-Only History? A Cost Break-Even Law for Agent Context Management under Prefix Caching** — paper, data and analysis.

Under a production prefix cache the cost axis is *uncached re-encodes + output tokens*, not total tokens. Replacing an agent's history with a compact mutable state (SKILL.state-style) cuts prompt tokens ~4x yet costs 1.3–2.1x **more** per step and is accuracy-neutral, because rewriting the block every step collapses the cache hit rate (97% → 49%). We derive a closed-form break-even `r* = [(u_b−u_s) + ρ(o_b−o_s)] / (h_s−h_b)`: structured state wins only when the cache-hit/miss price ratio `r` exceeds `r*` (0.155–0.189 here). Every major provider prices `r ≤ 0.10` today, so append-only wins everywhere; a best-effort cache (Gemini) realizes only ~89% of nominal hits and lands on the knife-edge. Reproduced on SWE-bench Verified.

## Layout
- `paper/` — LaTeX source, figures, compiled PDF (`tectonic main.tex`).
- `analysis/` — scripts that produce every number and figure (`analysis.py` break-even + CIs, `step_breakeven.py` length crossover, `ctx_balance_real.py` H* at real prices, `seed_stats.py`, `phase3_stats.py`, `*_fig.py`).
- `results/` — `trials.csv` (one row per harbor trial: task, arm, reward, tokens, cost), the research log, and the Tier‑1 (MiniPIC) report.
- `harness/dsh-plugin/` — the experimental harness: a SKILL.state plugin for DeepSeek's dsh agent (`plugin/`), dsh profiles for every arm (`dsh-home/profiles/`), a harbor `BaseInstalledAgent` (`harbor-agent/`), and run scripts.

## Reproduce
Experiments run on Terminal-Bench 2.1 and SWE-bench Verified via [harbor](https://hub.harborframework.com), driving [dsh](https://github.com/deepseek-ai/dsh) (DeepSeek's agent harness) inside the task containers; dsh's plugin system is what made swapping context-management strategies a config change. Set `DEEPSEEK_API_KEY` (and `GEMINI_API_KEY` for the Gemini arms), then e.g. `harness/dsh-plugin/scripts/run_seed.sh`. Full per-trial outputs (~GBs of session logs) are not committed; `results/trials.csv` is the aggregated record the analysis scripts consume.

## Cite
Qiu (William) Jin. *When Does Structured State Beat Append-Only History? A Cost Break-Even Law for Agent Context Management under Prefix Caching.* arXiv, 2026.

MIT License.
