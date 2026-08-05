import sys


def main() -> int:
    if len(sys.argv) > 1:
        from kkday_scraper.cli import main as cli_main

        return cli_main(sys.argv[1:])

    from kkday_scraper.gui import main as gui_main

    gui_main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
