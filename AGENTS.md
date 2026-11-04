# Notes for coding agents (Claude Code, Codex, others)

This repository is fewpapers: a free daily collector (`python -m fewpapers`) plus a daily pick
done by the user's own AI assistant. Python 3.11+, standard library only.
Tests: `python -m unittest discover -s tests`.

When the user asks to set it up ("set this up", "설정해 줘", or opens the repo with no profile),
follow the setup below. For the daily pick itself, follow `skills/fewpapers/SKILL.md`.

## Setup

Do the steps in order. Ask only what you cannot find out yourself, in one message per step.
Never create a public repository, push, store a secret, or open a website on the user's behalf
without an explicit yes for that action.

### 1. What to watch

Ask which of the two tracks they want, and the few facts each needs:

- **work**: papers that touch what they are working on now. Offer to draft the description from
  their repositories, drafts or notes (ask which folders you may read), or take it in their words.
  Also ask which arXiv categories and journals they read; look journal ISSNs up through
  `https://api.openalex.org/sources?search=<journal name>` rather than from memory.
- **landmark**: discoveries that may change a field or the world (the next Transformer, a quantum
  computing milestone). Ask the field(s), then offer the defaults in `profile.example.toml`: watched
  labs, top journals (add the field's own flagship journals), and lab blog or science news feeds.

Also ask: how many picks per day per track (defaults: work 3, landmark 3) and the reply language.

Write `profile.local.toml` (git-ignored) from `profile.example.toml`. Keep `interests` to a
concrete paragraph. Run `python -m fewpapers check` and fix anything it flags, then run
`python -m fewpapers collect --no-state --out /tmp-or-scratch-dir` and show the user the top ten
titles of each track. Adjust keywords, journals, labs or `min_upvotes` until they look right.

### 2. Where the collector runs

First ask one question: may others see what they follow? The daily candidate list is derived from
the profile, so in a public repository anyone can read it and infer their topics (README, Privacy).

| option | when to choose | what you do |
| --- | --- | --- |
| GitHub Actions, public repository | the user has GitHub, the computer may be off at collection time, and the list may be seen | with the user's yes: `gh repo create <name> --public --source . --push`, `gh secret set FEWPAPERS_PROFILE < profile.local.toml`, `gh workflow run daily.yml`, then confirm `output/latest.md` was committed |
| GitHub Actions, private repository + secret gist | as above, but the list must stay private | with the user's yes: create a private repository holding only `examples/private-runner.yml` as `.github/workflows/daily.yml` (plus empty `output/` and `state/`), `gh secret set FEWPAPERS_PROFILE`, create a secret gist with `gh gist create` and store its id as the `GIST_ID` variable. The user creates a classic token with only the `gist` scope and stores it as the `GIST_TOKEN` secret; never ask them to paste it to you. Run the workflow once and confirm the gist changed |
| This machine only | no GitHub, and the daily pick runs here | nothing to host; the daily pick runs `python -m fewpapers` first |

The profile goes into the secret, never into a repository, unless the user says otherwise. Before
the first push, check that git commits with a no-reply email (`git config user.email`).

### 3. Who picks and where it arrives

Ask where they want the daily result. Explain the cost in one line each:

| option | runs | reaches the phone | uses |
| --- | --- | --- | --- |
| ChatGPT scheduled task | ChatGPT's servers | ChatGPT app notification | the ChatGPT plan, no Claude/Codex usage; needs a URL readable without sign-in (public raw URL or secret gist) |
| Claude cloud routine (`/schedule` in Claude Code) | Anthropic's cloud on the repo | Claude app | Claude plan usage |
| Claude desktop scheduled task | this computer, while the app is open | phone only when Remote Control is on | Claude plan usage |
| Codex scheduled automation, if the user's Codex app offers one | Codex | Codex app | Codex plan usage |
| No assistant | - | GitHub app, watching the repository | nothing; the user reads the 30-45 candidates |

Then set it up:

- **ChatGPT**: run `python -m fewpapers prompt --url <URL> --lang <code> --n-work N --n-landmark M`,
  where URL is `https://raw.githubusercontent.com/<owner>/<repo>/main/output/latest.md` (public
  repository) or `https://gist.githubusercontent.com/<owner>/<gist id>/raw/latest.md` (secret gist),
  and give the user the text with two instructions: paste it into a new ChatGPT chat, and ask
  ChatGPT to run it every day at the chosen time (a time after 21:30 UTC). If a browser tool
  connected to the user's own Chrome is available and the user says yes, you may open
  chatgpt.com in their signed-in session and do this for them; stop if a sign-in is needed.
- **Claude cloud routine / desktop task / Codex**: install the skill (copy `skills/fewpapers`
  into `~/.claude/skills/` or `~/.codex/skills/`) and schedule the prompt
  "Run the fewpapers daily pick for <repo path or URL>" at the chosen time.

### 4. Confirm

Run the daily pick once now through the chosen route and show the user the result. Tell them when
it will run next and how to stop it. Record nothing about the user outside this repository.
