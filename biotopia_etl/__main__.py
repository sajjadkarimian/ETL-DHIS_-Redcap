"""Command line.

    python -m biotopia_etl run                      # pull from REDCap and DHIS2
    python -m biotopia_etl run --fixtures DIR       # read saved JSON instead
    python -m biotopia_etl synth --out DIR          # write synthetic JSON for testing
"""

import argparse
import json
import logging
import sys
from pathlib import Path

import psycopg

from . import config, load, transform

log = logging.getLogger('biotopia_etl')


def extract_live(settings: config.Settings) -> dict:
    from . import dhis2, redcap
    if not (settings.redcap_url and settings.redcap_token):
        raise SystemExit('REDCAP_API_URL and REDCAP_API_TOKEN are not set')
    if not settings.dhis2_url:
        raise SystemExit('DHIS2_URL is not set')
    client = dhis2.Client(settings.dhis2_url, settings.dhis2_token, settings.dhis2_username, settings.dhis2_password)
    return {
        'redcap': redcap.export_records(settings.redcap_url, settings.redcap_token),
        'programs': [
            {'arm': p.arm, 'events': client.events(p.uid), 'trackedEntities': client.tracked_entities(p.uid)}
            for p in settings.programs
        ],
        'organisationUnits': client.org_units(),
    }


def extract_fixtures(folder: Path) -> dict:
    return json.loads((folder / 'extract.json').read_text())


def transform_all(raw: dict) -> dict:
    encounters = []
    for p in raw['programs']:
        encounters += transform.dhis2_encounters(p['events'], p['trackedEntities'], p['arm'])
    return {
        'redcap_child': transform.redcap_children(raw['redcap']),
        'dhis2_encounter': encounters,
        'org_unit': transform.org_units(raw['organisationUnits']),
    }


def run(settings: config.Settings, fixtures: Path | None) -> None:
    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        with conn.transaction():
            load.create_schema(conn)
        run_id = load.start_run(conn)
        try:
            raw = extract_fixtures(fixtures) if fixtures else extract_live(settings)
            tables = transform_all(raw)
            with conn.transaction():
                for name, rows in tables.items():
                    load.replace_table(conn, name, rows)
        except Exception as exc:
            load.finish_run(conn, run_id, 'failed', error=f'{type(exc).__name__}: {exc}'[:2000])
            raise
        load.finish_run(conn, run_id, 'success', len(tables['redcap_child']), len(tables['dhis2_encounter']))
        log.info('Loaded %d REDCap records and %d DHIS2 encounters',
                 len(tables['redcap_child']), len(tables['dhis2_encounter']))


def main(argv=None) -> None:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    parser = argparse.ArgumentParser(prog='biotopia_etl')
    sub = parser.add_subparsers(dest='command', required=True)
    r = sub.add_parser('run', help='extract, clean and load')
    r.add_argument('--fixtures', type=Path, help='folder holding extract.json, instead of the live APIs')
    s = sub.add_parser('synth', help='write a synthetic extract.json')
    s.add_argument('--out', type=Path, required=True)
    s.add_argument('--children', type=int, default=300)
    s.add_argument('--seed', type=int, default=1)
    args = parser.parse_args(argv)

    if args.command == 'synth':
        from . import synthetic
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / 'extract.json').write_text(json.dumps(synthetic.extract(args.children, args.seed), indent=1))
        log.info('Wrote %s', args.out / 'extract.json')
    else:
        run(config.from_env(), args.fixtures)


if __name__ == '__main__':
    sys.exit(main())
