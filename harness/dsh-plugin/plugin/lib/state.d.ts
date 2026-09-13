/**
 * Execution-state schema for the SKILL.state replication.
 *
 * Field order is the serialization order and is deliberately slow-changing
 * first, fast-changing last, so a prefix cache keeps as much of the rendered
 * state as possible between steps (cache-aligned serialization):
 *   task (immutable) → plan → facts → files → done → log (append-only)
 *   → issues → next → step
 */
export interface SkillState {
    /** The original task instruction, verbatim. Immutable. */
    task: string;
    /** Numbered high-level plan. */
    plan: string[];
    /** Key facts discovered so far: paths, versions, errors, commands that work. */
    facts: Record<string, string>;
    /** Files created or modified. */
    files: string[];
    /** Completed plan steps / milestones. */
    done: string[];
    /** Runtime-owned, append-only one-line index of every tool call (step, tool, args, outcome). */
    log: string[];
    /** Open problems or blockers. */
    issues: string[];
    /** Current focus: what the very next action should be. */
    next: string;
    /** Loop step number of the request this state is rendered for. */
    step: number;
}
export declare const LIST_KEYS: readonly ["plan", "files", "done", "issues"];
export declare const EDITABLE_KEYS: readonly ["plan", "facts", "files", "done", "issues", "next"];
export declare function createState(task: string): SkillState;
/**
 * Apply a model-authored patch. Lists are replaced whole; `facts` is merged
 * with `null` deleting a key; `next` is replaced.
 * @returns an error message describing the first violation, or null when applied.
 */
export declare function applyPatch(state: SkillState, set: unknown): string | null;
/** Collapse whitespace and truncate to `max` characters. */
export declare function summarize(text: string, max: number): string;
/**
 * Append-only layout (Tier 0): everything that never changes byte-for-byte
 * between steps is emitted first, so a plain prefix cache keeps it hot:
 *   [stable preamble] → [immutable task] → [append-only history log]
 *   → [small mutable CURRENT STATE tail].
 * The volatile fields (plan/facts/files/done/issues/next/step) are the only
 * thing that changes position/content each step, and they sit at the very end,
 * so the divergence point between consecutive prompts moves from the middle
 * (right after `facts`) to just the newly appended log lines plus this small
 * tail. The full log is rendered (no front truncation) so history stays a pure
 * growing prefix; the tradeoff is unbounded growth instead of bounded context.
 */
export declare function renderStateAppendOnly(state: SkillState): string;
/**
 * Span layout (Tier 1): render the state block as an ordered list of
 * independently-cacheable spans joined by `sep` (a separator the serving stack
 * uses to reset its per-span hash chain — LMCache's LMCACHE_BLEND_SPECIAL_STR
 * or a MiniPIC SSep marker). Each stable unit is its own span so a
 * position-independent KV cache can reuse it by content regardless of where it
 * lands this step:
 *   [protocol] | [task] | [each fact, one span] | [plan] | [done] | [files]
 *   | [issues] | [history block] | [volatile: next+step]
 * The crucial property (unit-tested): an unchanged fact produces byte-identical
 * span text across steps even when other facts are added/removed/reordered, so
 * only genuinely new or edited facts miss. The fresh observation each step is a
 * separate dsh message (marked PDep at request assembly), not part of this block.
 */
export declare function renderStateSpans(state: SkillState, sep?: string): string;
/** Render the state block that replaces the conversation history. */
export declare function renderState(state: SkillState, maxLogLines: number, search?: boolean): string;
