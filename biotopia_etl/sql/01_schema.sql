-- Tables the ETL fills. Each run replaces their contents in one transaction.
-- No names, dates of birth or free text are stored.

CREATE SCHEMA IF NOT EXISTS biotopia;

CREATE TABLE IF NOT EXISTS biotopia.etl_run (
    id            serial PRIMARY KEY,
    started_at    timestamptz NOT NULL DEFAULT now(),
    finished_at   timestamptz,
    status        text NOT NULL DEFAULT 'running',  -- running | success | failed
    redcap_rows   integer,
    dhis2_rows    integer,
    error         text
);

CREATE TABLE IF NOT EXISTS biotopia.redcap_child (
    record_id              text PRIMARY KEY,
    participant_id         text,
    clinic                 text,
    arm                    text,
    sex                    text,
    age_months             integer,
    age_group              text,
    screen_status          text NOT NULL,
    enrolled               boolean NOT NULL,
    date_of_assessment     date,
    initial_outcome        text,
    d14_complete           boolean NOT NULL,
    d14_admitted_initial   boolean,
    d14_alive              boolean,
    d14_presented_other    boolean,
    d14_admitted_since     boolean,
    d14_outcome_positive   boolean,
    d14_outcome_known      boolean NOT NULL
);

CREATE TABLE IF NOT EXISTS biotopia.dhis2_encounter (
    event_id          text PRIMARY KEY,
    arm               text NOT NULL,
    child_id          text,
    org_unit_id       text,
    occurred_at       timestamp,
    created_at        timestamp,
    hours_to_server   numeric,
    sex               text,
    age_months        integer,
    age_group         text,
    disposition       text,
    referred          boolean,
    tx_antibiotic     boolean,
    tx_antimalarial   boolean,
    malaria_rdt       text,
    hiv_known         boolean,
    hiv_test          text,
    muac_cm           numeric,
    weight_age_z      numeric,
    ai_risk_pct       numeric,
    ai_category       text,
    ai_model_version  text,
    ai_scored         boolean NOT NULL,
    ai_positive       boolean,
    override          boolean,
    required_filled   integer NOT NULL,
    required_total    integer NOT NULL
);

CREATE TABLE IF NOT EXISTS biotopia.org_unit (
    id       text PRIMARY KEY,
    name     text NOT NULL,
    level    integer,
    level_1  text,
    level_2  text,
    level_3  text,
    level_4  text,
    level_5  text
);
