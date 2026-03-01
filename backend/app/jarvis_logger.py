from rich.console import Console
from rich.theme import Theme
from rich.panel import Panel
from rich.align import Align
import time
import sys

# Custom JARVIS Theme
jarvis_theme = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "bold red",
    "success": "bold green",
    "system": "bold blue",
    "highlight": "bold cyan",
})

console = Console(theme=jarvis_theme)

import asyncio
from typing import Set

class JarvisLogger:
    def __init__(self):
        self.subscribers: Set[asyncio.Queue] = set()

    def broadcast(self, message: str):
        """Push message to all active subscribers"""
        # Remove any [tags] for the frontend
        import re
        clean_msg = re.sub(r'\[/?[^\]]+\]', '', message)
        
        for queue in self.subscribers:
            try:
                # Use a background task to put in queue to avoid blocking
                loop = None
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    pass
                
                if loop and loop.is_running():
                    loop.call_soon_threadsafe(queue.put_nowait, clean_msg)
            except Exception:
                pass

    def print_header(self):
        """Print the JARVIS startup header"""
        console.clear()
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

    def display_panel(self, title: str, content: str, style: str = "cyan"):
        """Display important data in a styled panel"""
        panel = Panel(content, title=f"[{style}]{title}[/{style}]", border_style=style, width=80)
        console.print(panel)
        print("\n")
        self.broadcast(f"[{title}] {content}")

logger = JarvisLogger()
