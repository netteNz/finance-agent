import argparse
import datetime as dt
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import List
from urllib.parse import quote_plus

import feedparser
import requests
from google import genai
from google.api_core import exceptions
from google.genai import types
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_random_exponential

try:
    from googlenewsdecoder import gnewsdecoder
    GOOGLENEWSDECODER_AVAILABLE = True
except ImportError:
    GOOGLENEWSDECODER_AVAILABLE = False


# --- UI Setup with Rich ---
try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.theme import Theme
    from rich.table import Table

    custom_theme = Theme(
        {
            "info": "bold cyan",
            "warning": "bold yellow",
            "error": "bold red",
            "success": "bold green",
            "dim": "grey50",
        }
    )
    console = Console(theme=custom_theme, force_terminal=True)
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    console = None
    Table = None


DEFAULT_TECH_STOCKS = ["AAPL", "MSFT", "NVDA", "TSLA", "GOOGL", "AMZN", "META", "BTC", "ETH", "SOL"]
DEFAULT_THEMES = ["power", "oil", "tech"]
DEFAULT_INSTRUCTIONS_FILE = "AGENT_INSTRUCTIONS.md"
DEFAULT_CONTEXT_FILE = ""
BASE_DIR = Path(__file__).resolve().parent


@dataclass
class NewsItem:
    ticker: str
    title: str
    source: str
    link: str
    published: str
    summary: str


class AgentInstructionLoader:
    def __init__(self, instructions_file: str, base_dir: Path):
        self.instructions_file = instructions_file
        self.base_dir = base_dir

    def load(self) -> str:
        path = Path(self.instructions_file)
        if not path.is_absolute():
            candidate_cwd = Path.cwd() / path
            candidate_base = self.base_dir / path
            path = candidate_cwd if candidate_cwd.exists() else candidate_base
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8").strip()


class MarkdownContextLoader:
    def __init__(self, markdown_file: str, base_dir: Path):
        self.markdown_file = markdown_file
        self.base_dir = base_dir

    def load(self) -> str:
        if not self.markdown_file:
            return ""
        path = Path(self.markdown_file)
        if not path.is_absolute():
            candidate_cwd = Path.cwd() / path
            candidate_base = self.base_dir / path
            path = candidate_cwd if candidate_cwd.exists() else candidate_base
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8").strip()


class RichPrinter:
    def __init__(self, enabled: bool, rich_console):
        self.enabled = enabled
        self.console = rich_console

    def print_line(self, text: str, style: str = "") -> None:
        if self.enabled:
            self.console.print(text, style=style)
        else:
            print(text)

    def render_items(self, items: List[NewsItem]) -> None:
        if not items:
            self.print_line("No matching news found for your filters.", "warning")
            return

        if self.enabled:
            table = Table(
                title="Structured Market Intelligence",
                show_header=True,
                header_style="bold cyan",
                border_style="dim",
                expand=True
            )
            table.add_column("Ticker", style="bold yellow", width=10)
            table.add_column("Source & Time", style="dim", width=25)
            table.add_column("Intelligence (Headline + Summary)", overflow="fold")

            for item in items:
                # Truncate summary for neatness
                clean_summary = (item.summary or "").replace("\n", " ")
                summary_excerpt = f"{clean_summary[:280]}..." if len(clean_summary) > 280 else clean_summary
                
                source_time = f"[bold cyan]{item.source}[/]\n{item.published}"
                intelligence = (
                    f"[bold white]{item.title}[/]\n"
                    f"[dim]{summary_excerpt}[/]\n"
                    f"[blue underline][link={item.link}]{item.link}[/link]"
                )
                table.add_row(item.ticker, source_time, intelligence)
                # Add a spacer row between news items for readability if they aren't the last one
                if item != items[-1]:
                    table.add_row("", "", "")

            self.console.print(table)
        else:
            for item in items:
                print(f"\n[{item.ticker}] {item.title}")
                print(f"Source: {item.source}")
                print(f"Published: {item.published}")
                print(f"Summary: {item.summary[:400]}")
                print(f"Link: {item.link}")


