"""Turns raw REDCap and DHIS2 rows into de-identified analysis rows.

Names, dates of birth, contact names and free-text comments are dropped here
and never reach Postgres. Rules agreed with the project lead on 3 Nov 2026
are marked "Agreed:"; anything still open is marked "Open:".
"""

import csv
import json
from datetime import date, datetime
from importlib import resources

# ---------------------------------------------------------------- helpers


def yes_no(value):
    """REDCap yes/no: '1' -> True, '0' -> False, '' -> None."""
    return {'1': True, '0': False}.get(value or '')


def dhis2_bool(value):
    return {'true': True, 'false': False}.get((value or '').lower())


def to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_date(value) -> date | None:
    """REDCap exports dates as YYYY-MM-DD; DD-MM-YYYY is accepted too."""
    if not value:
        return None
    for fmt in ('%Y-%m-%d', '%d-%m-%Y'):
        try:
            return datetime.strptime(value[:10], fmt).date()
        except ValueError:
            pass
    return None


def parse_datetime(value) -> datetime | None:
    """DHIS2 timestamps: 2026-11-01T10:15:00.000 (server local time, no zone)."""
    if not value:
        return None
    return datetime.fromisoformat(value.replace('Z', '+00:00')).replace(tzinfo=None)


def months_between(born: date | None, on: date | None) -> int | None:
    """Completed months of age."""
    if not born or not on:
        return None
    months = (on.year - born.year) * 12 + (on.month - born.month)
    if on.day < born.day:
        months -= 1
    return months


def age_group(months) -> str | None:
    """Agreed: one set for all dashboards, 2-6, 7-12, 13-23, 24-59 months."""
    if months is None:
        return None
    m = int(months)
    if 2 <= m <= 6:
        return '2-6 months'
    if 7 <= m <= 12:
        return '7-12 months'
    if 13 <= m <= 23:
        return '13-23 months'
    if 24 <= m <= 59:
        return '24-59 months'
    return 'out of range'


SEX = {'1': 'Male', '2': 'Female'}
ARM = {'1': 'intervention', '2': 'control'}
INITIAL_OUTCOME = {'1': 'discharged_home', '2': 'referred_or_admitted', '3': 'died'}

# ---------------------------------------------------------------- REDCap


def merge_redcap_rows(rows: list[dict]) -> list[dict]:
    """One row per record_id. A longitudinal project exports one row per event;
    their non-empty values are merged."""
    merged: dict[str, dict] = {}
    for row in rows:
        target = merged.setdefault(row['record_id'], {})
        for key, value in row.items():
            if value not in (None, '') and not target.get(key):
                target[key] = value
    return list(merged.values())


def screen_status(screened, inclusion, consent, medical_exclude, satisfies, enrolled) -> str:
    """One CONSORT box per child, checked in the order the screening log asks."""
    if not screened:
        return 'not_screened'
    if inclusion is False:
        return 'not_eligible'
    if consent is False:
        return 'declined'
    if medical_exclude is True or satisfies is False:
        return 'excluded_other'
    if enrolled:
        return 'enrolled'
    if satisfies is True:
        return 'eligible_not_yet_enrolled'
    return 'screening_incomplete'


def day14_positive(admitted_initial, alive, presented_other):
    """Agreed: positive if admitted at initial assessment, OR died, OR seen by
    another healthcare provider. REDCap asks the last question only when the
    child was not admitted.
    Open: whether 'admitted since initial assessment' should also count."""
    if admitted_initial is True or alive is False or presented_other is True:
        return True
    if admitted_initial is False and alive is True and presented_other is False:
        return False
    return None


SCREEN_FIELDS = ('sex_screen_v2', 'age_screen_v2', 'does_child_meet_inclusion_v2', 'consent_v2')


def redcap_child(row: dict) -> dict:
    inclusion = yes_no(row.get('does_child_meet_inclusion_v2'))
    consent = yes_no(row.get('consent_v2'))
    medical_exclude = yes_no(row.get('medical_exclude_v2'))
    satisfies = yes_no(row.get('does_the_participant_satis_v2'))
    assessed_on = parse_date(row.get('date_of_assessment'))
    screened = any(row.get(f) for f in SCREEN_FIELDS)
    enrolled = satisfies is True and assessed_on is not None

    age = to_float(row.get('calculated_age_in_months')) or to_float(row.get('age')) or to_float(row.get('age_screen_v2'))

    admitted_initial = yes_no(row.get('was_the_child_admitted_to_d14'))
    alive = yes_no(row.get('is_the_child_still_alive_d14'))
    presented_other = yes_no(row.get('has_the_child_present2_d14'))
    positive = day14_positive(admitted_initial, alive, presented_other)

    return {
        'record_id': row['record_id'],
        'participant_id': (row.get('participant_id') or '').strip() or None,
        # Open: REDCap has no clinic field yet. A Data Access Group per clinic works meanwhile.
        'clinic': row.get('redcap_data_access_group') or None,
        'arm': ARM.get(row.get('what_arm_of_the_study_is_t') or ''),
        'sex': SEX.get(row.get('sex') or row.get('sex_screen_v2') or ''),
        'age_months': int(age) if age is not None else None,
        'age_group': age_group(age),
        'screen_status': screen_status(screened, inclusion, consent, medical_exclude, satisfies, enrolled),
        'enrolled': enrolled,
        'date_of_assessment': assessed_on,
        'initial_outcome': INITIAL_OUTCOME.get(row.get('what_happened_to_child_aft') or ''),
        'd14_complete': row.get('day_14_assessment_complete') == '2',
        'd14_admitted_initial': admitted_initial,
        'd14_alive': alive,
        'd14_presented_other': presented_other,
        'd14_admitted_since': yes_no(row.get('day7child_been_admitte_d14')),
        'd14_outcome_positive': positive,
        'd14_outcome_known': positive is not None,
    }


