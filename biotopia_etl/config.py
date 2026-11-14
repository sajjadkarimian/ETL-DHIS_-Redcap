"""Settings, read from environment variables (see .env.example)."""

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Program:
    """One DHIS2 tracker program and the study arm its encounters belong to."""
    uid: str
    arm: str  # 'intervention' (iCHIS+) or 'control' (iCHIS)


@dataclass(frozen=True)
class Settings:
    database_url: str
    redcap_url: str | None = None
    redcap_token: str | None = None
    dhis2_url: str | None = None
    dhis2_token: str | None = None
    dhis2_username: str | None = None
    dhis2_password: str | None = None
    programs: list[Program] = field(default_factory=list)


# The iCHIS+ program from PWA_iCHISPlus metadata/metadata.json.
DEFAULT_PROGRAMS = 'intervention:vH93guwEMVt'


def parse_programs(text: str) -> list[Program]:
    """'intervention:vH93guwEMVt,control:abc123' -> [Program, Program]"""
    programs = []
    for part in filter(None, (p.strip() for p in text.split(','))):
        arm, _, uid = part.partition(':')
        if not uid or arm not in ('intervention', 'control'):
            raise ValueError(f'DHIS2_PROGRAMS entry {part!r} must look like intervention:<uid> or control:<uid>')
        programs.append(Program(uid=uid, arm=arm))
    return programs


def from_env(env=os.environ) -> Settings:
    if not env.get('DATABASE_URL'):
        raise SystemExit('DATABASE_URL is not set')
    return Settings(
        database_url=env['DATABASE_URL'],
        redcap_url=env.get('REDCAP_API_URL'),
        redcap_token=env.get('REDCAP_API_TOKEN'),
        dhis2_url=(env.get('DHIS2_URL') or '').rstrip('/') or None,
        dhis2_token=env.get('DHIS2_TOKEN'),
        dhis2_username=env.get('DHIS2_USERNAME'),
        dhis2_password=env.get('DHIS2_PASSWORD'),
        programs=parse_programs(env.get('DHIS2_PROGRAMS', DEFAULT_PROGRAMS)),
    )