class NewsFetcher:
    def __init__(self, themes: List[str], timeout: int, per_ticker_limit: int):
        self.themes = themes
        self.timeout = timeout
        self.per_ticker_limit = per_ticker_limit

    @staticmethod
    def normalize_symbol(symbol: str) -> str:
        return symbol.strip().upper().lstrip("$")

    @staticmethod
    def _build_google_news_rss_url(ticker: str, themes: List[str]) -> str:
        theme_expr = " OR ".join(themes)
        crypto_symbols = {"BTC", "ETH", "SOL"}
        if ticker in crypto_symbols:
            query = f"{ticker} crypto ({theme_expr}) when:7d"
        else:
            query = f"{ticker} stock ({theme_expr}) when:7d"
        return f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"

    @staticmethod
    def _parse_entry_date(entry) -> str:
        published = entry.get("published") or entry.get("updated")
        if published:
            return published
        return dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    @staticmethod
    def _strip_html(text: str) -> str:
        return re.sub(r"<[^>]+>", "", text or "").strip()

    @staticmethod
    def _contains_theme(text: str, themes: List[str]) -> bool:
        lower = (text or "").lower()
        return any(theme.lower() in lower for theme in themes)

    @staticmethod
    def _decode_google_news_url(source_url: str) -> str:
        """Resolves the 2024/2025 style Google News redirect URLs to the direct article link."""
        if GOOGLENEWSDECODER_AVAILABLE:
            try:
                decoded_data = gnewsdecoder(source_url, interval=1)
                if decoded_data.get("status"):
                    return decoded_data["decoded_url"]
            except Exception:
                pass # Fallback to manual implementation

        try:
            # Extract the article ID
            if "articles/" not in source_url:
                return source_url
            
            article_id = source_url.split("articles/")[1].split("?")[0]
            
            # Google's BatchExecute protocol for resolving article URLs
            url = "https://news.google.com/_/DotsSplashUi/data/batchexecute?rpcids=Fbv4je"
            payload = [
                [
                    ["Fbv4je", 
                     re.sub(r"\s+", "", f"""["garturlreq", [["en", "US", ["FINANCE_TOP_INDICES", "WEB_TEST_1_0_0"], null, null, 1, 1, "US:en", null, 180, null, null, null, null, null, 0, null, None, [1717597091, 738001000]], "en", "US", 1, [2, 3, 4, 8], 1, 0, "658136446", 0, 0, null, 0], "{article_id}"]""").replace("null", "null"),
                     None, 
                     "generic"]
                ]
            ]
            
            # Wait, the payload structure in the search result used json.dumps. 
            # I should use json.dumps for robustness.
            import json
            import urllib.parse
            
            # Real payload from search result (Option 2)
            inner_payload = ["garturlreq", [["en", "US", ["FINANCE_TOP_INDICES", "WEB_TEST_1_0_0"], None, None, 1, 1, "US:en", None, 180, None, None, None, None, None, 0, None, None, [1717597091, 738001000]], "en", "US", 1, [2, 3, 4, 8], 1, 0, "658136446", 0, 0, None, 0], article_id]
            payload = [[["Fbv4je", json.dumps(inner_payload), None, "generic"]]]
            
            headers = {
                "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
                "Referer": "https://news.google.com/"
            }
            data = f"f.req={urllib.parse.quote(json.dumps(payload))}"
            
            response = requests.post(url, headers=headers, data=data, timeout=10)
            if response.status_code != 200:
                return source_url
            
            # Parse the response (Google's format starts with )]}' )
            res_text = response.text.split("\n\n")[1]
            res_json = json.loads(res_text)
            
            if not res_json or not res_json[0] or not res_json[0][2]:
                return source_url
                
            inner_data = json.loads(res_json[0][2])
            return inner_data[1][1]
            
        except Exception:
            # Fallback to the original URL if decoding fails
            return source_url

    def fetch_for_ticker(self, ticker: str) -> List[NewsItem]:
        url = self._build_google_news_rss_url(ticker, self.themes)
        response = requests.get(url, timeout=self.timeout)
        response.raise_for_status()
        feed = feedparser.parse(response.text)

        items: List[NewsItem] = []
        for entry in feed.entries:
            title = entry.get("title", "").strip()
            summary = self._strip_html(entry.get("summary", ""))
            if not self._contains_theme(f"{title} {summary}", self.themes):
                continue

            source = "Unknown"
            if "source" in entry and isinstance(entry.source, dict):
                source = entry.source.get("title", "Unknown")

            original_link = entry.get("link", "")
            # Decode Google News links to direct article links to avoid 400 errors and tracking redirects
            decoded_link = self._decode_google_news_url(original_link)

            items.append(
                NewsItem(
                    ticker=ticker,
                    title=title,
                    source=source,
                    link=decoded_link,
                    published=self._parse_entry_date(entry),
                    summary=summary,
                )
            )
            # Small delay to avoid rate limiting from Google's BatchExecute API if many URLs are decoded
            import time
            time.sleep(0.2)
            
            if len(items) >= self.per_ticker_limit:
                break

        return items

    def fetch_all(self, tickers: List[str], printer: RichPrinter) -> List[NewsItem]:
        all_items: List[NewsItem] = []
        for ticker in tickers:
            clean_ticker = self.normalize_symbol(ticker)
            try:
                all_items.extend(self.fetch_for_ticker(clean_ticker))
            except requests.RequestException as err:
                printer.print_line(f"Failed to fetch news for {clean_ticker}: {err}", "error")
        all_items.sort(key=lambda x: (x.ticker, x.published), reverse=True)
        return all_items


