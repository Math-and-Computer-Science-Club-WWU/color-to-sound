"""Start the Color to Sound window with `python main.py`."""

from ui.main_window import MainWindow


def main() -> None:
    """Open the window and run until it is closed."""
    MainWindow().mainloop()


if __name__ == "__main__":
    main()
