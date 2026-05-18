import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest OpenAQ data into staging and OLTP tables.")
    parser.add_argument("--initial", action="store_true", help="Run the initial historical load.")
    parser.add_argument("--incremental", action="store_true", help="Run an incremental load.")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not args.initial and not args.incremental:
        parser.print_help()
        return

    mode = "initial" if args.initial else "incremental"
    print(f"OpenAQ ingestion scaffold ready for {mode} mode.")


if __name__ == "__main__":
    main()
