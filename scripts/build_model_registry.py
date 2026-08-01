"""Build lightweight model registry reports from existing experiment artifacts."""

from pathlib import Path

from variant_time_machine.model_registry import build_reports


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    created = build_reports(root)
    print(f"Built {len(created)} registry/report artifacts under {root / 'outputs'}.")


if __name__ == "__main__":
    main()
