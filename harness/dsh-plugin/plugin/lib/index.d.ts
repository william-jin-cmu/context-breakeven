/**
 * dsh-skill-state: a replication of SKILL.state (arXiv 2608.26263) inside dsh.
 *
 * Each step the model sees only: system prompt (skill spec) + one structured
 * execution-state message + the most recent step (its assistant message and
 * tool results). Everything older is shadowed on the session surface by a
 * model-free positional replacement (the same mechanism dsh's compaction and
 * tool-result pruner use), so the raw trace stays in the durable log and a
 * `search_history` tool can disclose it progressively.
 *
 * Two additions over the paper:
 *  - `log`: a runtime-maintained, append-only one-line index of every tool call,
 *    so the model has a cue that history exists and where to look.
 *  - cache-aligned serialization: state fields are rendered slow-changing first.
 * @module dsh-skill-state
 */
import type { Context } from '@deepseek-ai/cordis';
import z from '@deepseek-ai/schemastery';
export declare const name = "dsh-skill-state";
export declare const inject: string[];
export declare const Config: z<Schemastery.ObjectS<{
    maxLogLines: z<number, number>;
    argsChars: z<number, number>;
    resultChars: z<number, number>;
    searchMaxChars: z<number, number>;
    search: z<boolean, boolean>;
    assistantChars: z<number, number>;
    layout: z<"append" | "inline" | "span", "append" | "inline" | "span">;
    spanSep: z<string, string>;
}>, Schemastery.ObjectT<{
    maxLogLines: z<number, number>;
    argsChars: z<number, number>;
    resultChars: z<number, number>;
    searchMaxChars: z<number, number>;
    search: z<boolean, boolean>;
    assistantChars: z<number, number>;
    layout: z<"append" | "inline" | "span", "append" | "inline" | "span">;
    spanSep: z<string, string>;
}>>;
interface ResolvedConfig {
    search: boolean;
    maxLogLines: number;
    argsChars: number;
    resultChars: number;
    searchMaxChars: number;
    assistantChars: number;
    layout: 'inline' | 'append' | 'span';
    spanSep: string;
}
export declare function apply(ctx: Context, config: Partial<ResolvedConfig>): void;
export {};
