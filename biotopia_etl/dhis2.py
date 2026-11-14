"""Reads events, tracked entities and org units from the DHIS2 tracker API.

Written for DHIS2 2.41 and later (ichisplus.eu runs 2.43.2): list responses
carry their rows under the plural entity name ("events", "trackedEntities").
2.40 used "instances"; both are accepted.
"""

import requests

PAGE_SIZE = 500

EVENT_FIELDS = 'event,program,orgUnit,occurredAt,createdAt,updatedAt,trackedEntity,status,dataValues[dataElement,value]'
TE_FIELDS = 'trackedEntity,orgUnit,attributes[attribute,value]'
OU_FIELDS = 'id,name,level,path'


class Client:
    def __init__(self, base_url: str, token: str | None = None, username: str | None = None,
                 password: str | None = None, timeout: int = 120):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.session.headers['Accept'] = 'application/json'
        if token:
            # Personal access token (DHIS2 2.37+).
            self.session.headers['Authorization'] = f'ApiToken {token}'
        elif username and password:
            self.session.auth = (username, password)
        else:
            raise ValueError('Set DHIS2_TOKEN, or DHIS2_USERNAME and DHIS2_PASSWORD')
        self.timeout = timeout

    def get(self, path: str, params: dict) -> dict:
        res = self.session.get(f'{self.base_url}/api{path}', params=params, timeout=self.timeout)
        res.raise_for_status()
        return res.json()

    def _paged(self, path: str, key: str, params: dict) -> list[dict]:
        rows, page = [], 1
        while True:
            body = self.get(path, {**params, 'page': page, 'pageSize': PAGE_SIZE})
            batch = body.get(key, body.get('instances', []))
            rows.extend(batch)
            if len(batch) < PAGE_SIZE:
                return rows
            page += 1

    def events(self, program: str) -> list[dict]:
        return self._paged('/tracker/events', 'events',
                           {'program': program, 'ouMode': 'ACCESSIBLE', 'fields': EVENT_FIELDS})

    def tracked_entities(self, program: str) -> list[dict]:
        return self._paged('/tracker/trackedEntities', 'trackedEntities',
                           {'program': program, 'ouMode': 'ACCESSIBLE', 'fields': TE_FIELDS})

    def org_units(self) -> list[dict]:
        return self.get('/organisationUnits', {'paging': 'false', 'fields': OU_FIELDS})['organisationUnits']