class GeminiSummarizer:
    def __init__(self, agent_instructions: str = "", rl_brief: bool = False):
        self.api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        self.agent_instructions = agent_instructions
        self.rl_brief = rl_brief

    @retry(
        wait=wait_random_exponential(min=1, max=30),
        stop=stop_after_attempt(4),
        retry=retry_if_exception_type(exceptions.ResourceExhausted),
    )
    def _generate_safe_content(self, client, model, contents, config):
        return client.models.generate_content(model=model, contents=contents, config=config)

    def summarize(self, items: List[NewsItem]) -> str:
        if not self.api_key:
            return ""

        client = genai.Client(api_key=self.api_key)
        digest_lines = []
        for idx, item in enumerate(items[:30], start=1):
            digest_lines.append(
                f"{idx}. [{item.ticker}] {item.title} | {item.source} | {item.published}\n"
                f"Summary: {item.summary}\n"
                f"URL: {item.link}"
            )

        if self.rl_brief:
            prompt = (
                "You are producing a companion intelligence brief for an RL trading optimization agent. "
                "Use the news below to provide inputs that can inform experiment hypotheses, not trade advice.\n\n"
                "Required output sections:\n"
                "1) Regime Signals (5 bullets): short-term market structure clues from news\n"
                "2) Feature Ideas (5 bullets): possible engineered feature ideas for market/news pipelines\n"
                "3) Reward/Risk Implications (4 bullets): potential effects on win-rate, stability, drawdown\n"
                "4) Sweep Hypotheses (4 bullets): candidate experiment directions for SAC/PPO tuning\n"
                "5) Hard Cautions (3 bullets): overfitting/leakage/confounding risks from this news set\n\n"
                "News items:\n" + "\n\n".join(digest_lines)
            )
        else:
            prompt = (
                "You are a finance analyst. Summarize the most relevant market-moving news with a focus on tech stocks and "
                "connections to power/energy demand, oil, and core technology trends.\n\n"
                "Provide:\n"
                "1) Top 5 headlines with one-line impact each\n"
                "2) Sector read-through in 4 bullets\n"
                "3) Risks to watch in 3 bullets\n\n"
                "News items:\n" + "\n\n".join(digest_lines)
            )

        system_parts = ["Be concise, factual, and avoid investment advice."]
        if self.agent_instructions:
            # Keep context bounded while still honoring user-provided agent policy.
            system_parts.append("Follow these user-provided agent instructions when applicable:")
            system_parts.append(self.agent_instructions[:6000])
        system_instruction = "\n\n".join(system_parts)

        response = self._generate_safe_content(
            client=client,
            model="gemini-2.0-flash",
            contents=prompt,
            config=types.GenerateContentConfig(system_instruction=system_instruction),
        )
        return (response.text or "").strip()


