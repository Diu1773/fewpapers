# fewpapers

A short daily list of new papers worth your time, from every venue, judged by the AI assistant
you already pay for. No API keys, no server.

Two tracks, either or both:

- **work**: the few papers that touch what you are working on now;
- **landmark**: the few that may change your field or the world, caught early (think of the
  Transformer or GPT-3 papers in their first week, or a quantum error-correction milestone).

fewpapers sends at most a handful, each with one sentence on why it matters to you, and sends
nothing on days when nothing qualifies.

Every paper comes from a real index (arXiv, OpenAlex, NASA ADS, Hugging Face, feeds) before any model
sees it. The assistant is told to choose only from that list, so every pick can be checked against
it, and each reply opens with the list's title and count lines so you can see which day's list it
read.

## Fastest start

Clone this repository, open it in an agent that can run commands (Claude Code or Codex), and say
**"set this up for me"**. The agent follows [`AGENTS.md`](AGENTS.md):

1. it asks a few plain questions, one at a time: what you work on, what you read, which field you
   want the rare big papers from, whether others may see it, and where the result should arrive;
2. it writes the profile, tries every source and shows you sample titles until they look right;
3. after one yes, it creates a private runner repository, stores the profile as a secret and runs
   the first collection;
4. it leaves you only the connections: signing in to GitHub if needed, connecting the ChatGPT
   GitHub app to that one repository, and pasting one prompt to schedule it.

A chat-only assistant (a plain ChatGPT chat) cannot run these commands, so use it for the daily
pick, not for setup.

## How it works

1. **Collect and pre-filter (free, no model).** A GitHub Actions job runs daily and commits
   `output/latest.md` with about 30 + 25 candidates and their abstracts.
   - work: arXiv categories, journals by ISSN and free-text searches across all venues via
     OpenAlex, and NASA ADS (optional); merged, corrections dropped, ranked by text similarity to
     your profile.
   - landmark, in four parts: recent top-journal papers already gathering citations (late
     risers); Hugging Face daily papers ranked by upvotes, code stars and watched labs (with
     `follow_field`, both of these are also ordered by closeness to your field); this
     week's top-journal papers (Nature, Science, PRL, ...) ranked by similarity to your field; and
     the newest posts of lab blogs and science news you follow.
   - Papers already listed are not listed again for 90 days.
2. **Pick (your assistant).** A scheduled task reads the file and applies the rules printed by
   `python -m fewpapers prompt`. A work pick must change what you would do soon (a method or data
   you could adopt, a result that overtakes your approach, another group on the same problem);
   "could be compared with" does not count. A landmark pick must be something people outside its
   subfield will still talk about in a year; most days that is none. With `--industry`, each
   landmark pick also gets the industry it touches, the companies among its authors, how far it is
   from use, and its first news coverage. That is information about industries, not investment
   advice.

```
# Paper candidates 2026-11-12
Fetched 412, 405 unique, 377 not listed before.

[work]
1. Early-cycle features predict end of life for fast-charged cells (Journal of Power Sources)
   Their first-100-cycle features could replace the 500-cycle screening step in the new cell test plan.
   https://doi.org/...

[landmark]
Nothing today.
```

Each candidate in `output/latest.md` lists venue, date, authors, affiliations (companies marked
and first), signals and abstract.

## Privacy

Your profile says what you are working on. Decide where it may be seen before you set up.

- Keep the profile out of git: `profile.local.toml` is ignored, and Actions reads it from the
  `FEWPAPERS_PROFILE` secret. Do not commit a filled-in `profile.toml` to a public repository.
- The daily candidate list (`output/`, `state/`) is derived from the profile. In a public
  repository anyone can read it and infer your topics. Choose one:
  - public repository: simplest; the list is visible;
  - private repository: `examples/private-runner.yml` keeps the list in a private repository, and
    the assistant reads it through its GitHub app (`python -m fewpapers prompt --repo <owner>/<name>`).
    Give the app access to that one repository only;
  - this computer only: nothing leaves the machine, but it must be on at collection time.
