#!/usr/bin/env python3
"""OP-XY SDK commands. Local builds and checks only; no device operations."""
import sys

COMMANDS = '''Commands:
  check     Contributor checks: python sdk.py check [--help]
  preview   Browser audition build: python sdk.py preview --engine fm2op --out local/preview-001
  new       New local machine: python sdk.py new --id mymachine --name "My Machine" --out local/mymachine
  compile   Native module only: python sdk.py compile --help
  build     Native firmware package for the curated collection: python sdk.py build --help
  verify    Rebuild and compare a native package: python sdk.py verify --help
  kit       Browser builder export: python sdk.py kit --help
  doctor    Check tools: python sdk.py doctor --preview | --toolchain <dir>
Preview server: python tools/serve_harness.py --preview local/preview-001'''

if __name__ == '__main__':
    command, argv = (sys.argv[1], sys.argv[2:]) if len(sys.argv) > 1 else (None, [])
    if command in ('compile', 'build', 'verify'):
        from opxy_sdk.native import main
        raise SystemExit(main(argv, command))
    if command == 'new':
        from opxy_sdk.custom_preview import main
        raise SystemExit(main(argv))
    if command == 'kit':
        from opxy_sdk.browser_kit import main
        raise SystemExit(main(argv))
    if command == 'preview':
        from opxy_sdk.preview import main
        raise SystemExit(main(argv))
    if command == 'check':
        from opxy_sdk.checks import main
        raise SystemExit(main(argv))
    if command == 'doctor':
        import argparse
        from opxy_sdk.pipeline import host_platform, tool_paths
        parser = argparse.ArgumentParser(prog='sdk.py doctor')
        kind = parser.add_mutually_exclusive_group(required=True)
        kind.add_argument('--toolchain')
        kind.add_argument('--preview', action='store_true', help='Check Python, NumPy, Node and actual WASM compilation')
        parser.add_argument('--cxx', default='clang++', help='Clang++ for --preview')
        args = parser.parse_args(argv)
        if args.preview:
            from opxy_sdk.preview_doctor import check
            try:
                raise SystemExit(check(args.cxx))
            except (ValueError, OSError) as error:
                parser.exit(1, 'FAIL: ' + str(error) + '\n')
        try:
            tool_paths(args.toolchain)
        except (ValueError, KeyError) as error:
            parser.exit(1, 'FAIL: ' + str(error) + '\n')
        print(f'PASS: pinned Blackfin tools for {host_platform()}; no device operations')
        raise SystemExit(0)
    print(COMMANDS)
    raise SystemExit(0 if command in (None, '--help', '-h') else 2)
