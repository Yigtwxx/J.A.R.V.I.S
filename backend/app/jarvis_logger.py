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

class JarvisLogger:
    @staticmethod
    def print_header():
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

    @staticmethod
    def log_action(action: str, target: str = ""):
        """Log a standard action (e.g., searching, analyzing)"""
        target_str = f" [highlight]TAR>{target}[/highlight]" if target else ""
        console.print(f"[system]\[SYS][/system] [info]{action}[/info]{target_str} ...")

    @staticmethod
    def log_success(message: str):
        """Log a successful operation"""
        console.print(f"[success]\[OK][/success] {message}")

    @staticmethod
    def log_error(message: str):
        """Log an error or failure"""
        console.print(f"[error]\[ERR][/error] {message}")

    @staticmethod
    def log_thought(thought: str):
        """Simulate JARVIS 'thinking' or processing data"""
        console.print(f"[warning]\[PROCESS][/warning] [italic cyan]{thought}[/italic cyan]")

    @staticmethod
    def display_panel(title: str, content: str, style: str = "cyan"):
        """Display important data in a styled panel"""
        panel = Panel(content, title=f"[{style}]{title}[/{style}]", border_style=style, width=80)
        console.print(panel)
        print("\n")

logger = JarvisLogger()