- Commit history keeps what was once pushed. Removing a file later does not remove it from earlier
  commits; set a no-reply commit email before the first push.
- `latest.md` includes abstracts from publishers and arXiv for your assistant to read. Keep it in
  a private place rather than republishing it.

## Manual setup

1. Copy `profile.example.toml` to `profile.local.toml` and edit it.
   `python -m fewpapers check` validates it and tries every source.
2. Push the repository to GitHub, store the profile as the `FEWPAPERS_PROFILE` secret
   (`gh secret set FEWPAPERS_PROFILE < profile.local.toml`; in PowerShell `Get-Content -Raw profile.local.toml | gh secret set FEWPAPERS_PROFILE`), and run the **daily candidates**
   workflow once. Optional secrets: `ADS_TOKEN`, `OPENALEX_MAILTO`, `OPENALEX_API_KEY` (free;
   without it OpenAlex returns at most 200 works per journal and per search in one run).
   To keep the candidate list private, see [Privacy](#privacy).
3. Print your prompt and schedule it in your assistant:
   `python -m fewpapers prompt --url https://raw.githubusercontent.com/<you>/<repo>/main/output/latest.md --lang en`
   Claude Code and Codex users can install `skills/fewpapers` instead.

## Commands

```bash
python -m fewpapers                 # collect (same as: collect)
python -m fewpapers check           # validate profile, try each source, resolve ISSNs
python -m fewpapers prompt --url URL --lang ko --n-work 3 --n-landmark 3
python -m fewpapers prompt --repo you/private-runner --industry   # read through the GitHub app
python -m unittest discover -s tests
```

Python 3.11+, standard library only.

## Profile

| field | meaning |
| --- | --- |
| `profile.interests`, `keywords`, `exclude_keywords` | the work track: what you do now, phrases that raise or remove a paper |
| `profile.library` | optional .bib, .jsonl, .csv or .txt of papers you already care about |
| `limits.*` | number of work candidates and fetch windows |
| `sources.arxiv.categories` | arXiv categories |
| `sources.openalex.issns`, `queries` | journals by ISSN; free-text searches across all venues |
| `sources.ads.query` | used only with `ADS_TOKEN` |
| `landmark.field` | the field you follow, in a sentence or two |
| `landmark.labs` | lab names matched against Hugging Face organisations |
| `landmark.journals`, `journal_candidates` | top journals by ISSN; this week's papers ranked by similarity to `landmark.field` |
| `landmark.rising*` | recent papers in those journals that already gather citations (not replayable for past dates) |
| `landmark.feeds`, `feed_max` | lab blog and science news feeds; the newest `feed_max` posts of each |
| `landmark.min_upvotes` | papers outside watched labs need this many upvotes |
| `landmark.follow_field` | also order the rising and Hugging Face parts by closeness to `field`; for a specific field such as batteries, not for a broad one |

## Limits

- Early attention is not lasting importance; the landmark track narrows the field, the assistant
  and you still judge.
- Hugging Face daily papers covers machine learning only and starts in 2023; other fields rely on
  top journals, citations and feeds. Citation counts lag by weeks.
- Replaying a past date (`--date`) works for arXiv, OpenAlex and most feeds, but not for
  Hugging Face before 2023 or for the rising part.
- Some publishers do not deposit abstracts, so a few journal candidates are title-only.
- The ADS source has not been exercised against the live service in this repository's tests.
- GitHub starts scheduled runs late, by up to ten hours on this account's history, so the
  workflows collect at 11:17 UTC for a morning read. Assistants' scheduled tasks can also skip a
  day without notice; the echoed first lines show when a reply came from an older list.
- Fresh preprints often have no affiliations in OpenAlex yet, so "companies among the authors"
  is mostly empty for them.

## License

MIT
