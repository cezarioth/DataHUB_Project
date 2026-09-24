"""Application entry point for DataHUB.

The user interface lives in :mod:`frontend.main_window`; backend services live
under :mod:`backend`.
"""

from frontend.main_window import App


def main() -> None:
    """Create the desktop application and start its event loop."""
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
