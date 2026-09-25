"""macOS notifications, so you know something needs your answer."""
import subprocess


def _osascript(args: list[str]) -> None:
    subprocess.run(["osascript", *args], timeout=5)


def notify(text: str) -> None:
    try:
        # the text comes from employers (company names, messages): pass it as data, never as AppleScript source
        _osascript(["-e", "on run argv", "-e", 'display notification (item 1 of argv) with title "kolenke"',
                    "-e", "end run", str(text)[:250]])
    except Exception:
        pass