class ActionStepPlanner:
    def __init__(self, agent_instructions: str = ""):
        self.api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        self.agent_instructions = agent_instructions

    @retry(
        wait=wait_random_exponential(min=1, max=30),
        stop=stop_after_attempt(4),
        retry=retry_if_exception_type(exceptions.ResourceExhausted),
    )
    def _generate_safe_content(self, client, model, contents, config):
        return client.models.generate_content(model=model, contents=contents, config=config)

    def build_next_steps(self, items: List[NewsItem], markdown_context: str) -> str:
        if not self.api_key:
            return ""

        client = genai.Client(api_key=self.api_key)
        digest_lines = []
        for idx, item in enumerate(items[:20], start=1):
            digest_lines.append(
                f"{idx}. [{item.ticker}] {item.title} | {item.source} | {item.published}\n"
                f"Summary: {item.summary}"
            )

        context_excerpt = markdown_context[:9000] if markdown_context else "No context markdown provided."
        prompt = (
            "You are supporting an RL optimization workflow. Use the report context and latest market/news signals to produce "
            "the next concrete actions.\n\n"
            "Output format (strict):\n"
            "## Next Actionable Steps\n"
            "1) Immediate command sequence (3-5 shell commands)\n"
            "2) Sweep hypothesis list (3 items)\n"
            "3) Gate-focused success criteria mapped to metrics\n"
            "4) Risk controls/checks before running\n"
            "5) One short fallback plan if gates fail\n\n"
            "Report context markdown:\n"
            f"{context_excerpt}\n\n"
            "Latest relevant news:\n"
            + "\n\n".join(digest_lines)
        )

        system_parts = [
            "Be concise, operational, and evidence-driven. Avoid investment advice.",
        ]
        if self.agent_instructions:
            system_parts.append("Apply these user instructions where relevant:")
            system_parts.append(self.agent_instructions[:6000])

        response = self._generate_safe_content(
            client=client,
            model="gemini-2.0-flash",
            contents=prompt,
            config=types.GenerateContentConfig(system_instruction="\n\n".join(system_parts)),
        )
        return (response.text or "").strip()


class ReviewScriptWriter:
    @staticmethod
    def write(items: List[NewsItem]) -> None:
        import sys
        # Generate both .sh and .ps1 for maximum portability
        # Use bash for broader compatibility (works on macOS, Linux, and Git Bash)
        sh_lines = ["#!/usr/bin/env bash", "", "# Latest filtered news links", ""]
        ps1_lines = ["# Latest filtered news links", ""]
        
        # Use sys.executable to ensure we use the same python that is currently running
        python_exe = sys.executable
        
        for item in items:
            if item.link:
                clean_title = item.title.replace("'", "").replace("\"", "")
                # Shell version
                sh_lines.append(f"echo '{item.ticker}: {clean_title}'")
                sh_lines.append(f"\"{python_exe}\" -m webbrowser -t '{item.link}'")
                sh_lines.append("sleep 1")
                
                # PowerShell version
                ps1_lines.append(f"Write-Host '{item.ticker}: {clean_title}'")
                ps1_lines.append(f"Start-Process '{item.link}'")
                ps1_lines.append("Start-Sleep -Seconds 1")
                
        with open("review_and_run.sh", "w", encoding="utf-8") as file_obj:
            file_obj.write("\n".join(sh_lines) + "\n")
        os.chmod("review_and_run.sh", os.stat("review_and_run.sh").st_mode | stat.S_IEXEC)
        
        with open("review_and_run.ps1", "w", encoding="utf-8") as file_obj:
            file_obj.write("\n".join(ps1_lines) + "\n")


