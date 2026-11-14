"""Reads records from the REDCap BIOTOPIA project through its API."""

import requests


def export_records(url: str, token: str, timeout: int = 120) -> list[dict]:
    """All records, one flat row per record, raw codes (1/0, 1/2/3), with the
    Data Access Group column and each form's <form>_complete status."""
    res = requests.post(url, data={
        'token': token,
        'content': 'record',
        'format': 'json',
        'type': 'flat',
        'rawOrLabel': 'raw',
        'exportDataAccessGroups': 'true',
        'returnFormat': 'json',
    }, timeout=timeout)
    res.raise_for_status()
    return res.json()
