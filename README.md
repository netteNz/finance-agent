# Finance Agent

CLI finance intelligence agent for tech + crypto symbols, with optional RL-focused briefing and markdown context feeding.

## Features

- Latest news gathering for tech and crypto symbols
- Default symbols: AAPL, MSFT, NVDA, TSLA, GOOGL, AMZN, META, BTC, ETH, SOL
- Theme filtering (default: power, oil, tech)
- Optional Gemini summary and RL companion brief
- Markdown context feeding (for session reports) to generate next actionable steps
- Stable execution from any directory via launcher script

## Requirements

- macOS/Linux shell (zsh)
- Python virtual environment at `.venv`
- Dependencies installed:

```bash
cd /Users/nettenz/Projects/agentic-dev/awesome-gemini-cli/finance
./.venv/bin/pip install -r requirements.txt
```

Optional for AI summary / next-step planning:

```bash
export GEMINI_API_KEY="your_key_here"
```

## Seamless Usage

### 1) Run with full path (works from anywhere)

```bash
/Users/nettenz/Projects/agentic-dev/awesome-gemini-cli/finance/bin/finance-agent --help
```

### 2) Add to PATH (recommended)

Add this line to your `~/.zshrc`:

```bash
export PATH="$PATH:/Users/nettenz/Projects/agentic-dev/awesome-gemini-cli/finance/bin"
```

Reload shell:

```bash
source ~/.zshrc
```

Now run from anywhere:

```bash
finance-agent --help
```

## Core Commands

### Default run

```bash
finance-agent
```

### Summary + RL brief

```bash
finance-agent --summary --rl-brief
```

### Use attached markdown context and generate next steps

```bash
finance-agent \
  --summary \
  --rl-brief \
  --next-steps \
  --context-file /Users/nettenz/Projects/agentic-dev/reinforcement-learning-stocks/sessions/quant-report-2026-04-01-0251.md
```

### Custom symbols (supports $ prefix)

```bash
finance-agent --tickers $BTC $ETH $SOL NVDA MSFT --summary --next-steps
```

### Custom themes

```bash
finance-agent --themes power oil tech ai datacenter
```

## CLI Options

- `--tickers`: symbols to scan
- `--themes`: keyword filter list
- `--per-ticker-limit`: max items per symbol
- `--timeout`: HTTP timeout seconds
- `--summary`: generate AI summary
- `--rl-brief`: use RL-optimization-style summary sections
- `--context-file`: markdown file used as context
- `--next-steps`: generate concrete next actions from context + news
- `--instructions-file`: instruction policy file (default: `AGENT_INSTRUCTIONS.md`)

## Notes

- The launcher uses the local `.venv` automatically.
- Relative paths for instruction/context files are resolved from current directory first, then from the finance project directory.
- A `review_and_run.sh` file is generated with links to open collected stories.
