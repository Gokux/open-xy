"""Offline aggregation of complete hardware runs, bound to a clean machine revision."""
import json
from pathlib import Path
import statistics

from .benchmark import case_label, combined_positions, decode, position
from .cpu_measurement import BENCHMARKS, RECOMMENDED_PERCENT, above_recommended, validate
from .formats import require, sha


def package_data(package):
    package = Path(package)
    manifest_bytes = (package / 'manifest.json').read_bytes()
    manifest = json.loads(manifest_bytes)
    require(manifest.get('profiling') is True, 'Benchmark requires a profiling-enabled package')
    report_bytes = (package / 'analysis/compile-report.json').read_bytes()
    require(sha(report_bytes) == manifest['files']['analysis/compile-report.json'], 'Compile report hash mismatch')
    require(sha((package / 'candidate/os.ldr').read_bytes()) == manifest['files']['candidate/os.ldr'],
            'Firmware hash mismatch')
    report = json.loads(report_bytes)
    require(report.get('profiling') is True and report.get('benchmark_cases'), 'Missing enabled diagnostic runner')
    identity = dict(manifest_sha256=sha(manifest_bytes), compile_report_sha256=sha(report_bytes),
                    firmware_sha256=manifest['files']['candidate/os.ldr'])
    return manifest, report, identity


def aggregate(captures, expected, identity, name, commit, url):
    """The machine's record from complete runs: each of its runs' median across captures;
    a synth's record is its heaviest run, with the midpoint run, the combined run and
    the heaviest swept setting beside it. Returns the record, the published run's
    per-capture values, the machine's standard case, every run's median by case and
    the positions each capture's combined run used."""
    require(3 <= len(captures) <= 100, 'Collect 3 to 100 independent runs')
    seen, collectors = set(), set()
    own = [c for c in expected if c['name'] == name and c['source'] == 'sdk']
    require(own and 'benchmark' in own[0], 'Machine is not in this diagnostic package')
    case = own[0]
    swept = own[1:]
    require(case['kind'] != 'synth' or swept,
            'A synth record is a control sweep: rebuild the package with --sweep on (the default with profiling)')
    settings = [index for index, c in enumerate(own) if 'setting' in c]
    combined = next((index for index, c in enumerate(own) if c.get('combined')), None)
    require(not swept or (settings and combined is not None), 'Incomplete control sweep in this package')
    values = {index: [] for index in range(len(own))}
    combinations = []
    for capture in captures:
        fingerprint = sha(json.dumps(capture, sort_keys=True).encode())
        require(fingerprint not in seen, 'Do not reuse a capture as another run')
        seen.add(fingerprint)
        require(capture.get('mode') == 'benchmark' and capture.get('package') == identity and
                capture.get('expected_cases') == expected, 'Capture belongs to a different build or workload')
        collectors.add(capture.get('collector_sha256'))
        results = [r for r in decode(capture, expected) if r['machine'] in own]
        for index, result in enumerate(results):
            metric = result['metrics'][case['metric']]
            require(metric['encoded_average'] < 65535, 'Saturated workload; do not publish a CPU number')
            active = not result['insufficient_voice_activity'] and metric['encoded_average'] > 0
            # A swept setting may silence the voice (a level at 0): it is left out, not refused.
            require(active or index in settings, 'Inactive or failed workload; do not publish a CPU number')
            values[index].append(metric['average_budget_percent'] if active else None)
        if swept:
            combinations.append(combined_positions(
                [(own[index]['setting'], results[index]['metrics'][case['metric']]['encoded_average'])
                 for index in settings]))
    require(len(collectors) == 1 and None not in collectors, 'Use the same collector for all runs')
    # A setting silent in every capture is left out; one silent in only some failed there.
    require(all(None not in runs or set(runs) == {None} for runs in values.values()),
            'A swept setting sounded in some runs but not others; collect the runs again')
    medians = {index: round(statistics.median(runs), 6) for index, runs in values.items() if None not in runs}
    require(not swept or any(index in medians for index in settings), 'Every swept setting was silent')
    heaviest = max(medians, key=lambda index: (medians[index], -index))
    measurement = dict(benchmark=BENCHMARKS[case['kind']] if swept else case['benchmark'], commit=commit,
                       firmware_sha256=identity['firmware_sha256'], runs=len(captures),
                       block_percent=medians[heaviest])
    if swept:
        worst = max((index for index in settings if index in medians), key=lambda index: (medians[index], -index))
        measurement.update(midpoint_percent=medians[0], combined_percent=medians[combined],
                           worst_setting=own[worst]['setting'])
    if url is not None:
        measurement['report'] = url
    validate(measurement, case['kind'], commit, legacy=False)
    return (measurement, values[heaviest], case, [(own[index], medians.get(index)) for index in values],
            combinations)


