"""Run the existing briefing pipeline; delivery requires an explicit flag."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
ZONE = dt.timezone(dt.timedelta(hours=8))


def write_status(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    os.replace(temporary, path)


def existing_report(day_dir: Path, day: str) -> Path | None:
    for manifest_path in sorted((day_dir / 'reports').glob('*/manifest.json')):
        manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
        identity = manifest.get('identity', {})
        if identity.get('day') != day or identity.get('publication_policy') != 'no-repeat-v1':
            continue
        report = manifest_path.parent / 'report.md'
        if hashlib.sha256(report.read_bytes()).hexdigest() != manifest['report_sha256']:
            raise RuntimeError(f'report hash mismatch: {report}')
        return report
    return None


def wait_for_generation(day_dir: Path, day: str) -> Path | None:
    deadline = time.monotonic() + 1800
    while (day_dir / 'run.lock').exists():
        report = existing_report(day_dir, day)
        if report is not None:
            return report
        if time.monotonic() >= deadline:
            raise RuntimeError('generation is still running after delivery wait window')
        time.sleep(10)
    return existing_report(day_dir, day)


def run_child(command: list[str], stdout_path: Path, stderr_path: Path) -> dict:
    with stdout_path.open('w', encoding='utf-8') as stdout, stderr_path.open('w', encoding='utf-8') as stderr:
        result = subprocess.run(command, cwd=ROOT, stdout=stdout, stderr=stderr, check=False)
    if result.returncode:
        raise RuntimeError(f'child exit {result.returncode}; inspect {stderr_path}')
    return json.loads(stdout_path.read_text(encoding='utf-8'))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root', type=Path, default=Path(os.getenv('TRENDING_OUTPUT_ROOT', '/data/output')))
    parser.add_argument('--send', action='store_true', help='Deliver the report through Feishu')
    args = parser.parse_args()
    day = dt.datetime.now(ZONE).date().isoformat()
    day_dir = args.output_root.resolve() / day
    state_dir = day_dir / 'automation'
    status_path = state_dir / 'run-status.json'
    state_dir.mkdir(parents=True, exist_ok=True)
    stage = 'discover'
    try:
        write_status(status_path, {'date': day, 'status': 'running', 'stage': stage})
        report = wait_for_generation(day_dir, day) if args.send else existing_report(day_dir, day)
        if report is None:
            stage = 'generation'
            write_status(status_path, {'date': day, 'status': 'running', 'stage': stage})
            command = [sys.executable, '-B', str(ROOT / 'trending.py'), 'run', '--output-dir', str(day_dir), '--timeout', '600']
            try:
                result = run_child(command, state_dir / 'generation.stdout.json', state_dir / 'generation.stderr.log')
            except RuntimeError:
                error = (state_dir / 'generation.stderr.log').read_text(encoding='utf-8', errors='replace')
                if 'all collected repositories have already appeared' in error:
                    write_status(status_path, {'date': day, 'status': 'no-new-projects', 'stage': stage})
                    return 0
                raise
            report = Path(result['report']).resolve()
            if not report.is_relative_to(day_dir) or existing_report(day_dir, day) != report:
                raise RuntimeError('generated report failed path or manifest validation')
        if args.send:
            stage = 'delivery'
            write_status(status_path, {'date': day, 'status': 'running', 'stage': stage, 'report': str(report)})
            command = [sys.executable, '-B', str(ROOT / 'feishu' / 'send_report.py'), '--report', str(report), '--state-dir', str(day_dir / 'delivery')]
            delivery = run_child(command, state_dir / 'feishu.stdout.json', state_dir / 'feishu.stderr.log')
            if delivery.get('status') not in ('sent', 'already_sent'):
                raise RuntimeError('Feishu returned no confirmed delivery status')
            write_status(status_path, {'date': day, 'status': 'success', 'stage': 'complete', 'report': str(report), 'push_status': delivery['status']})
        else:
            write_status(status_path, {'date': day, 'status': 'generated', 'stage': 'complete', 'report': str(report)})
        print(json.dumps({'status': 'success', 'report': str(report), 'sent': args.send}))
        return 0
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        write_status(status_path, {'date': day, 'status': 'failed', 'stage': stage, 'error': str(exc)})
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
