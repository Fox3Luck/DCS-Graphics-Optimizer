"""Where players report problems and talk about the tool. The tool itself sends nothing: these
are pages the player opens in their own browser."""
from __future__ import annotations

from .updates import REPO

LINKS = {
    "issues": f"https://github.com/{REPO}/issues",
    "discord": "https://discord.com/channels/814940459134484511/1571736773682274427",
}


def open_link(which: str) -> str:
    """Open one of the pages above (and nothing else) in the player's browser."""
    import webbrowser
    if which not in LINKS:
        raise RuntimeError("Unknown page.")
    webbrowser.open(LINKS[which])
    return ("The project's GitHub issues are open in your browser." if which == "issues"
            else "The Discord channel is open in your browser.")
