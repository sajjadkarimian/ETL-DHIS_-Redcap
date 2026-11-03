"""Synthetic REDCap and DHIS2 extracts, shaped like the real API responses,
for testing the pipeline before any real data is collected. All names are fake."""

import random
from datetime import date, datetime, timedelta

from .transform import UID_TO_CODE

CODE_TO_UID = {code: uid for uid, code in UID_TO_CODE.items()}
PROGRAM = 'vH93guwEMVt'
STAGE = 'vkG3IOjOxhg'

ORG_UNITS = [
    {'id': 'MW000000001', 'name': 'Malawi', 'level': 1, 'path': '/MW000000001'},
    {'id': 'ZN000000001', 'name': 'South West Zone', 'level': 2, 'path': '/MW000000001/ZN000000001'},
    {'id': 'DS000000001', 'name': 'Blantyre', 'level': 3, 'path': '/MW000000001/ZN000000001/DS000000001'},
    {'id': 'DS000000002', 'name': 'Zomba', 'level': 3, 'path': '/MW000000001/ZN000000001/DS000000002'},
    {'id': 'CL000000001', 'name': 'Clinic A', 'level': 4, 'path': '/MW000000001/ZN000000001/DS000000001/CL000000001'},
    {'id': 'CL000000002', 'name': 'Clinic B', 'level': 4, 'path': '/MW000000001/ZN000000001/DS000000001/CL000000002'},
    {'id': 'CL000000003', 'name': 'Clinic C', 'level': 4, 'path': '/MW000000001/ZN000000001/DS000000002/CL000000003'},
    {'id': 'CL000000004', 'name': 'Clinic D', 'level': 4, 'path': '/MW000000001/ZN000000001/DS000000002/CL000000004'},
]
# Clinics A and C use iCHIS+, B and D use iCHIS.
CLINICS = {'CL000000001': ('clinic_a', '1'), 'CL000000002': ('clinic_b', '2'),
           'CL000000003': ('clinic_c', '1'), 'CL000000004': ('clinic_d', '2')}


def _uid(rng: random.Random) -> str:
    alphabet = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    return rng.choice(alphabet[:52]) + ''.join(rng.choice(alphabet) for _ in range(10))


def _yn(flag: bool) -> str:
    return '1' if flag else '0'


