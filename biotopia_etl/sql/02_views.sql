-- Views the Superset datasets point at. Recreated on every run.
-- Row-level views (v_trial_children, v_encounters, v_ai_evaluation) let Superset
-- filter by arm, clinic, month, age group and so on; the *_summary views hold
-- the landing-page KPIs as one row each.

-- ------------------------------------------------------------ Dashboard A

CREATE OR REPLACE VIEW biotopia.v_trial_children AS
SELECT
    record_id,
    arm,
    clinic,
    sex,
    age_group,
    screen_status,
    date_trunc('month', date_of_assessment)::date                       AS assessment_month,
    screen_status <> 'not_screened'                                      AS is_screened,
    screen_status IN ('not_eligible', 'excluded_other')                  AS is_not_eligible,
    screen_status = 'declined'                                           AS is_declined,
    enrolled                                                             AS is_enrolled,
    enrolled AND date_of_assessment <= current_date - 14                 AS d14_due,
    enrolled AND date_of_assessment <= current_date - 14 AND d14_complete AS d14_done,
    enrolled AND date_of_assessment <= current_date - 14 AND d14_outcome_known AS outcome_known
FROM biotopia.redcap_child;

CREATE OR REPLACE VIEW biotopia.v_trial_summary AS
SELECT
    count(*) FILTER (WHERE is_screened)       AS approached,
    count(*) FILTER (WHERE is_not_eligible)   AS not_eligible,
    count(*) FILTER (WHERE is_declined)       AS declined,
    count(*) FILTER (WHERE is_enrolled)       AS enrolled,
    8100                                      AS target,
    round(100.0 * count(*) FILTER (WHERE is_enrolled) / 8100, 1) AS recruitment_pct,
    count(*) FILTER (WHERE d14_due)           AS d14_due,
    count(*) FILTER (WHERE d14_done)          AS d14_done,
    round(100.0 * count(*) FILTER (WHERE d14_done) / nullif(count(*) FILTER (WHERE d14_due), 0), 1) AS d14_completion_pct,
    count(*) FILTER (WHERE outcome_known)     AS outcome_known,
    round(100.0 * count(*) FILTER (WHERE outcome_known) / nullif(count(*) FILTER (WHERE d14_due), 0), 1) AS outcome_completeness_pct
FROM biotopia.v_trial_children;

CREATE OR REPLACE VIEW biotopia.v_recruitment_monthly AS
SELECT assessment_month, clinic, arm, count(*) AS enrolled
FROM biotopia.v_trial_children
WHERE is_enrolled
GROUP BY assessment_month, clinic, arm;

-- ------------------------------------------------------------ Dashboard B
-- Aggregated use only: no child ID, event ID or org unit ID.

CREATE OR REPLACE VIEW biotopia.v_encounters AS
SELECT
    e.arm,
    o.name                                    AS facility,
    o.level_2, o.level_3, o.level_4,
    date_trunc('month', e.occurred_at)::date  AS month,
    date_trunc('week', e.occurred_at)::date   AS week,
    e.sex,
    e.age_group,
    e.disposition,
    e.referred,
    e.tx_antibiotic,
    e.tx_antimalarial,
    e.malaria_rdt,
    e.ai_category,
    e.hours_to_server,
    e.hours_to_server <= 72                   AS within_72h,
    round(100.0 * e.required_filled / nullif(e.required_total, 0), 1) AS completeness_pct
FROM biotopia.dhis2_encounter e
LEFT JOIN biotopia.org_unit o ON o.id = e.org_unit_id;

CREATE OR REPLACE VIEW biotopia.v_public_health_summary AS
SELECT
    count(*)                                           AS consultations,
    count(*) FILTER (WHERE referred)                   AS referred,
    count(*) FILTER (WHERE referred IS NOT NULL)       AS referral_known,
    round(100.0 * count(*) FILTER (WHERE referred) / nullif(count(*) FILTER (WHERE referred IS NOT NULL), 0), 1) AS referral_rate_pct,
    count(*) FILTER (WHERE tx_antibiotic)              AS antibiotic,
    count(*) FILTER (WHERE tx_antibiotic IS NOT NULL)  AS antibiotic_known,
    round(100.0 * count(*) FILTER (WHERE tx_antibiotic) / nullif(count(*) FILTER (WHERE tx_antibiotic IS NOT NULL), 0), 1) AS antibiotic_rate_pct,
    round(100.0 * count(*) FILTER (WHERE within_72h) / nullif(count(*) FILTER (WHERE within_72h IS NOT NULL), 0), 1) AS within_72h_pct,
    round(avg(completeness_pct), 1)                    AS completeness_pct
FROM biotopia.v_encounters;

-- ------------------------------------------------------------ Dashboard C
-- Restricted. Each child's first encounter is matched to its REDCap record
-- on participant_id = BIOTOPIA_CHILD_ID (to be confirmed with the project lead).

