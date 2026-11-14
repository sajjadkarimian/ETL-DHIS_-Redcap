"""End-to-end run on synthetic data. Needs a throwaway Postgres database:
TEST_DATABASE_URL=postgresql://postgres@localhost/biotopia_test pytest"""

import json
import os

import psycopg
import pytest

from biotopia_etl import __main__ as cli, config, synthetic

URL = os.environ.get('TEST_DATABASE_URL')
pytestmark = pytest.mark.skipif(not URL, reason='TEST_DATABASE_URL not set')


@pytest.fixture(scope='module')
def db(tmp_path_factory):
    folder = tmp_path_factory.mktemp('fx')
    (folder / 'extract.json').write_text(json.dumps(synthetic.extract(400, seed=7)))
    with psycopg.connect(URL, autocommit=True) as conn:
        conn.execute('DROP SCHEMA IF EXISTS biotopia CASCADE')
    settings = config.Settings(database_url=URL)
    cli.run(settings, folder)
    cli.run(settings, folder)  # a second run replaces, never duplicates
    with psycopg.connect(URL) as conn:
        yield conn


def one(conn, view):
    cur = conn.execute(f'SELECT * FROM biotopia.{view}')
    return dict(zip([c.name for c in cur.description], cur.fetchone()))


def test_consort_boxes_add_up(db):
    a = one(db, 'v_trial_summary')
    other = db.execute("SELECT count(*) FROM biotopia.redcap_child WHERE screen_status NOT IN "
                       "('not_eligible','excluded_other','declined','enrolled')").fetchone()[0]
    assert a['approached'] == 400
    assert a['not_eligible'] + a['declined'] + a['enrolled'] + other == a['approached']
    assert a['d14_done'] <= a['d14_due'] <= a['enrolled']


def test_second_run_does_not_duplicate(db):
    assert db.execute('SELECT count(*) FROM biotopia.redcap_child').fetchone()[0] == 400
    assert db.execute("SELECT count(*) FROM biotopia.etl_run WHERE status = 'success'").fetchone()[0] == 2


def test_confusion_matrix_covers_every_evaluable_child(db):
    c = one(db, 'v_ai_summary')
    assert c['tp'] + c['fn'] + c['fp'] + c['tn'] == c['evaluable'] > 0
    assert c['false_negative_low_pct'] <= c['false_negative_pct'] <= c['false_negative_high_pct']


def test_no_identifiers_reach_postgres(db):
    columns = {r[0] for r in db.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = 'biotopia'")}
    for banned in ('first_name', 'surname', 'date_of_birth', 'name_of_person_to_be_conta'):
        assert banned not in columns
    names = db.execute("SELECT count(*) FROM biotopia.redcap_child WHERE record_id LIKE '%Child%'").fetchone()[0]
    assert names == 0


def test_public_health_view_has_no_ids(db):
    columns = {r[0] for r in db.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'v_encounters'")}
    assert not columns & {'child_id', 'event_id', 'org_unit_id', 'record_id'}
