# 🚀 Gemini Zsh Copilot: Project Memory

This project is a context-aware terminal assistant for macOS/Linux (Zsh) that provides explanations, task automation, and error diagnostics using the Gemini 2.0 Flash API.

## 🛠️ Architecture & Components

### 1. Core Script (`gemini_cli.py`)
- **Multi-Mode Operation**: Controlled via the `GEMINI_MODE` environment variable.
    - `ask`: General Knowledge/Q&A.
    - `do`: Task execution (includes an interactive "Execute now?" prompt).
    - `explain`: Diagnostic expert for analyzing piped logs and syntax errors.
- **Context Awareness**: Automatically captures the Current Working Directory (CWD) and active Git Branch.
- **Rich UI**: Utilizes the `Rich` library for structured, color-coded panels:
    - **Plan**: A concise summary of the AI's intended action.
    - **Commands**: Syntax-highlighted code blocks with line numbers.
    - **Explanation**: Brief bullet points explaining the "why" and specific flags.
- **Safety Mechanism**: All suggested commands are automatically written to `review_and_run.sh` and made executable for manual inspection.

### 2. Environment & Dependencies
- **Virtual Environment**: `./gemini-env/`
- **Key Libraries**: `google-genai`, `rich`, `tenacity`, `google-api-core`.
- **API Handling**: Includes robust `tenacity` retry logic to manage `429 RESOURCE_EXHAUSTED` errors.

---

## ⌨️ CLI Configuration (`~/.zshrc`)

To use this tool effectively, add the following to your shell configuration:

```zsh
# Primary script and environment paths
export AGENT_VENV="$HOME/Projects/agentic-dev/cli-agent/gemini-env/bin/python3"
export AGENT_SCRIPT="$HOME/Projects/agentic-dev/cli-agent/gemini_cli.py"

# Mode-based Aliases
alias ask="GEMINI_MODE=ask $AGENT_VENV $AGENT_SCRIPT"
alias do="GEMINI_MODE=do $AGENT_VENV $AGENT_SCRIPT"
alias explain="GEMINI_MODE=explain $AGENT_VENV $AGENT_SCRIPT"
```

---

## 📝 Key Learnings & Session Fixes

- **Dependency Isolation**: Always invoke the script using the virtual environment's Python (`$AGENT_VENV`) to ensure all UI and API libraries are correctly loaded.
- **File Persistence**: The script was explicitly updated to **always overwrite** `review_and_run.sh` in every mode to prevent the accidental execution of stale commands from previous requests.
- **Piping Support**: The script detects `stdin` allowing for powerful diagnostic workflows like `some_command 2>&1 | explain "analyze this error"`.
- **API Resilience**: The `generate_safe_content` function uses exponential backoff to handle rate-limiting gracefully.
- **OS Context**: Added `platform` information to the execution context, ensuring the AI provides platform-specific commands (e.g., macOS-friendly `top` instead of Linux `free`).
- **Robust Parsing**: Updated the response parser to handle numbered headers (e.g., `1) Plan:`, `2) Commands:`) that the model occasionally includes in its output.
- **Visual Consistency**: Forced `Rich` terminal output (`force_terminal=True`) to ensure consistent visual formatting across different terminal types and piping scenarios.

---
*Last updated: Saturday, February 28, 2026*