CREATE OR REPLACE VIEW biotopia.v_ai_evaluation AS
WITH first_encounter AS (
    SELECT DISTINCT ON (child_id) *
    FROM biotopia.dhis2_encounter
    WHERE child_id IS NOT NULL
    ORDER BY child_id, occurred_at
)
SELECT
    e.arm,
    o.name                                    AS facility,
    o.level_2, o.level_3, o.level_4,
    date_trunc('month', e.occurred_at)::date  AS month,
    e.sex,
    e.age_group,
    e.hiv_known,
    e.hiv_test,
    e.muac_cm,
    e.weight_age_z,
    e.ai_model_version,
    e.ai_category,
    e.ai_risk_pct,
    e.ai_scored,
    e.ai_positive,
    e.disposition,
    e.referred,
    e.override,
    r.record_id IS NOT NULL                   AS linked_to_redcap,
    r.d14_outcome_positive                    AS outcome_positive,
    coalesce(e.ai_scored AND r.d14_outcome_known, false) AS evaluable,
    e.ai_positive AND r.d14_outcome_positive             AS tp,
    NOT e.ai_positive AND r.d14_outcome_positive         AS fn,
    e.ai_positive AND NOT r.d14_outcome_positive         AS fp,
    NOT e.ai_positive AND NOT r.d14_outcome_positive     AS tn
FROM first_encounter e
LEFT JOIN biotopia.redcap_child r ON r.participant_id = e.child_id
LEFT JOIN biotopia.org_unit o ON o.id = e.org_unit_id
WHERE e.arm = 'intervention';

-- Wilson 95% interval for a proportion k/n.
CREATE OR REPLACE FUNCTION biotopia.wilson(k bigint, n bigint, upper boolean)
RETURNS numeric LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE WHEN n = 0 THEN NULL ELSE round(100 * (
        (k::numeric / n + 1.96 ^ 2 / (2 * n)
         + CASE WHEN upper THEN 1 ELSE -1 END
           * 1.96 * sqrt(k::numeric / n * (1 - k::numeric / n) / n + 1.96 ^ 2 / (4 * n ^ 2)))
        / (1 + 1.96 ^ 2 / n))::numeric, 1) END
$$;

CREATE OR REPLACE VIEW biotopia.v_ai_summary AS
WITH c AS (
    SELECT
        count(*) FILTER (WHERE ai_scored)  AS scored,
        count(*) FILTER (WHERE evaluable)  AS evaluable,
        count(*) FILTER (WHERE tp)         AS tp,
        count(*) FILTER (WHERE fn)         AS fn,
        count(*) FILTER (WHERE fp)         AS fp,
        count(*) FILTER (WHERE tn)         AS tn,
        count(*) FILTER (WHERE ai_category = 'RED' AND referred IS NOT NULL) AS red,
        count(*) FILTER (WHERE override)   AS overrides,
        count(*)                           AS encounters
    FROM biotopia.v_ai_evaluation
)
SELECT
    encounters, scored, evaluable,
    round(100.0 * evaluable / nullif(encounters, 0), 1)  AS coverage_pct,
    tp, fn, fp, tn,
    round(100.0 * tp / nullif(tp + fn, 0), 1)            AS sensitivity_pct,
    round(100.0 * tn / nullif(tn + fp, 0), 1)            AS specificity_pct,
    round(100.0 * fn / nullif(tp + fn, 0), 1)            AS false_negative_pct,
    biotopia.wilson(fn, tp + fn, false)                  AS false_negative_low_pct,
    biotopia.wilson(fn, tp + fn, true)                   AS false_negative_high_pct,
    red, overrides,
    round(100.0 * overrides / nullif(red, 0), 1)         AS override_pct
FROM c;

-- Quality check: REDCap's outcome at initial assessment vs the DHIS2 disposition.
CREATE OR REPLACE VIEW biotopia.v_outcome_agreement AS
SELECT
    r.initial_outcome AS redcap_outcome,
    e.disposition     AS dhis2_disposition,
    (r.initial_outcome, e.disposition) IN (
        ('discharged_home', 'DISCHARGED_HOME'),
        ('referred_or_admitted', 'REFERRED_HOSPITAL'),
        ('died', 'DIED'))  AS agrees,
    count(*)          AS children
FROM biotopia.redcap_child r
JOIN (SELECT DISTINCT ON (child_id) child_id, disposition
      FROM biotopia.dhis2_encounter WHERE child_id IS NOT NULL
      ORDER BY child_id, occurred_at) e ON e.child_id = r.participant_id
GROUP BY 1, 2, 3;

-- ------------------------------------------------------------ All dashboards

CREATE OR REPLACE VIEW biotopia.v_etl_status AS
SELECT finished_at AS last_success, redcap_rows, dhis2_rows,
       (SELECT status FROM biotopia.etl_run ORDER BY id DESC LIMIT 1) AS last_status
FROM biotopia.etl_run
WHERE status = 'success'
ORDER BY id DESC
LIMIT 1;
