import asyncio
import re

from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.theme import Theme

# Custom JARVIS Theme
jarvis_theme = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "bold red",
    "success": "bold green",
    "system": "bold blue",
    "highlight": "bold cyan",
    "network": "magenta",
    "database": "green",
    "time": "grey50",
    "step": "bold magenta",
    "scan": "bright_cyan",
    "detail": "dim cyan",
    "phase": "bold yellow",
    "timer": "bright_black",
})

console = Console(theme=jarvis_theme)


class JarvisLogger:
    def __init__(self):
        self.subscribers: set[asyncio.Queue] = set()
        self._timers: dict[str, float] = {}

    def _push_to_queues(self, message: str):
        """Internal: push a message to all SSE subscriber queues (thread-safe)."""
        for queue in list(self.subscribers):  # iterate over copy to avoid mutation issues
            try:
                loop = asyncio.get_running_loop()
                loop.call_soon_threadsafe(queue.put_nowait, message)
            except RuntimeError:
                # No running event loop — skip (happens during startup logging)
                pass
            except asyncio.QueueFull:
                pass  # Drop message if queue is full (prevents memory leak)

    def broadcast(self, message: str):
        """Push a status/log message to all active subscribers (strips Rich tags)."""
        clean_msg = re.sub(r'\[/?[^\]]+\]', '', message)
        self._push_to_queues(clean_msg)

    def stream_token(self, token: str):
        """Push a raw AI stream token to frontend (escapes newlines for SSE safety)."""
        escaped_token = token.replace('\n', '\\n').replace('\r', '')
        self._push_to_queues(f"[STREAM] {escaped_token}")

    def stream_start(self):
        """Signal frontend that AI streaming is about to begin."""
        self._push_to_queues("[STREAM_START]")

    def stream_end(self):
        """Signal frontend that AI streaming has finished."""
        self._push_to_queues("[STREAM_END]")

    def print_header(self):
        """Print the JARVIS startup header"""
        # console.clear()
        header = """
[bold cyan]
      :::::::::::     :::     :::::::::  :::     ::: ::::::::::: ::::::::
         :+:       :+: :+:   :+:    :+: :+:     :+:     :+:    :+:    :+:
        +:+      +:+   +:+  +:+    +:+ +:+     +:+     +:+    +:+
       +#+     +#++:++#++: +#++:++#:  +#+     +:+     +#+    +#++:++#++
      +#+     +#+     +#+ +#+    +#+  +#+   +#+      +#+           +#+
 #+# #+#     #+#     #+# #+#    #+#   #+#+#+#       #+#    #+#    #+#
 #####      ###     ### ###    ###     ###      ########### ########
[/bold cyan]
[bold blue]=== SYSTEM NODE ONLINE ===[/bold blue]
[cyan]Awaiting input parameters...[/cyan]
        """
        console.print(Align.center(header))
        print("\n")

    def log_action(self, action: str, target: str = ""):
        """Log a standard action (e.g., searching, analyzing)"""
        target_str = f" [highlight]TAR>{target}[/highlight]" if target else ""
        msg = f"[SYS] {action}{' ' + target if target else ''}"
        console.print(f"[system][SYS][/system] [info]{action}[/info]{target_str} ...")
        self.broadcast(msg)

    def log_success(self, message: str):
        """Log a successful operation"""
        console.print(f"[success][OK][/success] {message}")
        self.broadcast(f"[OK] {message}")

    def log_error(self, message: str):
        """Log an error or failure"""
        console.print(f"[error][ERR][/error] {message}")
        self.broadcast(f"[ERR] {message}")

    def log_thought(self, thought: str):
        """Simulate JARVIS 'thinking' or processing data"""
        console.print(f"[warning][PROCESS][/warning] [italic cyan]{thought}[/italic cyan]")
        self.broadcast(f"[PROCESS] {thought}")

    def log_warning(self, message: str):
        """Log a warning message"""
        console.print(f"[warning][WARN][/warning] {message}")
        self.broadcast(f"[WARN] {message}")

    def log_network_traffic(self, method: str, path: str, client_ip: str, status_code: int = None, process_time: float = None):
        """Log dynamic network requests like a cyber-security terminal"""
        try:
            if status_code is None:
                console.print(f"[network][NET-IN][/network] [bold white]{method}[/bold white] [highlight]{path}[/highlight] <- from IP {client_ip}")
            else:
                color = "success" if status_code < 400 else "error"
                console.print(f"[network][NET-OUT][/network] [bold white]{method}[/bold white] [highlight]{path}[/highlight] -> [{color}]Status: {status_code}[/{color}] [time]({process_time:.2f}ms)[/time]")
        except Exception:
            print(f"[NET] {method} {path} {status_code or '<-'} {client_ip}")

    def log_db_query(self, query_type: str, table: str = "", details: str = ""):
        """Log background database activity mimicking deep data retrieval"""
        try:
            console.print(f"[database][DB-LINK][/database] [bold]{query_type}[/bold] [highlight]{table}[/highlight] {f'-> {details}' if details else ''}")
        except Exception:
            print(f"[DB] {query_type} {table} {details}")

    def log_step(self, step_num: int, total: int, description: str):
        """Log a numbered pipeline step (e.g., Step 3/10: Scanning Instagram)"""
        msg = f"[STEP {step_num}/{total}] {description}"
        console.print(f"[step]▶ STEP {step_num}/{total}[/step] [info]{description}[/info]")
        self.broadcast(msg)

    def log_scan(self, platform: str, target: str, detail: str = ""):
        """Log a platform-specific scan operation"""
        detail_str = f" → {detail}" if detail else ""
        msg = f"[SCAN] {platform}: {target}{detail_str}"
        console.print(f"[scan]  🔍 {platform}[/scan] [highlight]{target}[/highlight]{f' [detail]→ {detail}[/detail]' if detail else ''}")
        self.broadcast(msg)

    def log_detail(self, message: str):
        """Log a sub-step detail (indented, dimmer — for granular info)"""
        msg = f"    ↳ {message}"
        console.print(f"[detail]    ↳ {message}[/detail]")
        self.broadcast(msg)

    def log_phase(self, phase_name: str, description: str = ""):
        """Log a major phase transition with visual separator"""
        separator = "─" * 60
        desc_str = f" — {description}" if description else ""
        msg = f"[PHASE] ═══ {phase_name}{desc_str} ═══"
        console.print(f"\n[phase]{'═' * 60}[/phase]")
        console.print(f"[phase]  ⚡ {phase_name.upper()}{desc_str}[/phase]")
        console.print(f"[phase]{'═' * 60}[/phase]")
        self.broadcast(msg)

    def log_separator(self, label: str = ""):
        """Print a visual separator line for grouping output"""
        if label:
            line = f"──── {label} {'─' * max(1, 50 - len(label))}"
        else:
            line = "─" * 56
        console.print(f"[dim]{line}[/dim]")

    def start_timer(self, label: str):
        """Start a named timer"""
        import time
        self._timers[label] = time.time()

    def stop_timer(self, label: str):
        """Stop a named timer and log the elapsed time"""
        import time
        if label in self._timers:
            elapsed = time.time() - self._timers.pop(label)
            if elapsed >= 60:
                time_str = f"{elapsed / 60:.1f} dakika"
            else:
                time_str = f"{elapsed:.1f}s"
            msg = f"[TIMER] {label}: {time_str}"
            console.print(f"[timer]  ⏱  {label}: {time_str}[/timer]")
            self.broadcast(msg)

    def display_panel(self, title: str, content: str, style: str = "cyan"):
        """Display important data in a styled panel"""
        panel = Panel(content, title=f"[{style}]{title}[/{style}]", border_style=style, width=80)
        console.print(panel)
        print("\n")
        self.broadcast(f"[{title}] {content}")

logger = JarvisLogger()
