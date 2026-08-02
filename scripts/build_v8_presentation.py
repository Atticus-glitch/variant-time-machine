"""Build deterministic presentation data from the frozen V8 evaluation."""

from pathlib import Path

from variant_time_machine.v8_presentation import build_v8_presentation


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    created = build_v8_presentation(root)
    print(f"Built {len(created)} V8 presentation artifacts under {root / 'outputs'}.")


if __name__ == "__main__":
    main()
