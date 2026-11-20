"""The row of four steps that shows how far along the process is, with an explanation of the current step."""

import tkinter as tk
from tkinter import ttk

from common.modes import Channel, Mode
from ui.text import IDLE_EXPLANATION, STAGE_ALL_DONE, STAGE_NONE, STAGE_REBUILD, STAGES, explain

BLUE, GREEN, GREY = "#1565c0", "#2e7d32", "#9e9e9e"
NORMAL_FONT = ("Segoe UI", 10)
BOLD_FONT = ("Segoe UI", 10, "bold")


class StageTracker(ttk.Frame):
    """Shows each step as done (green tick), current (blue arrow) or still to come (grey)."""

    def __init__(self, parent: tk.Misc, wraplength: int) -> None:
        """Build the four step labels and the explanation line beneath them."""
        super().__init__(parent)
        steps = ttk.Frame(self, padding=(8, 4, 8, 0))
        steps.pack(fill="x")
        self.labels = []
        for number, name in enumerate(STAGES, start=1):
            label = tk.Label(steps, text=f"{number}. {name}", font=NORMAL_FONT)
            label.pack(side="left", padx=(0, 14))
            self.labels.append(label)
        self.explanation = tk.StringVar()
        ttk.Label(self, textvariable=self.explanation, wraplength=wraplength, padding=(10, 2, 10, 4),
                  foreground="#444444").pack(fill="x")
        self.show(STAGE_NONE, Channel.CABLE, Mode.FILE)

    def show(self, stage: int, channel: Channel, mode: Mode) -> None:
        """Highlight `stage` (STAGE_NONE for none, STAGE_ALL_DONE for all) and explain what it is doing."""
        for index, label in enumerate(self.labels):
            if index < stage:
                label.configure(text=f"\u2713 {STAGES[index]}", fg=GREEN, font=NORMAL_FONT)
            elif index == stage:
                label.configure(text=f"\u25B6 {STAGES[index]}", fg=BLUE, font=BOLD_FONT)
            else:
                label.configure(text=f"{index + 1}. {STAGES[index]}", fg=GREY, font=NORMAL_FONT)

        if stage == STAGE_NONE:
            self.explanation.set(IDLE_EXPLANATION)
        else:
            self.explanation.set(explain(channel, mode, STAGE_REBUILD if stage == STAGE_ALL_DONE else stage))
