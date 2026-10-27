"""Compare hardware CPU benchmark runs of two builds, such as the same machines on two OS releases.

Each side is a profiling package and its benchmark captures (docs/profiling.md). For every
benchmark case the two sides share, by name, it prints each recorded stage's median share of
the stock block budget and the change. Offline; reads private captures, prints no device identity.

    python tools/cpu_compare.py --a <private>/cpu-build-1.2.0 <run-001> <run-002> <run-003> \\
                                --b <private>/cpu-build-1.2.1 <run-001> <run-002> <run-003>
"""
import argparse
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tooling.benchmark import decode  # noqa: E402
from tooling.formats import require  # noqa: E402
from tooling.profile_report import package_data  # noqa: E402

# The stock diagnostic's stages that the whole-voice synth benchmark reports (METHODS), and
# the per-block total; other indices are TE's internal stage timers, printed with --all.
NAMED = {5: 'whole voice', 15: 'block total'}


def medians(package, runs):
    """{(case name, stage index): median budget percent} over the runs."""
    _, report, _ = package_data(package)
    values = {}
    for run in runs:
        capture = json.loads((Path(run) / 'capture.json').read_text(encoding='utf-8'))
        for result in decode(capture, report['benchmark_cases']):
            for metric in result['metrics']:
                if metric['encoded_average']:
                    key = (result['machine']['name'], metric['index'])
                    values.setdefault(key, []).append(metric['average_budget_percent'])
    require(values, 'No benchmark results in these captures')
    return {key: statistics.median(v) for key, v in values.items()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--a', nargs='+', required=True, metavar='PATH', help='package, then its run folders')
    parser.add_argument('--b', nargs='+', required=True, metavar='PATH', help='package, then its run folders')
    parser.add_argument('--all', action='store_true', help='every stage index, not only whole voice and block total')
    args = parser.parse_args(argv)
    require(len(args.a) > 1 and len(args.b) > 1, 'Give each side a package and at least one run')
    a, b = medians(args.a[0], args.a[1:]), medians(args.b[0], args.b[1:])
    shared = sorted(set(a) & set(b), key=lambda k: (k[0], k[1]))
    stages = sorted({i for _, i in shared}) if args.all else sorted(NAMED)
    print(f'{"case":12} {"stage":14} {"A %":>8} {"B %":>8} {"change":>9}')
    for name in dict.fromkeys(n for n, _ in shared):
        for stage in stages:
            if (name, stage) in a and (name, stage) in b:
                x, y = a[(name, stage)], b[(name, stage)]
                print(f'{name:12} {NAMED.get(stage, str(stage)):14} {x:8.3f} {y:8.3f} {100 * (y - x) / x:+8.1f}%')
    only = sorted({n for n, _ in a} ^ {n for n, _ in b})
    if only:
        print('Not on both sides: ' + ', '.join(only))


if __name__ == '__main__':
    main()
