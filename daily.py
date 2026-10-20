"""Unattended daily generation and optional AstrBot delivery."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import sys

import astrbot_delivery
import trending


def existing_report(day_dir, day):
    for manifest_path in sorted((day_dir / 'reports').glob('*/manifest.json')):
        manifest = trending.load(manifest_path)
        if manifest.get('identity', {}).get('day') != day or manifest['identity'].get('publication_policy') != 'no-repeat-v1':
            continue
        report = manifest_path.parent / 'report.md'
        if trending.digest(report.read_bytes()) != manifest['report_sha256']:
            raise trending.BriefingError('archive', 'existing report hash mismatch')
        return report
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root', default=os.environ.get('TRENDING_OUTPUT_ROOT', 'data'))
    parser.add_argument('--timeout', type=trending.positive, default=180)
    parser.add_argument('--backend', choices=('deepseek', 'json'), default='deepseek')
    parser.add_argument('--analysis-file')
    parser.add_argument('--html-file', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    day = dt.datetime.now(trending.ZONE).date().isoformat()
    day_dir = Path(args.output_root).resolve() / day
    try:
        with trending.run_lock(day_dir):
            report = existing_report(day_dir, day)
            if report is None:
                snapshot = trending.collect(day_dir, args.html_file, args.timeout)
                try:
                    report, _ = trending.analyze(snapshot, day_dir, args.backend, args.analysis_file, timeout=args.timeout)
                except trending.BriefingError as exc:
                    if exc.kind == 'no-new-projects':
                        print(json.dumps({'status': 'no-new-projects', 'day': day}))
                        return 0
                    raise
            delivery = astrbot_delivery.deliver(report, day_dir / 'delivery')
        print(json.dumps({'status': 'success', 'report': str(report), 'delivery': delivery}, ensure_ascii=False))
        return 0
    except (trending.BriefingError, astrbot_delivery.DeliveryError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
