"""Integrated experimental AI runner; defaults to $100 paper trading."""
import sys
from run_gold_consensus_bot import main


if __name__ == '__main__':
    if '--hft-paper-replay' in sys.argv or any(a.startswith('--hft-paper-replay=') for a in sys.argv):
        raise SystemExit(main())
    if '--mode' not in sys.argv and not any(a.startswith('--mode=') for a in sys.argv):
        sys.argv.extend(['--mode', 'shadow'])
    if '--exit-policy' not in sys.argv and not any(a.startswith('--exit-policy=') for a in sys.argv):
        sys.argv.extend(['--exit-policy', 'adaptive'])
    from run_gold_consensus_bot import _arguments
    mode = _arguments().mode
    if '--cross-market-policy' not in sys.argv and not any(a.startswith('--cross-market-policy=') for a in sys.argv):
        sys.argv.extend(['--cross-market-policy', 'protect' if mode == 'shadow' else 'observe'])
    if '--learned-policy' not in sys.argv and not any(a.startswith('--learned-policy=') for a in sys.argv):
        sys.argv.extend(['--learned-policy', 'filter' if mode == 'shadow' else 'observe'])
    # Parse once to avoid fragile positional assumptions or duplicate mode flags.
    if mode == 'shadow' and '--paper-trading' not in sys.argv:
        sys.argv.append('--paper-trading')
    raise SystemExit(main())
