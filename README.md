# Finance Agent

CLI finance intelligence agent for tech + crypto symbols, with optional RL-focused briefing and markdown context feeding.

## Features

- Latest news gathering for tech and crypto symbols
- **Structured, table-based market intelligence output** (Rich UI) grouped by ticker and sorted by date
- Default symbols: AAPL, MSFT, NVDA, TSLA, GOOGL, AMZN, META, BTC, ETH, SOL
- Theme filtering (default: power, oil, tech)
- Optional Gemini summary and RL companion brief
- Markdown context feeding (for session reports) to generate next actionable steps
- **Cross-Platform**: Native support for macOS/Linux (Zsh/Bash) and Windows (PowerShell/Git Bash).
- Stable execution from any directory via launcher scripts.

## Requirements

- Python 3.9+
- Python virtual environment at `.venv`
- Dependencies installed:

### macOS / Linux
```bash
./.venv/bin/pip install -r requirements.txt
```

### Windows
```powershell
.\.venv\Scripts\pip.exe install -r requirements.txt
```

### API Key
Optional for AI summary / next-step planning:

```bash
# macOS / Linux
export GEMINI_API_KEY="your_key_here"

# Windows (PowerShell)
$env:GEMINI_API_KEY="your_key_here"
```

## Seamless Usage

### 1) Run with relative or full path

#### macOS / Linux
```bash
./bin/finance-agent --help
```

#### Windows
```powershell
.\bin\finance-agent.ps1 --help
```

### 2) Add to PATH (recommended)

#### macOS / Linux (Zsh)
Add this to your `~/.zshrc`:
```bash
export PATH="$PATH:/path/to/finance/bin"
```

#### Windows (PowerShell)
Add this to your `$PROFILE`:
```powershell
$env:Path += ";C:\path\to\finance\bin"
```

## Core Commands

### Default run
```bash
finance-agent
# OR (Windows)
finance-agent.ps1
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
  --context-file sessions/quant-report-2026-04-01-0251.md
```

### Custom symbols (supports $ prefix)
```bash
finance-agent --tickers BTC ETH SOL NVDA MSFT --summary --next-steps
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
- Relative paths for instruction/context files are resolved from the current directory first, then from the finance project directory.
- `review_and_run.sh` (macOS/Linux) and `review_and_run.ps1` (Windows) are generated with links to open collected stories.
