import sys

from netlauncher import __version__


def main() -> int:
    if "--version" in sys.argv:
        print(__version__)
        return 0
    try:
        from netlauncher.ui.app import main as ui_main
    except ImportError:
        print(f".NET Launcher {__version__}")
        return 0
    return ui_main()


if __name__ == "__main__":
    sys.exit(main())
