# Notes for coding agents (Claude Code, Codex, others)

This repository is fewpapers: a free daily collector (`python -m fewpapers`) plus a daily pick
done by the user's own AI assistant. Python 3.11+, standard library only.
Tests: `python -m unittest discover -s tests`.

When the user asks to set it up ("set this up", "설정해 줘", or opens the repo with no profile),
follow the setup below. For the daily pick itself, follow `skills/fewpapers/SKILL.md`.

Setup needs an agent that can run commands here. A chat-only assistant cannot run `gh` or
`python -m fewpapers`; if that is you, say so in one line and point the user to Claude Code or Codex.

## Setup

You do the work; the user answers questions and approves. At the end, only sign-ins, app
connections and one paste are left for them.

Rules for the whole setup:

- Ask one question per message, in the user's language, in plain words, each with a short example
  answer. Wait for the answer before the next question.
- Ask about content only: what they work on, what they read, which field they follow. Never ask
  for ISSNs, arXiv category codes, cron times or file names; work those out yourself and say what
  you chose.
- Use defaults unless the user objects, and state them once: work 3 and landmark 3 picks a day,
  private repository, collection at 11:17 UTC, the pick at 07:00 in the user's time zone.
- Never create a public repository, push, store a secret, or open a website without a yes. Ask for
  that yes once, for the whole plan, in step 4.
- Never ask the user to paste a token, password or key into the chat.

### 1. Interview

Ask these in order, one per message. Skip a question when an earlier answer already covers it.

1. "What are you working on these days? A few sentences is enough, for example: I predict battery
   capacity fade from early cycling data." Offer to draft it from their repositories, drafts or
   notes instead; ask which folders you may read.
2. "Which journals or arXiv sections do you read, if any? For example: Journal of Power Sources,
   Joule, arXiv materials science." If they do not know, choose them from question 1.
3. "Besides your own work, do you want the rare paper that may change your field or the world?
   If yes, which field? For example: energy storage, or AI in general." A no turns the landmark
   track off.
4. "Should anyone else be able to see what you follow?" The candidate list is derived from the
   profile; in a public repository anyone can read it and infer their topics (README, Privacy).
   No or unsure means the private route.
5. "Where should the daily result reach you, and in what language?" Offer the options in step 5
   with their cost in one line each.

### 2. Write the profile

Write `profile.local.toml` (git-ignored) from `profile.example.toml`:

- `interests`: one concrete paragraph from answer 1. `keywords`: five to eight phrases from it.
- Journals: look ISSNs up through `https://api.openalex.org/sources?search=<journal name>` and use
  exact-name matches, never ISSNs from memory. arXiv categories: choose from the arXiv category
  list for the field.
- Landmark: write `field` from answer 3. The example's labs, feeds and journals are for AI and
  quantum computing. For any other field, replace them: the field's flagship journals plus Nature
  and Science in `journals`, its labs or organisations in `labs` (or none), and its society news or
  lab blogs in `feeds` (or none). Keep `rising` on, and set `follow_field = true` when the field is
  specific (batteries, protein design) rather than broad (frontier science). Hugging Face daily papers are machine learning
  only: unless the field is machine learning itself, set `candidates` to 3, or 0 if they want no
  machine-learning papers.

### 3. Show and confirm

Run `python -m fewpapers check` and fix anything it flags. Then run
`python -m fewpapers collect --no-state --out <scratch folder>` and show the top ten titles of each
track. Ask: "Is this the kind of thing you want? Too broad, too narrow, or something missing?"
Adjust keywords, journals, labs, feeds or `min_upvotes` and show again until they say yes.
In PowerShell, write the run's output to a file instead of using `*>`; its progress lines go to
stderr and PowerShell reports them as errors.

### 4. One plan, one yes

Before anything leaves the machine, check `git config user.email`. It should be a GitHub no-reply
address (`<id>+<user>@users.noreply.github.com`); if not, say so and set it for the runner folder
only with the user's yes. Then show the plan in a few lines and ask for a single yes:

- private route (default): create the private repository `<user>/fewpapers-runner` holding only
  the workflow, store the profile as its `FEWPAPERS_PROFILE` secret, and run it once;
- public route: the same with this repository made public instead;
- this machine only: the profile and lists stay here (the collector still sends its searches to
  the paper sources).

If `gh` is missing or `gh auth status` fails, ask the user to install GitHub CLI and run
`gh auth login` themselves (it opens their browser), then continue.