def extract(children: int = 300, seed: int = 1, today: date | None = None) -> dict:
    rng = random.Random(seed)
    today = today or date.today()
    redcap, events, tracked = [], [], []

    for i in range(1, children + 1):
        clinic_ou = rng.choice(list(CLINICS))
        dag, arm = CLINICS[clinic_ou]
        assessed = today - timedelta(days=rng.randint(0, 120))
        age = rng.randint(1, 62)
        inclusion = 2 <= age <= 59 and rng.random() > 0.1
        consent = rng.random() > 0.12
        medical = rng.random() < 0.03
        satisfies = inclusion and consent and not medical
        row = {'record_id': str(i), 'redcap_data_access_group': dag,
               'sex_screen_v2': rng.choice('12'), 'age_screen_v2': str(age),
               'does_child_meet_inclusion_v2': _yn(inclusion),
               'consent_v2': _yn(consent) if inclusion else '',
               'medical_exclude_v2': _yn(medical) if inclusion and consent else '',
               'does_the_participant_satis_v2': _yn(satisfies) if inclusion and consent else '',
               'screen_log_complete': '2'}
        if satisfies:
            pid = f'BIO-{i:05d}'
            born = assessed - timedelta(days=int(age * 30.44))
            row.update({'participant_id': pid, 'what_arm_of_the_study_is_t': arm,
                        'date_of_assessment': assessed.isoformat(), 'first_name': 'Test', 'surname': f'Child{i}',
                        'date_of_birth': born.isoformat(), 'sex': row['sex_screen_v2'],
                        'calculated_age_in_months': str(age), 'name_of_person_to_be_conta': 'Test Carer',
                        'initial_assessment_complete': '2'})
            sick = rng.random() < 0.15
            red = rng.random() < (0.7 if sick else 0.1)
            referred = rng.random() < (0.8 if red else 0.1)
            disposition = 'REFERRED_HOSPITAL' if referred else ('DIED' if rng.random() < 0.005 else 'DISCHARGED_HOME')
            row['what_happened_to_child_aft'] = {'DISCHARGED_HOME': '1', 'REFERRED_HOSPITAL': '2', 'DIED': '3'}[disposition]
            if (today - assessed).days >= 14 and rng.random() < 0.9:
                admitted = referred and sick
                alive = not (sick and rng.random() < 0.05)
                row.update({'was_the_child_admitted_to_d14': _yn(admitted), 'is_the_child_still_alive_d14': _yn(alive),
                            'has_the_child_present2_d14': '' if admitted else _yn(sick and rng.random() < 0.6),
                            'day7child_been_admitte_d14': '' if admitted else _yn(sick and rng.random() < 0.2),
                            'day_14_assessment_complete': '2'})

            te = _uid(rng)
            tracked.append({'trackedEntity': te, 'orgUnit': clinic_ou, 'attributes': [
                {'attribute': CODE_TO_UID['BIOTOPIA_CHILD_ID'], 'value': pid},
                {'attribute': CODE_TO_UID['BIOTOPIA_FIRST_NAME'], 'value': 'Test'},
                {'attribute': CODE_TO_UID['BIOTOPIA_DATE_OF_BIRTH'], 'value': born.isoformat()},
                {'attribute': CODE_TO_UID['BIOTOPIA_SEX_OPTIONS'], 'value': 'Male' if row['sex'] == '1' else 'Female'},
            ]})
            occurred = datetime.combine(assessed, datetime.min.time()) + timedelta(hours=rng.randint(8, 16))
            created = occurred + timedelta(hours=rng.choice([0.2, 1, 5, 30, 80, 200]))
            values = {
                'BIOTOPIA_OUT_DISPOSITION': disposition,
                'BIOTOPIA_TX_ANTIBIOTIC': rng.choice(['true', 'true', 'false']),
                'BIOTOPIA_CA_RESP_RATE': str(rng.randint(30, 70)),
                'BIOTOPIA_CA_MUAC': str(round(rng.uniform(11, 16), 1)),
            }
            if arm == '1' and rng.random() < 0.95:
                values.update({'BIOTOPIA_AI_RISK_CATEGORY': 'RED' if red else rng.choice(['GREEN', 'ORANGE']),
                               'BIOTOPIA_AI_ADMISSION_RISK_PCT': str(round(rng.uniform(40, 90) if red else rng.uniform(1, 39), 1)),
                               'BIOTOPIA_AI_MODEL_VERSION': 'biotope-rf-2025-11-trial',
                               'BIOTOPIA_AI_INFERENCE_TIME': occurred.isoformat()})
            events.append({'event': _uid(rng), 'program': PROGRAM, 'programStage': STAGE, 'orgUnit': clinic_ou,
                           'trackedEntity': te, 'status': 'COMPLETED',
                           'occurredAt': occurred.isoformat(timespec='milliseconds'),
                           'createdAt': created.isoformat(timespec='milliseconds'),
                           'dataValues': [{'dataElement': CODE_TO_UID[c], 'value': v} for c, v in values.items()],
                           '_arm': 'intervention' if arm == '1' else 'control'})
        redcap.append(row)

    # The real extract has one list per DHIS2 program; here both arms share the iCHIS+ metadata.
    programs = []
    for arm in ('intervention', 'control'):
        arm_events = [{k: v for k, v in e.items() if k != '_arm'} for e in events if e['_arm'] == arm]
        tes = {e['trackedEntity'] for e in arm_events}
        programs.append({'arm': arm, 'events': arm_events, 'trackedEntities': [t for t in tracked if t['trackedEntity'] in tes]})
    return {'redcap': redcap, 'programs': programs, 'organisationUnits': ORG_UNITS}
