"""Keep expected command-line failures concise; internal APIs still raise."""
import sys


def run_cli(main):
    try:
        main()
    except (ValueError, OSError, OverflowError) as exc:
        print(f'操作失败：{exc}', file=sys.stderr)
        raise SystemExit(1) from None
