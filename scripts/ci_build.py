#!/usr/bin/env python3
"""Run the shared GitHub/Cloudflare build and checks; never publish anything."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REGISTRIES = ('content/page-history.json', 'content/weekly-feature-state.json')


def registry_snapshot(root=ROOT):
    return {name: (root / name).read_bytes() if (root / name).is_file() else None
            for name in REGISTRIES}


def require_unchanged_registries(before, root=ROOT):
    after = registry_snapshot(root)
    changed = [name for name in REGISTRIES if before[name] != after[name]]
    if changed:
        raise ValueError('Build changed editorial history: ' + ', '.join(changed)
                         + '. Build locally, review the dates, and commit the updated registries before pushing.')


def run(command):
    print('+ ' + ' '.join(command), flush=True)
    env = {**os.environ, 'AGURI_CI_BUILD': '1', 'PYTHONUTF8': '1'}
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def main():
    run([sys.executable, 'scripts/check_public_source.py'])
    if not (ROOT / 'content/page-history.json').is_file():
        raise ValueError('Commit content/page-history.json before building in CI.')
    run([sys.executable, '-m', 'unittest', 'discover', '-s', 'scripts', '-p', 'test_*.py'])
    node_tests = sorted(path.relative_to(ROOT).as_posix()
                        for path in (ROOT / 'scripts').glob('test_*.mjs'))
    if not node_tests:
        raise ValueError('No Worker/JavaScript tests found.')
    run(['node', '--test', *node_tests])
    before = registry_snapshot()
    run([sys.executable, 'build.py'])
    require_unchanged_registries(before)
    run([sys.executable, 'scripts/check_site.py'])
    run([sys.executable, 'scripts/prepare_cloudflare.py',
         '--repository', 'rn5678/aguri-heritage-resources', '--tag', 'journals-v1',
         '--remote-journals', '--skip-archive', '--upload-method', 'wrangler'])
    print('PASS: tests, editorial dates, site links, and Cloudflare deployment folder verified.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error)) from None
