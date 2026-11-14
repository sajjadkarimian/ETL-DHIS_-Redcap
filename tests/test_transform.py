from datetime import date

from biotopia_etl import transform as t
from biotopia_etl.synthetic import CODE_TO_UID


def test_age_groups_follow_the_agreed_bands():
    assert [t.age_group(m) for m in (1, 2, 6, 7, 12, 13, 23, 24, 59, 60)] == [
        'out of range', '2-6 months', '2-6 months', '7-12 months', '7-12 months',
        '13-23 months', '13-23 months', '24-59 months', '24-59 months', 'out of range']
    assert t.age_group(None) is None


def test_months_between_counts_completed_months():
    assert t.months_between(date(2026, 1, 31), date(2026, 3, 30)) == 1
    assert t.months_between(date(2026, 1, 15), date(2026, 3, 15)) == 2


def test_day14_positive():
    assert t.day14_positive(True, None, None) is True          # admitted at initial assessment
    assert t.day14_positive(False, False, None) is True        # died
    assert t.day14_positive(False, True, True) is True         # seen by another provider
    assert t.day14_positive(False, True, False) is False
    assert t.day14_positive(False, True, None) is None         # question not answered


def test_screen_status_follows_the_screening_order():
    s = t.screen_status
    assert s(True, False, None, None, None, False) == 'not_eligible'
    assert s(True, True, False, None, None, False) == 'declined'
    assert s(True, True, True, True, False, False) == 'excluded_other'
    assert s(True, True, True, False, True, True) == 'enrolled'
    assert s(True, True, True, False, True, False) == 'eligible_not_yet_enrolled'
    assert s(False, None, None, None, None, False) == 'not_screened'


def test_redcap_child_drops_identifiers():
    row = {'record_id': '7', 'participant_id': ' BIO-7 ', 'first_name': 'Ama', 'surname': 'Banda',
           'date_of_birth': '2025-01-02', 'name_of_person_to_be_conta': 'Mother',
           'sex_screen_v2': '2', 'does_child_meet_inclusion_v2': '1', 'consent_v2': '1',
           'medical_exclude_v2': '0', 'does_the_participant_satis_v2': '1',
           'date_of_assessment': '2026-10-01', 'calculated_age_in_months': '9.4',
           'what_arm_of_the_study_is_t': '1', 'day_14_assessment_complete': '2',
           'was_the_child_admitted_to_d14': '0', 'is_the_child_still_alive_d14': '1',
           'has_the_child_present2_d14': '1'}
    child = t.redcap_child(row)
    assert child['participant_id'] == 'BIO-7'
    assert child['arm'] == 'intervention' and child['sex'] == 'Female'
    assert child['age_months'] == 9 and child['age_group'] == '7-12 months'
    assert child['screen_status'] == 'enrolled' and child['d14_outcome_positive'] is True
    flat = repr(child)
    for secret in ('Ama', 'Banda', '2025-01-02', 'Mother'):
        assert secret not in flat


def test_merge_redcap_rows_combines_events():
    rows = [{'record_id': '1', 'consent_v2': '1', 'participant_id': ''},
            {'record_id': '1', 'consent_v2': '', 'participant_id': 'BIO-1'}]
    assert t.merge_redcap_rows(rows) == [{'record_id': '1', 'consent_v2': '1', 'participant_id': 'BIO-1'}]


def _event(category, disposition):
    values = {'BIOTOPIA_AI_RISK_CATEGORY': category, 'BIOTOPIA_OUT_DISPOSITION': disposition}
    return {'event': 'e1', 'orgUnit': 'ou', 'occurredAt': '2026-10-01T10:00:00.000',
            'createdAt': '2026-10-02T12:30:00.000',
            'dataValues': [{'dataElement': CODE_TO_UID[c], 'value': v} for c, v in values.items() if v]}


def test_override_is_red_not_referred():
    child = {'BIOTOPIA_DATE_OF_BIRTH': '2025-01-01', 'BIOTOPIA_CHILD_ID': 'BIO-1', 'BIOTOPIA_FIRST_NAME': 'Ama'}
    red_home = t.dhis2_encounter(_event('RED', 'DISCHARGED_HOME'), child, 'intervention')
    assert red_home['override'] is True and red_home['ai_positive'] is True
    assert red_home['hours_to_server'] == 26.5 and red_home['age_months'] == 21
    assert 'Ama' not in repr(red_home)
    assert t.dhis2_encounter(_event('RED', 'REFERRED_HOSPITAL'), child, 'intervention')['override'] is False
    assert t.dhis2_encounter(_event('ORANGE', 'DISCHARGED_HOME'), child, 'intervention')['override'] is False
    unscored = t.dhis2_encounter(_event(None, 'DISCHARGED_HOME'), child, 'control')
    assert unscored['ai_scored'] is False and unscored['override'] is None


def test_org_unit_ancestors_by_level():
    units = [{'id': 'a', 'name': 'Malawi', 'level': 1, 'path': '/a'},
             {'id': 'b', 'name': 'Zomba', 'level': 2, 'path': '/a/b'},
             {'id': 'c', 'name': 'Clinic', 'level': 3, 'path': '/a/b/c'}]
    clinic = t.org_units(units)[2]
    assert (clinic['level_1'], clinic['level_2'], clinic['level_3'], clinic['level_4']) == ('Malawi', 'Zomba', 'Clinic', None)