def redcap_children(rows: list[dict]) -> list[dict]:
    return [redcap_child(r) for r in merge_redcap_rows(rows)]

# ---------------------------------------------------------------- DHIS2


def _load_fields() -> dict[str, str]:
    with resources.files(__package__).joinpath('dhis2_fields.csv').open() as f:
        return {r['dhis2_uid']: r['code'] for r in csv.DictReader(f)}


def _load_required() -> list[str]:
    with resources.files(__package__).joinpath('ai_required.json').open() as f:
        return json.load(f)['codes']


UID_TO_CODE = _load_fields()
# Completeness = share of the AI model's required inputs that are filled
# (copied from PWA_iCHISPlus src/ai/required.json).
REQUIRED_CODES = _load_required()


def by_code(values: list[dict], key: str) -> dict[str, str]:
    return {UID_TO_CODE[v[key]]: v.get('value') for v in values if v.get(key) in UID_TO_CODE}


def dhis2_encounter(event: dict, child: dict, arm: str) -> dict:
    v = by_code(event.get('dataValues', []), 'dataElement')
    occurred = parse_datetime(event.get('occurredAt'))
    created = parse_datetime(event.get('createdAt'))
    born = parse_date(child.get('BIOTOPIA_DATE_OF_BIRTH'))
    age = months_between(born, occurred.date() if occurred else None)

    category = v.get('BIOTOPIA_AI_RISK_CATEGORY') or None
    disposition = v.get('BIOTOPIA_OUT_DISPOSITION') or None
    referred = disposition == 'REFERRED_HOSPITAL' if disposition else None

    filled = sum(1 for c in REQUIRED_CODES if (born if c == 'BIOTOPIA_DATE_OF_BIRTH' else v.get(c)) not in (None, ''))

    return {
        'event_id': event['event'],
        'arm': arm,
        'child_id': (child.get('BIOTOPIA_CHILD_ID') or '').strip() or None,
        'org_unit_id': event.get('orgUnit'),
        'occurred_at': occurred,
        'created_at': created,
        'hours_to_server': round((created - occurred).total_seconds() / 3600, 2) if occurred and created else None,
        'sex': child.get('BIOTOPIA_SEX_OPTIONS') or None,
        'age_months': age,
        'age_group': age_group(age),
        'disposition': disposition,
        'referred': referred,
        'tx_antibiotic': dhis2_bool(v.get('BIOTOPIA_TX_ANTIBIOTIC')),
        'tx_antimalarial': dhis2_bool(v.get('BIOTOPIA_TX_ANTIMALARIAL')),
        'malaria_rdt': v.get('BIOTOPIA_TEST_MALARIA_RDT') or None,
        'hiv_known': dhis2_bool(v.get('BIOTOPIA_RF_KNOWN_HIV')),
        'hiv_test': v.get('BIOTOPIA_TEST_HIV_RESULT') or None,
        'muac_cm': to_float(v.get('BIOTOPIA_CA_MUAC')),
        'weight_age_z': to_float(v.get('BIOTOPIA_CA_WEIGHT_AGE_Z')),
        'ai_risk_pct': to_float(v.get('BIOTOPIA_AI_ADMISSION_RISK_PCT')),
        'ai_category': category,
        'ai_model_version': v.get('BIOTOPIA_AI_MODEL_VERSION') or None,
        'ai_scored': category is not None,
        # Agreed: only RED counts as a referral recommendation; an override is RED not referred.
        'ai_positive': category == 'RED' if category else None,
        'override': (category == 'RED' and referred is False) if category and referred is not None else None,
        'required_filled': filled,
        'required_total': len(REQUIRED_CODES),
    }


def dhis2_encounters(events: list[dict], tracked_entities: list[dict], arm: str) -> list[dict]:
    children = {te['trackedEntity']: by_code(te.get('attributes', []), 'attribute') for te in tracked_entities}
    return [dhis2_encounter(e, children.get(e.get('trackedEntity'), {}), arm) for e in events]


def org_units(units: list[dict]) -> list[dict]:
    """Each org unit with the names of its ancestors by level (level_1 = country)."""
    names = {u['id']: u['name'] for u in units}
    rows = []
    for u in units:
        ancestors = [p for p in (u.get('path') or '').split('/') if p]
        row = {'id': u['id'], 'name': u['name'], 'level': u.get('level')}
        for i in range(1, 6):
            row[f'level_{i}'] = names.get(ancestors[i - 1]) if i <= len(ancestors) else None
        rows.append(row)
    return rows