class FinanceNewsAgentApp:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.printer = RichPrinter(RICH_AVAILABLE, console)
        self.instructions = AgentInstructionLoader(args.instructions_file, BASE_DIR).load()
        self.markdown_context = MarkdownContextLoader(args.context_file, BASE_DIR).load()
        self.fetcher = NewsFetcher(
            themes=args.themes,
            timeout=args.timeout,
            per_ticker_limit=args.per_ticker_limit,
        )
        self.summarizer = GeminiSummarizer(
            agent_instructions=self.instructions,
            rl_brief=args.rl_brief,
        )
        self.action_planner = ActionStepPlanner(agent_instructions=self.instructions)

    def run(self) -> int:
        if self.instructions:
            self.printer.print_line(
                f"Loaded agent instructions from {self.args.instructions_file}",
                "dim",
            )
        else:
            self.printer.print_line(
                f"Instruction file not found: {self.args.instructions_file} (continuing without it)",
                "warning",
            )

        if self.args.context_file:
            if self.markdown_context:
                self.printer.print_line(
                    f"Loaded markdown context from {self.args.context_file}",
                    "dim",
                )
            else:
                self.printer.print_line(
                    f"Context file not found or empty: {self.args.context_file}",
                    "warning",
                )

        items = self.fetcher.fetch_all(self.args.tickers, self.printer)

        self.printer.print_line(
            f"\nFound {len(items)} relevant stories across {len(self.args.tickers)} ticker(s).",
            "success",
        )
        self.printer.render_items(items)

        if items:
            ReviewScriptWriter.write(items)
            self.printer.print_line("\nSaved open commands to review_and_run.sh", "dim")

        if self.args.summary and items:
            self.printer.print_line("\nGenerating Gemini summary...", "info")
            try:
                summary = self.summarizer.summarize(items)
                if summary:
                    if RICH_AVAILABLE:
                        console.print(Panel(Markdown(summary), title="AI Market Summary", border_style="green"))
                    else:
                        print("\nAI Market Summary\n")
                        print(summary)
                else:
                    self.printer.print_line("GEMINI_API_KEY not set; skipped summary.", "warning")
            except Exception as err:
                self.printer.print_line(f"Summary generation failed: {err}", "error")

        if self.args.next_steps and items:
            self.printer.print_line("\nGenerating next actionable steps...", "info")
            try:
                steps = self.action_planner.build_next_steps(items, self.markdown_context)
                if steps:
                    if RICH_AVAILABLE:
                        console.print(Panel(Markdown(steps), title="Next Actionable Steps", border_style="magenta"))
                    else:
                        print("\nNext Actionable Steps\n")
                        print(steps)
                else:
                    self.printer.print_line("GEMINI_API_KEY not set; skipped next-step generation.", "warning")
            except Exception as err:
                self.printer.print_line(f"Next-step generation failed: {err}", "error")

        return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch latest tech-stock news related to power, oil, and tech themes."
    )
    parser.add_argument(
        "--tickers",
        nargs="+",
        default=DEFAULT_TECH_STOCKS,
        help="Tickers/symbols to scan (default: major tech + BTC ETH SOL).",
    )
    parser.add_argument(
        "--themes",
        nargs="+",
        default=DEFAULT_THEMES,
        help="Keywords to keep news relevant (default: power oil tech).",
    )
    parser.add_argument(
        "--per-ticker-limit",
        type=int,
        default=4,
        help="Maximum items per ticker.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=15,
        help="HTTP timeout in seconds.",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Generate an AI summary using Gemini (requires GEMINI_API_KEY).",
    )
    parser.add_argument(
        "--instructions-file",
        default=DEFAULT_INSTRUCTIONS_FILE,
        help="Path to agent instructions used to guide summary behavior.",
    )
    parser.add_argument(
        "--context-file",
        default=DEFAULT_CONTEXT_FILE,
        help="Markdown file to feed as session context for action planning.",
    )
    parser.add_argument(
        "--rl-brief",
        action="store_true",
        help="Generate an RL-companion brief aligned to optimization workflows.",
    )
    parser.add_argument(
        "--next-steps",
        action="store_true",
        help="Generate concrete next actionable steps using news + markdown context.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    app = FinanceNewsAgentApp(args)
    return app.run()


if __name__ == "__main__":
    raise SystemExit(main())
