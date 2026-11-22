---
name: fewpapers
description: Daily paper pick from fewpapers candidates - every candidate scored 1 to 5, only the few at 3 or more reported, with a one-line headline for the phone. Use for the scheduled daily paper pick, "what should I read today", or to set up or tune fewpapers (setup steps are in the repository's AGENTS.md).
---

# fewpapers daily pick

The collector (`python -m fewpapers`) writes `output/latest.md`: today's candidates in up to two
tracks, **work** (similar to the user's current work) and **landmark** (early attention: upvotes,
code stars, watched labs, lab blogs). The pick is the part that needs judgment.

## Daily pick

1. Get the candidates. In a checkout of the user's fewpapers repository, use `output/latest.md`
   if its first line is from today or yesterday (UTC); otherwise run `python -m fewpapers` first.
   Without a checkout, open the raw URL of `output/latest.md` the user gave.
2. Get the instructions: run
   `python -m fewpapers prompt --url output/latest.md --lang <user's language> --max N`
   (the user's number; default 3). It prints the 1-5 scale and reply shape built from the user's
   profile. Follow them exactly: score every candidate, report only 3 or more, highest first.
   Nothing at 3 or more is the usual answer. Judge only from title, abstract and signals.
3. Deliver the digest and nothing else. When the host offers a push-notification tool, send the
   reply's first line, which is written for a notification. When the user asked for GitHub issues,
   post with `gh issue create --title "Papers <date>" --body-file <file>`.
4. Append one JSON line per reported paper to `state/picks.jsonl`:
   `{"date", "score", "title", "link", "reason"}`.

## Tuning

When the user says the picks are off, read `state/picks.jsonl` and their words, then edit the
profile: sharpen `interests` or `landmark.field`, add `exclude_keywords`, change watched labs or
`min_upvotes`. Run `python -m fewpapers check` after editing. Keep the profile short.

## Setup

For a first-time setup, follow `AGENTS.md` in the repository root.
