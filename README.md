# BIOTOPIA ETL

Pulls BIOTOPIA data from REDCap and DHIS2, removes identifiers, and loads it into a Postgres database that the Superset dashboards at dashboard.ichisplus.eu read.

```
REDCap API ──┐
             ├─> biotopia_etl ─> Postgres (schema biotopia) ─> Superset
DHIS2 API ───┘
```

Superset reads SQL databases only (it needs a DB-API driver and SQLAlchemy dialect per source), so it cannot query the REDCap or DHIS2 APIs directly. This job fills that gap.

Each run replaces the tables in one transaction, so a failed run leaves the previous data in place. Every run is logged in `biotopia.etl_run`.

## What is stored

Names, dates of birth, contact names and free-text comments are dropped in `transform.py` and never reach Postgres. Age is kept in completed months.

| Table | One row per | Source |
| --- | --- | --- |
| `redcap_child` | REDCap record (screened child) | `screen_log`, `initial_assessment`, `day_14_assessment` |
| `dhis2_encounter` | DHIS2 event (clinical encounter) | tracker events + tracked entity attributes |
| `org_unit` | DHIS2 org unit, with ancestor names by level | `/api/organisationUnits` |
| `etl_run` | ETL run | the job itself |

## Superset datasets

| View | Dashboard | Notes |
| --- | --- | --- |
| `v_trial_children`, `v_trial_summary`, `v_recruitment_monthly` | A Trial Operations | CONSORT counts, 14-day follow-up, monthly recruitment per clinic |
| `v_encounters`, `v_public_health_summary` | B THRIVE Public Health | No child, event or org unit IDs |
| `v_ai_evaluation`, `v_ai_summary` | C AI Governance | Restricted. Sensitivity, specificity, false-negative rate with a Wilson 95% interval, override rate |
| `v_outcome_agreement` | data quality | REDCap outcome at initial assessment vs DHIS2 disposition |
| `v_etl_status` | all | Last successful refresh |

The row-level views carry the filter columns (arm, clinic or facility, month, age group, sex, and so on); the `*_summary` views hold the landing-page KPIs as one row.

## Rules agreed with the project lead (3 Nov 2026)

- Every encounter in iCHIS or iCHIS+ is a pneumonia case.
- Positive at Day 14: admitted at initial assessment, OR died, OR presented to another healthcare provider.
- The AI counts as positive only for RED. An override is RED and not referred to hospital.
- Study arm is per clinic.
- Age groups: 2–6, 7–12, 13–23, 24–59 months.

Still open, marked `Open:` in the code:

- The link between REDCap and DHIS2. `v_ai_evaluation` assumes REDCap `participant_id` equals the DHIS2 attribute `BIOTOPIA_CHILD_ID`, and uses each child's first encounter.
- REDCap has no clinic field. Until it does, the clinic comes from the REDCap Data Access Group, if the project uses one per clinic.
- Whether "admitted since initial assessment" also counts as positive. It is stored as `d14_admitted_since` but not used.
- The iCHIS (control) program UID. Add it to `DHIS2_PROGRAMS`.

## Install on the Superset server

```sh
git clone https://github.com/sajjadkarimian/ETL-DHIS_-Redcap.git /opt/biotopia-etl
cd /opt/biotopia-etl
python3 -m venv .venv
.venv/bin/pip install .
cp .env.example .env    # then fill it in; keep it readable by this user only
chmod 600 .env
```

Create a database and two users: one the ETL writes with, and a read-only one for Superset.

```sql
CREATE DATABASE biotopia_analytics;
CREATE USER biotopia_etl WITH PASSWORD '...';
GRANT ALL ON DATABASE biotopia_analytics TO biotopia_etl;
\c biotopia_analytics
CREATE USER superset_reader WITH PASSWORD '...';
-- after the first run has created the schema:
GRANT USAGE ON SCHEMA biotopia TO superset_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA biotopia TO superset_reader;
ALTER DEFAULT PRIVILEGES FOR USER biotopia_etl IN SCHEMA biotopia GRANT SELECT ON TABLES TO superset_reader;
```

Run once by hand, then schedule it (here every hour):

```sh
set -a; . ./.env; set +a; .venv/bin/python -m biotopia_etl run
```

```cron
0 * * * * cd /opt/biotopia-etl && set -a && . ./.env && set +a && .venv/bin/python -m biotopia_etl run >> /var/log/biotopia-etl.log 2>&1
```

In Superset, add a database connection to `biotopia_analytics` as `superset_reader`, then add the views above as datasets. Give Dashboard C's datasets to a restricted role only.

## Try it without real data

```sh
pip install -e '.[dev]'
python -m biotopia_etl synth --out fixtures          # writes fixtures/extract.json
DATABASE_URL=postgresql://localhost/biotopia_test python -m biotopia_etl run --fixtures fixtures
TEST_DATABASE_URL=postgresql://localhost/biotopia_test pytest
```

`synthetic.py` makes REDCap records and DHIS2 events shaped like the real API responses, with fake names. The pipeline tests drop and recreate the `biotopia` schema, so point them at a throwaway database.

## Field maps

- `biotopia_etl/dhis2_fields.csv`: DHIS2 UID to code, copied from `PWA_iCHISPlus` `metadata/mapping.csv`.
- `biotopia_etl/ai_required.json`: the AI model's required inputs, copied from `PWA_iCHISPlus` `src/ai/required.json`. Data completeness is the share of these that are filled.
- REDCap field names come from the BIOTOPIA data dictionary exported on 3 Nov 2026.

Update these files when the DHIS2 metadata or the REDCap forms change.
