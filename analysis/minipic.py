"""Build a MiniPIC token-id prompt from a span-layout text.
Recipe (from IBM fork examples/offline_inference/spans/spans.py):
  pad(toks) keeps last token, pads the rest to a multiple of 16 with PAD.
  prefix span     -> pad(tok(span0))                 (base, no marker)
  reusable spans  -> pad([PLUS] + tok(span_i))       (independently cacheable)
  final span      -> [CROSS] + tok(span_last)        (depends on all preceding)
Special token ids are single-char tokens, set via env on the server too.
"""
BLOCK = 16
def pad(toks, padtok):
    return toks[:-1] + [padtok] * ((BLOCK - len(toks)) % BLOCK) + toks[-1:]
def tok_ids(tokenizer, s):
    return tokenizer.convert_tokens_to_ids(tokenizer.tokenize(s))
def special_ids(tokenizer):
    # single-char tokens used as markers (must be real vocab tokens)
    plus = tokenizer.convert_tokens_to_ids(tokenizer.tokenize("+"))[-1]
    cross = tokenizer.convert_tokens_to_ids(tokenizer.tokenize("@"))[-1]
    padt = tokenizer.convert_tokens_to_ids(tokenizer.tokenize("<"))[-1]
    return plus, cross, padt
def build(tokenizer, span_text, sep=" # # "):
    plus, cross, padt = special_ids(tokenizer)
    spans = span_text.split(sep)
    ids = []
    for i, s in enumerate(spans):
        t = tok_ids(tokenizer, s)
        if i == 0:
            ids += pad(t, padt)
        elif i == len(spans) - 1:
            ids += [cross] + t
        else:
            ids += pad([plus] + t, padt)
    return ids
