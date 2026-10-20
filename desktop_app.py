"""Native launcher and PyInstaller entry point for Gel Analyzer."""

from gel_analyzer.desktop import main


if __name__ == "__main__":
    raise SystemExit(main())
