import { toolPairingBalancedBefore } from '@deepseek-ai/dsh-compaction';
import { createUserMessage } from '@deepseek-ai/dsh-llm';
import { deriveEventMessage } from '@deepseek-ai/dsh-session';
import { defineTool } from '@deepseek-ai/dsh-tools';
import z from '@deepseek-ai/schemastery';
import { searchHistory } from './search.js';
import { applyPatch, createState, renderState, renderStateAppendOnly, renderStateSpans, summarize, EDITABLE_KEYS } from './state.js';
export const name = 'dsh-skill-state';
export const inject = ['tools', 'systemPrompt', 'tokenMeter'];
const PLUGIN_SOURCE = 'dsh-skill-state';
export const Config = z.object({
    maxLogLines: z.number().step(1).min(10).default(300).description('Log lines rendered in the state block; older lines are omitted (still searchable).'),
    argsChars: z.number().step(1).min(20).default(90).description('Characters of tool arguments kept per log line.'),
    resultChars: z.number().step(1).min(20).default(100).description('Characters of tool result kept per log line.'),
    searchMaxChars: z.number().step(1).min(500).default(6000).description('Default character budget of one search_history answer.'),
    search: z.boolean().default(true).description('Register the search_history tool (progressive disclosure). false = pure SKILL.state.'),
    assistantChars: z.number().step(1).min(0).default(240).description('Characters of the assistant\'s own text kept per step in the log (0 disables).'),
    layout: z.union([z.const('inline'), z.const('append'), z.const('span')]).default('inline').description('State serialization: "inline" (mutable fields before the log) or "append" (Tier 0: stable task+history prefix, small mutable tail last, for prefix-cache friendliness).'),
    spanSep: z.string().default(' # # ').description('Separator between cacheable spans in layout:span (LMCACHE_BLEND_SPECIAL_STR or MiniPIC SSep marker).'),
});
function promptText(search, layout = 'inline') {
    if (layout === 'append') {
        return `## Execution state protocol (SKILL.state, append-only layout)
Your conversation history is NOT kept. At every step the runtime gives you exactly: one <execution-state> block (your structured memory), plus the most recent step's actions and outputs. The block has three parts: TASK (fixed), HISTORY (an append-only one-line index of every action, maintained for you, sN = step N), and CURRENT STATE (the only part you edit). Anything you do not record in CURRENT STATE is gone from your context on the next step; HISTORY keeps only a one-line summary per action, not full outputs.
Rules:
1. Call update_state in EVERY step that produced new information, in the same assistant turn as your other tool calls (they run in parallel, so it costs no extra round trip). Record into CURRENT STATE: the plan, key facts (paths, versions, working commands, exact error messages, findings), files you changed, milestones done, open issues, and the next action.
2. Keep entries short and concrete. Prefer facts like "tests: run with \`make test\` (3 failing: t_parse, t_io, t_cli)" over prose.
3. HISTORY is only a summary: there is no way to read older full output again, so record every conclusion you will need into facts the first time you see it. Do not re-run a command just to look at output you already saw.
4. When the task is complete, verify it, update CURRENT STATE a final time, then answer.`;
    }
    const retrievable = search ? ' (it remains retrievable with search_history)' : '';
    const rule3 = search
        ? '3. The `log` field is maintained for you: one line per tool call, tagged sN = step N. If you need the full output of an earlier command, call search_history with step=N, or with a query to grep across all history.'
        : '3. The `log` field is maintained for you: one line per tool call, tagged sN = step N. It is only a summary: there is NO way to read older output again, so record every conclusion you will need in facts.';
    const rule4 = search
        ? '4. Do not re-run commands just to see output you already saw; retrieve it with search_history instead. Better: record the conclusion in facts the first time, so you never need to look again.'
        : '4. Record the conclusion in facts the first time you see an output, so you never need to re-run a command just to look at it again.';
    return `## Execution state protocol (SKILL.state)
Your conversation history is NOT kept. At every step the runtime removes all earlier messages and tool outputs and gives you exactly: one <execution-state> block (your structured memory), plus the most recent step's actions and outputs. Anything you do not record in the state is gone from your context on the next step${retrievable}.
Rules:
1. Call update_state in EVERY step that produced new information, in the same assistant turn as your other tool calls (tool calls run in parallel, so this costs no extra round trip). Record: the plan, key facts (paths, versions, working commands, exact error messages, findings), files you changed, milestones done, open issues, and the next action. If you skip it, the runtime will remind you and you will have to re-derive what you lost.
2. Keep entries short and concrete. Prefer facts like "tests: run with \`make test\` (3 failing: t_parse, t_io, t_cli)" over prose.
${rule3}
${rule4}
5. When the task is complete, verify it, update the state a final time, then answer.`;
}
const TEXT_OUTPUT = {
    schema: { type: 'string' },
    render: (_args, value) => [{ type: 'text', text: String(value) }],
};
function textOfContent(content) {
    if (content === undefined)
        return '';
    return content.map((block) => (block.type === 'text' ? block.text : '')).filter((t) => t !== '').join('\n');
}
function isCheckpoint(event) {
    if (event === undefined || event.type !== 'user/message')
        return false;
    const source = event.data.source;
    return source?.kind === 'plugin' && source.plugin === PLUGIN_SOURCE;
}
function argsSummary(toolName, args, max) {
    const record = args !== null && typeof args === 'object' ? args : undefined;
    if (record !== undefined) {
        if (toolName === 'bash' && typeof record.command === 'string')
            return summarize(record.command, max);
        if (typeof record.command === 'string' && typeof record.path === 'string')
            return summarize(`${record.command} ${record.path}`, max);
    }
    try {
        return summarize(JSON.stringify(args) ?? '', max);
    }
    catch {
        return '';
    }
}
function resultSummary(content, isError, max) {
    const text = summarize(textOfContent(content), max);
    return `${isError ? 'ERR ' : ''}${text === '' ? '(no output)' : text}`;
}
export function apply(ctx, config) {
    const resolved = {
        search: config.search ?? true,
        maxLogLines: config.maxLogLines ?? 300,
        argsChars: config.argsChars ?? 90,
        resultChars: config.resultChars ?? 100,
        searchMaxChars: config.searchMaxChars ?? 6000,
        assistantChars: config.assistantChars ?? 240,
        layout: config.layout ?? 'inline',
        spanSep: config.spanSep ?? ' # # ',
    };
    const store = new WeakMap();
    const sessionState = (session) => {
        let entry = store.get(session);
        if (entry === undefined) {
            entry = { state: undefined, currentStep: 0, replacements: 0, updatedThisStep: true, stepsWithoutUpdate: 0 };
            store.set(session, entry);
        }
        return entry;
    };
    const anyCtx = ctx;
    /**
     * Replace every surface node before the last assistant message with one
     * state checkpoint. Model-free; mirrors dsh-compaction-tool-result-pruner's
     * shadow-price + replace protocol.
     */
    const compactSurface = (session, entry) => {
        if (entry.state === undefined)
            return 0;
        const nodes = session.surface.nodes;
        let lastAssistant = -1;
        for (let index = nodes.length - 1; index >= 0; index -= 1) {
            if (session.eventAt(nodes[index])?.type === 'assistant/message') {
                lastAssistant = index;
                break;
            }
        }
        if (lastAssistant < 1)
            return 0;
        if (lastAssistant === 1 && isCheckpoint(session.eventAt(nodes[0])))
            return 0;
        if (!toolPairingBalancedBefore(session, nodes[lastAssistant])) {
            anyCtx.logger.warn('skill-state: retained tail is not tool-pairing balanced; skipping replacement this step');
            return 0;
        }
        const shadowed = nodes.slice(0, lastAssistant);
        let shadowedTokenCount = 0;
        for (const seq of shadowed) {
            const event = session.eventAt(seq);
            const message = event === undefined ? null : deriveEventMessage(event);
            if (message !== null)
                shadowedTokenCount += anyCtx.tokenMeter.estimateMessage(message);
        }
        const rendered = resolved.layout === 'span'
            ? renderStateSpans(entry.state, resolved.spanSep)
            : resolved.layout === 'append'
                ? renderStateAppendOnly(entry.state)
                : renderState(entry.state, resolved.maxLogLines, resolved.search);
        const checkpoint = createUserMessage({
            content: [{ type: 'text', text: rendered }],
            source: { kind: 'plugin', plugin: PLUGIN_SOURCE },
        });
        const start = shadowed[0];
        const end = shadowed[shadowed.length - 1];
        session.append('compaction/prune', {
            shadowedRange: { start, end },
            shadowedSeqs: [...shadowed],
            shadowedTokenCount,
        });
        session.append('user/message', checkpoint, {
            surfaceOp: { op: 'replace', start, end },
            sourceEventSeqs: [...shadowed],
        });
        entry.replacements += 1;
        return shadowed.length;
    };
    // 1. Every step: seed the state from the task, then collapse history into it.
    ctx.effect(() => anyCtx.on('agent/pre-step', async (payload, next) => {
        const session = payload.agent.session;
        const entry = sessionState(session);
        // Close the previous step's bookkeeping before this step's request is built.
        const previousStepUpdated = entry.updatedThisStep;
        if (entry.state !== undefined && payload.step > 1) {
            entry.stepsWithoutUpdate = previousStepUpdated ? 0 : entry.stepsWithoutUpdate + 1;
        }
        entry.updatedThisStep = false;
        entry.currentStep = payload.step;
        if (entry.state === undefined) {
            let task = textOfContent(payload.messages[0]?.content);
            if (task === '') {
                const first = session.surface.nodes.map((seq) => session.eventAt(seq)).find((event) => event?.type === 'user/message');
                task = first === undefined ? '' : textOfContent(first.data.content);
            }
            entry.state = createState(task);
        }
        entry.state.step = payload.step;
        try {
            const count = compactSurface(session, entry);
            if (count > 0)
                anyCtx.logger.info(`skill-state: step ${payload.step}: replaced ${count} surface nodes with the state checkpoint`);
        }
        catch (error) {
            anyCtx.logger.warn(`skill-state: replacement failed: ${error instanceof Error ? error.message : String(error)}; continuing with full history this step`);
        }
        const decision = (await next());
        if (decision.kind === 'enter' && entry.stepsWithoutUpdate >= 1 && payload.step > 2) {
            const reminder = createUserMessage({
                content: [{ type: 'text', text: `[state protocol] Your last ${entry.stepsWithoutUpdate} step(s) did not call update_state. Everything you learned in them is now only in the log line summaries above. Call update_state in THIS step (alongside your other tool calls) to record the facts, files, done items and next action; anything unrecorded will be dropped again.` }],
                source: { kind: 'plugin', plugin: PLUGIN_SOURCE, form: 'notice', summary: 'state protocol reminder' },
            });
            return { ...decision, messages: [...(decision.messages ?? []), reminder] };
        }
        return decision;
    }), 'skill-state.pre-step');
    // 2. Runtime-owned log: one line per tool call, so the model knows history exists.
    ctx.effect(() => anyCtx.on('tools/result', (exec, result) => {
        const session = exec.agent?.session;
        if (session === undefined)
            return;
        const entry = sessionState(session);
        if (entry.state === undefined)
            return;
        if (exec.name === 'update_state') {
            entry.updatedThisStep = true;
            return; // its own note is logged by the tool
        }
        const line = `s${entry.currentStep} ${exec.name}: ${argsSummary(exec.name, exec.arguments, resolved.argsChars)} → ${resultSummary(result.content, result.isError, resolved.resultChars)}`;
        entry.state.log.push(line);
    }), 'skill-state.log');
    // 2b. The model's own prose per step (its conclusions), truncated, so they survive replacement.
    ctx.effect(() => anyCtx.on('session/event', (session, event) => {
        if (event.type !== 'assistant/message')
            return;
        const entry = store.get(session);
        if (entry?.state === undefined)
            return;
        const data = event.data;
        const text = summarize(textOfContent(data.message?.content), resolved.assistantChars);
        if (text !== '')
            entry.state.log.push(`s${data.step ?? entry.currentStep} said: ${text}`);
    }), 'skill-state.assistant-log');
    // 3. Tools.
    ctx.effect(() => anyCtx.tools.register(defineTool({
        name: 'update_state',
        description: `Update your execution state (your only persistent memory across steps). Editable fields: ${EDITABLE_KEYS.join(', ')}. Lists (plan, files, done, issues) are replaced whole; facts is merged (set a key to null to delete it); next is a short string. Invalid patches are rejected with an explanation — fix and retry.`,
        parameters: {
            set: { type: 'object', additionalProperties: true, description: 'Partial state: {plan?: string[], facts?: {[key]: string|null}, files?: string[], done?: string[], issues?: string[], next?: string}' },
            note: { type: 'string', description: 'Optional free-text memo appended to the log (e.g. a hypothesis you ruled out).' },
        },
        output: TEXT_OUTPUT,
        isConcurrencySafe: () => true,
        execute: async (args, exec) => {
            const session = exec.agent?.session;
            if (session === undefined)
                throw new Error('update_state: no agent session');
            const entry = sessionState(session);
            if (entry.state === undefined)
                throw new Error('update_state: state not initialized yet');
            if (args.set !== undefined) {
                const error = applyPatch(entry.state, args.set);
                if (error !== null)
                    throw new Error(`update_state rejected: ${error}`);
            }
            if (typeof args.note === 'string' && args.note.trim() !== '') {
                entry.state.log.push(`s${entry.currentStep} note: ${summarize(args.note, 200)}`);
            }
            const { plan, facts, files, done, issues, next } = entry.state;
            return `ok (plan ${plan.length}, facts ${Object.keys(facts).length}, files ${files.length}, done ${done.length}, issues ${issues.length}; next: ${next === '' ? '(unset)' : summarize(next, 80)})`;
        },
    })), 'skill-state.tool.update_state');
    if (resolved.search)
        ctx.effect(() => anyCtx.tools.register(defineTool({
            name: 'search_history',
            description: 'Retrieve earlier history that is no longer in your context. Give step=N to get the full tool calls, outputs and your own message from step N (see the sN tags in the state log), or query=<regex> to grep across all past commands, outputs and messages (returns snippets with step numbers).',
            parameters: {
                query: { type: 'string', description: 'Case-insensitive regex to search for.' },
                step: { type: 'integer', description: 'Return every record of this step in full.' },
                max_chars: { type: 'integer', description: `Character budget of the answer (default ${resolved.searchMaxChars}).` },
            },
            output: TEXT_OUTPUT,
            isConcurrencySafe: () => true,
            execute: async (args, exec) => {
                const session = exec.agent?.session;
                if (session === undefined)
                    throw new Error('search_history: no agent session');
                return searchHistory(session, {
                    ...(args.query === undefined ? {} : { query: args.query }),
                    ...(args.step === undefined ? {} : { step: args.step }),
                    maxChars: Math.max(500, Math.min(args.max_chars ?? resolved.searchMaxChars, 60000)),
                });
            },
        })), 'skill-state.tool.search_history');
    // 4. Skill spec: the protocol lives in the system prompt (stable prefix).
    ctx.effect(() => anyCtx.systemPrompt.section({ name: 'skill-state', order: 120, text: promptText(resolved.search, resolved.layout) }), 'skill-state.prompt');
}
