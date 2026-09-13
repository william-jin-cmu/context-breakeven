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

export const LIST_KEYS = ['plan', 'files', 'done', 'issues'] as const;
export const EDITABLE_KEYS = ['plan', 'facts', 'files', 'done', 'issues', 'next'] as const;

export function createState(task: string): SkillState {
  return { task, plan: [], facts: {}, files: [], done: [], log: [], issues: [], next: '', step: 0 };
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'string');
}

/**
 * Apply a model-authored patch. Lists are replaced whole; `facts` is merged
 * with `null` deleting a key; `next` is replaced.
 * @returns an error message describing the first violation, or null when applied.
 */
export function applyPatch(state: SkillState, set: unknown): string | null {
  if (set === null || typeof set !== 'object' || Array.isArray(set)) {
    return 'set must be a JSON object';
  }
  const patch = set as Record<string, unknown>;
  const unknown = Object.keys(patch).filter((key) => !(EDITABLE_KEYS as readonly string[]).includes(key));
  if (unknown.length > 0) {
    return `unknown state field(s): ${unknown.join(', ')}. Editable fields: ${EDITABLE_KEYS.join(', ')}`;
  }
  // Lenient coercion: the model's intent matters more than exact JSON types.
  const toStringList = (value: unknown): string[] | null => {
    if (Array.isArray(value)) return value.map((item) => (typeof item === 'string' ? item : JSON.stringify(item)));
    if (typeof value === 'string') return value.trim() === '' ? [] : [value];
    if (value === null || value === undefined) return [];
    return null;
  };
  const lists: Partial<Record<(typeof LIST_KEYS)[number], string[]>> = {};
  for (const key of LIST_KEYS) {
    if (!(key in patch)) continue;
    const list = toStringList(patch[key]);
    if (list === null) return `${key} must be an array of strings`;
    lists[key] = list;
  }
  let next: string | undefined;
  if ('next' in patch) {
    const value = patch.next;
    next = typeof value === 'string' ? value : value === null || value === undefined ? '' : JSON.stringify(value);
  }
  let facts: Record<string, string | null> | undefined;
  if ('facts' in patch) {
    const value = patch.facts;
    if (value === null || typeof value !== 'object' || Array.isArray(value)) return 'facts must be an object: {key: string | null}';
    facts = {};
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      facts[k] = v === null || v === undefined ? null : typeof v === 'string' ? v : JSON.stringify(v);
    }
  }
  // Validated: apply.
  for (const key of LIST_KEYS) {
    const list = lists[key];
    if (list !== undefined) state[key] = list;
  }
  if (next !== undefined) state.next = next;
  if (facts !== undefined) {
    for (const [k, v] of Object.entries(facts)) {
      if (v === null) delete state.facts[k];
      else state.facts[k] = v;
    }
  }
  return null;
}

/** Collapse whitespace and truncate to `max` characters. */
export function summarize(text: string, max: number): string {
  const collapsed = text.replace(/\s+/g, ' ').trim();
  return collapsed.length <= max ? collapsed : `${collapsed.slice(0, max - 1)}…`;
}

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
export function renderStateAppendOnly(state: SkillState): string {
  const currentState = {
    plan: state.plan,
    facts: state.facts,
    files: state.files,
    done: state.done,
    issues: state.issues,
    next: state.next,
    step: state.step,
  };
  return [
    '<execution-state>',
    'This block is your complete memory of the task. Earlier messages, tool outputs and reasoning have been removed from the conversation; only the most recent step is kept below the block. This block is laid out append-only so it stays cache-friendly: the TASK and HISTORY never change, and you only ever edit the small CURRENT STATE section at the end via `update_state`. `history` is maintained automatically (one line per tool call, `sN` = step N) and is complete — there is no separate search tool, so record every conclusion you need into facts.',
    '',
    '# TASK (fixed)',
    state.task,
    '',
    '# HISTORY (append-only, one line per action; sN = step N)',
    ...(state.log.length === 0 ? ['(none yet)'] : state.log),
    '',
    '# CURRENT STATE (the only part you edit; keep it accurate)',
    JSON.stringify(currentState, null, 2),
    '</execution-state>',
  ].join('\n');
}

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
export function renderStateSpans(state: SkillState, sep = ' # # '): string {
  const spans: string[] = [];
  spans.push('<execution-state>\nStructured memory. Earlier messages and tool outputs are removed; only the latest step is kept after this block. Edit fields with `update_state`; `history` is maintained for you (sN = step N).');
  spans.push(`# TASK\n${state.task}`);
  // Facts: one span each, keyed and sorted so identical facts are byte-stable across steps.
  for (const key of Object.keys(state.facts).sort()) {
    spans.push(`# FACT ${key}\n${state.facts[key]}`);
  }
  spans.push(`# PLAN\n${state.plan.join('\n')}`);
  spans.push(`# DONE\n${state.done.join('\n')}`);
  spans.push(`# FILES\n${state.files.join('\n')}`);
  spans.push(`# ISSUES\n${state.issues.join('\n')}`);
  spans.push(`# HISTORY\n${state.log.length === 0 ? '(none yet)' : state.log.join('\n')}`);
  // Volatile tail: next action + step number change almost every step.
  spans.push(`# NEXT (step ${state.step})\n${state.next}\n</execution-state>`);
  return spans.join(sep);
}

/** Render the state block that replaces the conversation history. */
export function renderState(state: SkillState, maxLogLines: number, search = true): string {
  const omitted = Math.max(0, state.log.length - maxLogLines);
  const log = omitted > 0
    ? [`(${omitted} earlier log lines omitted${search ? '; use search_history to retrieve them' : ''})`, ...state.log.slice(omitted)]
    : state.log;
  const ordered = {
    task: state.task,
    plan: state.plan,
    facts: state.facts,
    files: state.files,
    done: state.done,
    log,
    issues: state.issues,
    next: state.next,
    step: state.step,
  };
  return [
    '<execution-state>',
    'This block is your complete memory of the task so far. Earlier messages, tool outputs and reasoning have been removed from the conversation; only the most recent step is kept below. `log` is maintained automatically (one line per tool call, `sN` = step N). Use `update_state` to keep plan/facts/files/done/issues/next accurate' + (search ? ', and `search_history` to read anything older in full.' : '. Older output cannot be read again.'),
    JSON.stringify(ordered, null, 2),
    '</execution-state>',
  ].join('\n');
}