def create(package, paths, name, url, out):
    from . import native, catalog
    manifest, report, identity = package_data(package)
    _, machines, _ = native.configuration(native.package_collection(package), native.package_layout(package))
    machine = next((m for m in machines if m.id == name), None)
    require(machine is not None, 'Unknown package machine')
    # Publication binds the tested source tree, not an arbitrary user-supplied SHA.
    commit = catalog.git('rev-parse', 'HEAD', cwd=machine.root).strip()
    require(not catalog.git('status', '--porcelain', '--untracked-files=all', '--', '.', cwd=machine.root).strip(),
            'Commit the machine before building and profiling it')
    files = machine.files()
    prefix = 'external/' + name + '/'
    actual = {key: sha(path.read_bytes()) for key, path in files.items()}
    require(actual == {k: v for k, v in report['sources'].items() if k.startswith(prefix)},
            'Machine source differs from the measured build')
    for path in files.values():
        catalog.git('ls-files', '--error-unmatch', '--', str(path.relative_to(machine.root)), cwd=machine.root)
    captures = [json.loads(Path(path).read_text()) for path in paths]
    measurement, values, case, runs, combinations = aggregate(captures, report['benchmark_cases'], identity,
                                                              name, commit, url)
    destination = Path(out)
    require(not destination.exists(), 'Use a fresh report directory')
    destination.mkdir(parents=True)
    (destination / 'catalog-cpu.json').write_text(json.dumps({'cpu': measurement}, indent=2) + '\n')
    scope = 'whole voice, including oscillator/filter' if case['kind'] == 'synth' else 'machine render callback only'
    warning = above_recommended(measurement)
    if 'worst_setting' in measurement:
        setting = measurement['worst_setting']
        published = (f"Heaviest of {len(runs)} runs (midpoint, then each control through its positions with the "
                     f"others at their defaults), median of {len(values)} run means each: "
                     f"**{measurement['block_percent']:.3f}%** of the stock 580,352-cycle block budget. "
                     f"Midpoint run: {measurement['midpoint_percent']:.3f}%. Every control at its heaviest "
                     f"position: {measurement['combined_percent']:.3f}%. Heaviest single setting: "
                     f"{position(setting)}.")
        same = all(c == combinations[0] for c in combinations)
        together = (', '.join(map(position, combinations[0])) if same else
                    'positions differ between runs: ' + '; '.join(', '.join(map(position, c)) for c in combinations))
        table = ['| Setting | Median |', '| --- | ---: |']
        for run, median in runs:
            label = case_label(run) + (' (as read from the reports): ' + together if run.get('combined') else '')
            table.append(f'| {label} | ' + ('silent, left out' if median is None else f'{median:.3f}%') + ' |')
        published += '\n\n' + '\n'.join(table)
        limits = 'maximum polyphony or other combinations of control settings. '
    else:
        published = (f"Median of {len(values)} run means: **{measurement['block_percent']:.3f}%** of the stock "
                     f"580,352-cycle block budget. Run means: {', '.join(f'{v:.3f}%' for v in values)}.")
        limits = 'maximum polyphony or a settings sweep. '
    advice = f'**Warning: {warning}.**' if warning else 'Within it.'
    text = (f"# {name}: hardware CPU measurement\n\n"
            f"Machine commit: `{commit}`. Benchmark: `{measurement['benchmark']}`. Scope: {scope}.\n\n"
            f"{published}\n\n"
            f"Recommended: at most {RECOMMENDED_PERCENT}%. {advice}\n\n"
            "This is a synthetic measurement on the USB-MIDI command endpoint, not total device CPU, " + limits +
            "Graphics are excluded. "
            "Callback tests exclude sample preparation, allocation, stock mixing and voice processing; "
            "they include stopwatch-call overhead and may include interrupt time. "
            "See docs/profiling.md for the versioned workloads.\n\n"
            f"Firmware SHA-256: `{identity['firmware_sha256']}`.\n\n"
            f"Compile report SHA-256: `{identity['compile_report_sha256']}`.\n\n"
            "Attribution uses the user-confirmed installed package, expected case order and exact report count; "
            "the device does not attest its firmware hash. Raw captures remain private because they contain device identity.\n")
    if warning:
        print('WARNING: ' + name + ': ' + warning)
    (destination / 'report.md').write_text(text, encoding='utf-8')
    return destination
