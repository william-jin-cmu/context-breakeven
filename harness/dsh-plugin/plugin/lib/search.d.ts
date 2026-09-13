/**
 * Progressive disclosure over the durable session log. The model-visible
 * surface only carries the execution state plus the latest step, but every
 * earlier event is still in the log (replacements shadow, they do not delete),
 * so `search_history` can retrieve it on demand.
 */
import type { Session } from '@deepseek-ai/dsh-session';
interface Record_ {
    step: number;
    kind: 'call' | 'result' | 'assistant';
    text: string;
}
/** Flatten the session log into step-tagged text records (calls, results, assistant text). */
export declare function collectRecords(session: Session): Record_[];
export interface SearchOptions {
    query?: string;
    step?: number;
    maxChars: number;
}
export declare function searchHistory(session: Session, options: SearchOptions): string;
export {};
