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

function textOfBlocks(blocks: unknown): string {
  if (!Array.isArray(blocks)) return '';
  const parts: string[] = [];
  for (const block of blocks as Array<Record<string, unknown>>) {
    if (block.type === 'text' && typeof block.text === 'string') parts.push(block.text);
    else if (block.type === 'tool-result') parts.push(textOfBlocks(block.content));
    else if (block.type === 'tool-call') parts.push(`[tool-call ${String(block.name)} ${typeof block.arguments === 'string' ? block.arguments : JSON.stringify(block.arguments)}]`);
  }
  return parts.join('\n');
}

/** Flatten the session log into step-tagged text records (calls, results, assistant text). */
export function collectRecords(session: Session): Record_[] {
  const records: Record_[] = [];
  for (const event of session.snapshotEvents()) {
    const data = event.data as Record<string, unknown>;
    if (event.type === 'tool/call') {
      const args = typeof data.arguments === 'string' ? data.arguments : JSON.stringify(data.arguments);
      records.push({ step: Number(data.step), kind: 'call', text: `${String(data.name)} ${args}` });
    } else if (event.type === 'tool/result') {
      const message = data.message as Record<string, unknown> | undefined;
      if (event.surfaceOp !== 'append') continue; // skip replacement copies (pruned/shadowed variants)
      records.push({ step: Number(data.step), kind: 'result', text: textOfBlocks(message?.content) });
    } else if (event.type === 'assistant/message') {
      const message = data.message as Record<string, unknown> | undefined;
      const text = textOfBlocks(message?.content);
      if (text.trim() !== '') records.push({ step: Number(data.step), kind: 'assistant', text });
    }
  }
  return records;
}

export interface SearchOptions {
  query?: string;
  step?: number;
  maxChars: number;
}

function clip(text: string, max: number): string {
  return text.length <= max ? text : `${text.slice(0, max)}\n…[truncated ${text.length - max} chars]`;
}

export function searchHistory(session: Session, options: SearchOptions): string {
  const records = collectRecords(session);
  if (options.step !== undefined) {
    const hits = records.filter((r) => r.step === options.step);
    if (hits.length === 0) return `No records for step ${options.step}.`;
    let budget = options.maxChars;
    const out: string[] = [`Step ${options.step} (${hits.length} records):`];
    for (const hit of hits) {
      if (budget <= 0) { out.push('…[budget exhausted]'); break; }
      const body = clip(hit.text, Math.min(budget, options.maxChars));
      budget -= body.length;
      out.push(`--- ${hit.kind} ---\n${body}`);
    }
    return out.join('\n');
  }
  const query = options.query?.trim() ?? '';
  if (query === '') return 'Provide a query or a step number.';
  let regex: RegExp;
  try {
    regex = new RegExp(query, 'i');
  } catch {
    regex = new RegExp(query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'i');
  }
  const matches: string[] = [];
  const window = 200;
  for (const record of records) {
    const match = regex.exec(record.text);
    if (match === null) continue;
    const start = Math.max(0, match.index - window);
    const end = Math.min(record.text.length, match.index + match[0].length + window);
    const snippet = record.text.slice(start, end).replace(/\s+/g, ' ');
    matches.push(`s${record.step} ${record.kind}: ${start > 0 ? '…' : ''}${snippet}${end < record.text.length ? '…' : ''}`);
    if (matches.length >= 12) break;
  }
  if (matches.length === 0) return `No history records match /${query}/i.`;
  const header = `${matches.length} match(es) for /${query}/i (use search_history with step=N for the full record):`;
  return clip([header, ...matches].join('\n'), options.maxChars);
}
