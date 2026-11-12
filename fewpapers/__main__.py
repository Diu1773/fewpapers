"""fewpapers: collect and pre-filter new papers, check a profile, or print the daily-pick prompt.

  python -m fewpapers [collect]          fetch, merge, pre-filter, write output/latest.md
  python -m fewpapers check              validate the profile and try every source once
  python -m fewpapers prompt --url URL   print the prompt for an assistant's scheduled task
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .profile import Profile, load_profile
from .prompt import build_prompt
from .rank import load_library, score_landmark, score_papers
from .sources import (add_affiliations, fetch_ads, fetch_arxiv, fetch_feeds, fetch_hf_daily, fetch_openalex,
                      fetch_openalex_rising, newest_per_feed)
from .store import dedupe, filter_unseen, keys, load_seen, update_seen, write_outputs


def _run_jobs(jobs: list[tuple[str, callable]]) -> tuple[list, dict, dict]:
    got_all, errors, counts = [], {}, {}
    for name, job in jobs:
        try:
            got = job()
            counts[name] = len(got)
            got_all.extend(got)
        except Exception as e:
            errors[name] = type(e).__name__
            print(f"{name}: failed ({e})", file=sys.stderr)
    return got_all, errors, counts


def _work_jobs(prof: Profile, today: date) -> list:
    jobs = []
    if prof.arxiv_categories:
        jobs.append(("arxiv", lambda: fetch_arxiv(prof.arxiv_categories, prof.arxiv_lookback_days, today)))
    if prof.openalex_issns or prof.openalex_queries:
        jobs.append(("openalex", lambda: fetch_openalex(prof.openalex_issns, prof.openalex_queries,
                                                        prof.lookback_days, today, prof.openalex_mailto)))
    if prof.ads_query:
        jobs.append(("ads", lambda: fetch_ads(prof.ads_query, prof.lookback_days)))
    return jobs


def _landmark_jobs(prof: Profile, today: date) -> list:
    """Landmark parts in listing order, each with its own fetch, ranking and slot count."""
    lm = prof.landmark
    real_today = datetime.now(timezone.utc).date()
    parts = []
    if lm.rising and lm.journals and today >= real_today - timedelta(days=2):
        parts.append(("rising", lambda: fetch_openalex_rising(lm.journals, lm.rising_days, today,
                                                              lm.rising_min_citations, 50, prof.openalex_mailto),
                      lambda ps: [_mark(p, "rising") for p in ps], lm.rising_candidates))
    parts.append(("hf_daily", lambda: fetch_hf_daily(lm.hf_days, today),
                  lambda ps: score_landmark(ps, lm.labs, lm.min_upvotes), lm.candidates))
    if lm.journals:
        parts.append(("journals", lambda: fetch_openalex(lm.journals, [], lm.journal_lookback_days, today,
                                                         prof.openalex_mailto),
                      lambda ps: score_papers(ps, lm.topic, lm.keywords, [], []), lm.journal_candidates))
    if lm.feeds:
        parts.append(("feeds", lambda: fetch_feeds(lm.feeds, lm.lookback_days, today),
                      lambda ps: newest_per_feed(ps, lm.feed_max), 10 ** 6))
    return parts


def _mark(p, kind: str):
    p.signals["kind"] = kind
    return p


def cmd_collect(args) -> int:
    prof = load_profile(args.profile)
    today = date.fromisoformat(args.date) if args.date else datetime.now(timezone.utc).date()
    state_path = Path(args.state)
    seen = {} if args.no_state else load_seen(state_path)
    sections, errors, stats = {}, {}, {"fetched": 0, "unique": 0, "unseen": 0}
    taken: set[str] = set()
    dead_tracks = []

    if prof.landmark.enabled:
        listed = []
        lm_jobs = _landmark_jobs(prof, today)
        lm_failed = 0
        for name, fetch, rank, slots in lm_jobs:
            fetched, err, _ = _run_jobs([(name, fetch)])
            errors.update(err)
            lm_failed += bool(err)
            unique = dedupe(fetched)
            unseen = [p for p in filter_unseen(unique, seen) if not any(k in taken for k in keys(p))]
            top = rank(unseen)[:slots]
            listed += top
            taken.update(k for p in top for k in keys(p))
            stats["fetched"] += len(fetched); stats["unique"] += len(unique); stats["unseen"] += len(unseen)
            print(f"landmark/{name}: {len(fetched)} -> {len(top)} listed", file=sys.stderr)
        sections["landmark"] = listed
        if lm_jobs and lm_failed == len(lm_jobs):
            dead_tracks.append("landmark")

    if prof.work_enabled:
        jobs = _work_jobs(prof, today)
        fetched, err, counts = _run_jobs(jobs)
        errors.update(err)
        if jobs and len(err) == len(jobs):
            dead_tracks.append("work")
        unique = dedupe(fetched)
        unseen = [p for p in filter_unseen(unique, seen) if not any(k in taken for k in keys(p))]
        library = load_library(prof.base_dir / prof.library) if prof.library else []
        top = score_papers(unseen, prof.interests, prof.keywords, prof.exclude_keywords, library)[: prof.candidates]
        sections["work"] = top
        stats["fetched"] += len(fetched); stats["unique"] += len(unique); stats["unseen"] += len(unseen)
        print(f"work: {counts} -> {len(top)} listed", file=sys.stderr)

    listed_all = [p for ps in sections.values() for p in ps]
    try:
        n = add_affiliations(listed_all, prof.openalex_mailto)
        print(f"affiliations: {sum(bool(p.affiliations) for p in listed_all)} of {len(listed_all)} listed ({n} looked up)",
              file=sys.stderr)
    except Exception as e:  # affiliations are extra; a failed lookup does not stop the run
        errors["affiliations"] = type(e).__name__
        print(f"affiliations: failed ({e})", file=sys.stderr)
    write_outputs(Path(args.out), sections, today, stats, errors)
    if not args.no_state:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        shown = [p for ps in sections.values() for p in ps]
        state_path.write_text(json.dumps(update_seen(seen, shown, today), indent=0, sort_keys=True), encoding="utf-8")
    if dead_tracks:
        print("every source failed for: " + ", ".join(dead_tracks), file=sys.stderr)
        return 1
    return 0


def cmd_check(args) -> int:
    prof = load_profile(args.profile)
    today = datetime.now(timezone.utc).date()
    print("tracks:", ", ".join(t for t, on in [("work", prof.work_enabled), ("landmark", prof.landmark.enabled)] if on))
    ok = True
    jobs = (_work_jobs(prof, today) if prof.work_enabled else []) + \
           ([(n, f) for n, f, _, _ in _landmark_jobs(prof, today)] if prof.landmark.enabled else [])
    for name, job in jobs:
        try:
            n = len(job())
            print(f"  {name}: {n} papers")
            if n == 0:
                print(f"    warning: {name} returned nothing; check categories, ISSNs, queries or URLs")
        except Exception as e:
            ok = False
            print(f"  {name}: FAILED {type(e).__name__}: {e}")
    issns = list(dict.fromkeys(prof.openalex_issns + (prof.landmark.journals if prof.landmark.enabled else [])))
    if issns:
        from .sources import _get
        import urllib.parse
        q = urllib.parse.urlencode({"filter": "issn:" + "|".join(issns), "per-page": 200,
                                    "select": "issn_l,issn,display_name"})
        found = json.loads(_get("https://api.openalex.org/sources?" + q)).get("results", [])
        known = {i for s in found for i in (s.get("issn") or [])}
        for issn in issns:
            name = next((s["display_name"] for s in found if issn in (s.get("issn") or [])), None)
            print(f"  issn {issn}: {name or 'NOT FOUND in OpenAlex'}")
            ok &= issn in known
    return 0 if ok else 1


def cmd_prompt(args) -> int:
    prof = load_profile(args.profile)
    sys.stdout.write(build_prompt(prof, args.url or "", args.lang, args.n_work, args.n_landmark, args.repo or "",
                                  args.industry))
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0].startswith("-"):
        argv.insert(0, "collect")
    ap = argparse.ArgumentParser(prog="fewpapers", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("collect", help="fetch, merge, pre-filter and write candidates")
    c.add_argument("--profile")
    c.add_argument("--out", default="output")
    c.add_argument("--state", default="state/seen.json")
    c.add_argument("--date", help="run as if today were YYYY-MM-DD (UTC)")
    c.add_argument("--no-state", action="store_true", help="ignore and do not update the seen list")
    c.set_defaults(func=cmd_collect)

    k = sub.add_parser("check", help="validate the profile and try each source")
    k.add_argument("--profile")
    k.set_defaults(func=cmd_check)

    p = sub.add_parser("prompt", help="print the scheduled-task prompt")
    p.add_argument("--profile")
    where = p.add_mutually_exclusive_group(required=True)
    where.add_argument("--url", help="raw URL (or local path) of output/latest.md")
    where.add_argument("--repo", help="owner/name of a private repository the assistant reads through its GitHub app")
    p.add_argument("--lang", default="en", help="reply language code, e.g. en, ko")
    p.add_argument("--n-work", type=int, default=3)
    p.add_argument("--n-landmark", type=int, default=3)
    p.add_argument("--industry", action="store_true",
                   help="add industry, makers, stage and first news coverage under each landmark pick")
    p.set_defaults(func=cmd_prompt)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
