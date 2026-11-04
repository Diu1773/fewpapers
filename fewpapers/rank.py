"""Model-free pre-filter: TF-IDF similarity between candidates and the reader profile."""
from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path

from .sources import Paper

STOP = set("""
a an and are as at be been being but by can could did do does for from had has have how in into is it its
may more most not of on or our over such than that the their them then there these they this those through
to under using use used via was we were what when where which while who will with within without also both
each here however paper study results show shows shown present presented propose proposed based new two
one three between than other only well very data method methods approach approaches analysis using
""".split())

NON_RESEARCH = re.compile(r"^(correction|erratum|corrigendum|retraction|editorial|reply|comment on|addendum)\b", re.I)


def tokens(text: str) -> list[str]:
    words = re.findall(r"[a-z][a-z0-9\-]{2,}", text.lower())
    return [w for w in words if w not in STOP]


class Tfidf:
    def __init__(self, docs: list[list[str]]):
        n = len(docs)
        df = Counter()
        for d in docs:
            df.update(set(d))
        self.idf = {t: math.log((1 + n) / (1 + c)) + 1.0 for t, c in df.items()}

    def vec(self, toks: list[str]) -> dict[str, float]:
        tf = Counter(toks)
        v = {t: (1 + math.log(c)) * self.idf.get(t, 1.0) for t, c in tf.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {t: x / norm for t, x in v.items()}


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(t, 0.0) for t, x in a.items())


def load_library(path: Path) -> list[str]:
    """Titles and abstracts from a .bib, .jsonl, .csv or plain .txt file (one entry per line)."""
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    suffix = path.suffix.lower()
    if suffix == ".bib":
        entries = re.split(r"\n@", text)
        out = []
        for e in entries:
            parts = re.findall(r"\b(?:title|abstract)\s*=\s*[{\"](.+?)[}\"]\s*,?\s*\n", e, re.I | re.S)
            if parts:
                out.append(" ".join(parts))
        return out
    if suffix == ".jsonl":
        import json
        out = []
        for line in text.splitlines():
            if line.strip():
                d = json.loads(line)
                out.append(f"{d.get('title', '')} {d.get('abstract', '')}")
        return out
    if suffix == ".csv":
        import csv
        import io
        rows = csv.DictReader(io.StringIO(text))
        return [f"{r.get('title', '')} {r.get('abstract', '')}" for r in rows]
    return [line for line in text.splitlines() if line.strip()]


def score_papers(papers: list[Paper], interests: str, keywords: list[str],
                 exclude_keywords: list[str], library_docs: list[str]) -> list[Paper]:
    """Attach a relevance score and drop non-research items and excluded topics."""
    kept = []
    excl = [k.lower() for k in exclude_keywords]
    for p in papers:
        text = f"{p.title} {p.abstract}".lower()
        if NON_RESEARCH.match(p.title) or not p.title:
            continue
        if any(k in text for k in excl):
            continue
        kept.append(p)
    if not kept:
        return []

    profile_text = interests + " " + " ".join(keywords + keywords)
    cand_toks = [tokens(f"{p.title} {p.title} {p.abstract}") for p in kept]
    lib_toks = [tokens(d) for d in library_docs]
    model = Tfidf(cand_toks + lib_toks + [tokens(profile_text)])
    prof_vec = model.vec(tokens(profile_text))
    lib_vecs = [model.vec(t) for t in lib_toks if t]
    kw = [k.lower() for k in keywords]

    for p, toks in zip(kept, cand_toks):
        v = model.vec(toks)
        s_prof = cosine(v, prof_vec)
        s_lib = max((cosine(v, lv) for lv in lib_vecs), default=0.0)
        text = f"{p.title} {p.abstract}".lower()
        hits = sum(1 for k in kw if k in text)
        no_abstract_penalty = 0.7 if not p.abstract else 1.0
        base = 0.6 * s_prof + 0.4 * s_lib if lib_vecs else s_prof
        p.score = round((base + 0.04 * min(hits, 5)) * no_abstract_penalty, 4)
    kept.sort(key=lambda p: p.score, reverse=True)
    return kept


def _lab_match(p: Paper, labs: list[str]) -> str:
    hay = " ".join([p.signals.get("org", ""), p.signals.get("feed", "")]).lower()
    return next((lab for lab in labs if lab.lower() in hay), "")


def score_landmark(papers: list[Paper], labs: list[str], min_upvotes: int) -> list[Paper]:
    """Rank community-tracked papers by attention: upvotes, code stars and watched labs."""
    kept = []
    for p in papers:
        if not p.title or NON_RESEARCH.match(p.title):
            continue
        up = p.signals.get("upvotes", 0)
        stars = p.signals.get("github_stars", 0)
        lab = _lab_match(p, labs)
        if not (lab or up >= min_upvotes):
            continue
        if lab:
            p.signals["watched_lab"] = lab
        s_up = min(math.log1p(up) / math.log1p(200), 1.0)
        s_stars = min(math.log1p(stars) / math.log1p(5000), 1.0)
        base = 0.7 * s_up + 0.15 * s_stars + (0.15 if lab else 0.0)
        p.score = round(base, 4)
        kept.append(p)
    kept.sort(key=lambda p: p.score, reverse=True)
    return kept
