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
    "time": "grey50"
})

console = Console(theme=jarvis_theme)


class JarvisLogger:
    def __init__(self):
        self.subscribers: set[asyncio.Queue] = set()

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

    def display_panel(self, title: str, content: str, style: str = "cyan"):
        """Display important data in a styled panel"""
        panel = Panel(content, title=f"[{style}]{title}[/{style}]", border_style=style, width=80)
        console.print(panel)
        print("\n")
        self.broadcast(f"[{title}] {content}")

logger = JarvisLogger()