Private route, bash:

```bash
R=fewpapers-runner; P="$PWD/profile.local.toml"
mkdir -p ../$R/.github/workflows ../$R/output ../$R/state
cp examples/private-runner.yml ../$R/.github/workflows/daily.yml
touch ../$R/output/.gitkeep ../$R/state/.gitkeep
cd ../$R && git init -b main && git add . && git commit -m "fewpapers runner"
gh repo create $R --private --source . --push
gh secret set FEWPAPERS_PROFILE --repo "$(gh api user --jq .login)/$R" < "$P"
gh workflow run daily.yml
```

Private route, PowerShell:

```powershell
$R = "fewpapers-runner"; $P = (Resolve-Path profile.local.toml).Path
New-Item -ItemType Directory -Force "..\$R\.github\workflows", "..\$R\output", "..\$R\state" | Out-Null
Copy-Item examples\private-runner.yml "..\$R\.github\workflows\daily.yml"
New-Item -ItemType File "..\$R\output\.gitkeep", "..\$R\state\.gitkeep" | Out-Null
Push-Location "..\$R"; git init -b main; git add .; git commit -m "fewpapers runner"
gh repo create $R --private --source . --push
Get-Content -Raw $P | gh secret set FEWPAPERS_PROFILE --repo "$(gh api user --jq .login)/$R"
gh workflow run daily.yml; Pop-Location
```

Public route: `gh repo create <name> --public --source . --push`,
the same `gh secret set FEWPAPERS_PROFILE`, then `gh workflow run daily.yml` here.

Wait for the run (`gh run watch`) and confirm that `output/latest.md` was committed and that its
first line carries today's date. The profile goes into the secret, never into a repository.

### 5. The daily pick

| option | runs | reaches the phone | uses |
| --- | --- | --- | --- |
| ChatGPT scheduled task | ChatGPT's servers | ChatGPT app notification | the ChatGPT plan; reads a public raw URL, or a private repository through the ChatGPT GitHub app |
| Claude cloud routine (`/schedule` in Claude Code) | Anthropic's cloud on the repo | Claude app | Claude plan usage |
| Claude desktop scheduled task | this computer, while the app is open | phone only when Remote Control is on | Claude plan usage |
| Codex scheduled automation, if the user's Codex app offers one | Codex | Codex app | Codex plan usage |
| No assistant | - | GitHub app, watching the repository | nothing; the user reads the 30-55 candidates |

- **ChatGPT**: write the prompt to a file with
  `python -m fewpapers prompt --repo <user>/fewpapers-runner --lang <code>` (private) or
  `--url https://raw.githubusercontent.com/<user>/<repo>/main/output/latest.md` (public). Add
  `--industry` if they want industry lines under landmark picks. Scheduled runs do not reliably
  open private links such as secret gists, which is why the private route goes through the
  ChatGPT GitHub app.
- **Claude cloud routine / desktop task / Codex**: install the skill (copy `skills/fewpapers` into
  `~/.claude/skills/` or `~/.codex/skills/`) and schedule "Run the fewpapers daily pick for
  <repo path or URL>" at the chosen time. You can usually do this yourself.

### 6. Connections the user does

End with this list and nothing else for the user to do. Give each item its link and, for the
paste, the exact text from the file you wrote.

1. ChatGPT GitHub app: in ChatGPT, Settings, Apps (or Plugins), connect GitHub. On GitHub's page
   choose **Only select repositories** and pick `fewpapers-runner` only.
2. The paste: open a new ChatGPT chat, paste the prompt, then send "Run this every day at 07:00
   <their time zone>". The pick time must be at least ten hours after the 11:17 UTC collection
   (21:30 UTC or later); move the cron in the runner's workflow if their 07:00 is earlier.
3. Notifications: allow ChatGPT notifications on the phone.

If a browser tool connected to the user's own Chrome is available and the user says yes, you may do
items 1 and 2 in their signed-in session; stop at any sign-in or authorization screen and hand it
back.

### 7. Confirm

Ask the user to press "Run now" on the task (or run it yourself through the browser tool) and
compare the reply's first two lines with the title line (`# Paper candidates <date>`) and the
`Fetched ...` line of `output/latest.md` in the repository. Same lines: done. Different or missing: the assistant read another list or none; check
the app connection. Tell them when it runs next and how to stop it (pause the task, disable the
workflow). Record nothing about the user outside this repository and the runner.
