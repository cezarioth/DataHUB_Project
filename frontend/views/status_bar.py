"""Reusable status bar for the DataHUB desktop interface."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

import customtkinter as ctk


class StatusBar(ctk.CTkFrame):
    """Footer that displays application state and exposes a safe update API."""

    def __init__(
        self,
        master: tk.Misc,
        textvariable: tk.StringVar,
        *,
        on_clear: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master, corner_radius=8, height=32)
        self.grid_propagate(False)

        self._textvariable = textvariable
        self._on_clear = on_clear
        self._label = ctk.CTkLabel(
            self,
            textvariable=self._textvariable,
            font=("Segoe UI", 11, "bold"),
            anchor="w",
        )
        self._label.pack(side="left", fill="x", expand=True, padx=(12, 6), pady=6)

        self._clear_button = ctk.CTkButton(
            self,
            text="Limpar",
            width=64,
            height=22,
            corner_radius=5,
            command=self.clear,
        )
        self._clear_button.pack(side="right", padx=(6, 8), pady=5)

    @property
    def label(self) -> ctk.CTkLabel:
        """Return the label for callers that apply theme-specific styling."""
        return self._label

    def clear(self) -> None:
        """Clear the status through the optional callback or a neutral message."""
        if self._on_clear is not None:
            self._on_clear()
            return
        self._textvariable.set("Pronto.")

    def set_message(self, message: str) -> None:
        """Update the visible status message."""
        self._textvariable.set(message)
