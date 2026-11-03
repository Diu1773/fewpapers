# Daily pick prompt

The prompt for an assistant's scheduled task is built from your profile:

```bash
python -m paper_radar prompt --url https://raw.githubusercontent.com/<owner>/<repo>/main/output/latest.md --lang en --n-work 3 --n-landmark 3
```

Paste the printed text into a new chat in ChatGPT (or any assistant that can open a URL) and ask it
to run the same request every day, some time after the collector's 21:00 UTC run. Rebuild it when
you change the profile.
