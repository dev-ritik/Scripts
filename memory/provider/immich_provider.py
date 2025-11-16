import os
from collections import defaultdict
from datetime import datetime, timedelta, date
from typing import Dict, List, Tuple, Any

import httpx

from profile import get_immich_ids_from_senders
from provider.base_provider import MemoryProvider, MediaType, Message
from utils import post_with_retries


class ImmichProvider(MemoryProvider):
    NAME = "Immich"

    IMMICH_PATH = 'data/immich'
    IMMICH_BASE_URL = os.environ.get('IMMICH_BASE_URL')
    SEARCH_PAGE_SIZE = 100
    WORKING = True

    def __init__(self):
        if not self.WORKING:
            return

        self.bearer_token = None

    def is_working(self):
        return self.WORKING

    async def get_bearer_token(self) -> Any | None:
        if self.bearer_token:
            return self.bearer_token

        url = f"{self.IMMICH_BASE_URL}/api/auth/login"

        payload = {
            "email": os.environ.get('IMMICH_EMAIL'),
            "password": os.environ.get('IMMICH_PASSWORD')
        }

        response = await post_with_retries(url, payload, headers={}, retries=2, timeout=2)

        if not response or response.status_code != 201:
            print('Immich login failed: ', response.text if response else 'No response')
            self.WORKING = False
            return None

        self.bearer_token = response.json()["accessToken"]
        return self.bearer_token

    async def fetch_on_date(self, on_date: date, ignore_groups: bool = False, senders: List[str] = None) -> List[
        Message]:
        raise NotImplementedError

    async def fetch_dates(self, start_date: date, end_date: date, ignore_groups: bool = False,
                          senders: List[str] = None) -> Dict[datetime.date, List[Message]]:
        results = defaultdict(list)
        if not self.WORKING:
            return results

        print("Starting to fetch from Immich")

        url = f"{self.IMMICH_BASE_URL}/api/search/metadata"
        page = 1

        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': f'Bearer {await self.get_bearer_token()}',
        }

        if not self.WORKING:
            return results

        async with httpx.AsyncClient() as client:
            while True:
                payload = {
                    "takenAfter": start_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "takenBefore": (end_date + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "order": "asc",
                    "page": page,
                    "size": self.SEARCH_PAGE_SIZE,
                }

                if senders:
                    immich_ids = await get_immich_ids_from_senders(senders)
                    if immich_ids:
                        payload["personIds"] = immich_ids
                    else:
                        return results

                response = await post_with_retries(url, payload, headers, retries=2, timeout=2)

                if not response or response.status_code != 200:
                    print('Fetching failed', response.text if response else 'No response')
                    self.WORKING = False
                    return results

                data = response.json()

                for asset in data.get("assets", {}).get("items", []):
                    # results.append({
                    #     "id": asset["id"],
                    #     "name": asset["originalFileName"],
                    #     "originalPath": asset["originalPath"],
                    #     "originalMimeType": asset["originalMimeType"],
                    #     "fileCreatedAt": asset["fileCreatedAt"],
                    #     "fileModifiedAt": asset["fileModifiedAt"],
                    #     "localDateTime": asset["localDateTime"],
                    #     "updatedAt": asset["updatedAt"],
                    #     "duration": asset["duration"],
                    # })
                    _date = datetime.fromisoformat(asset["localDateTime"]).replace(tzinfo=None)
                    results[_date.date()].append(Message(_datetime=_date,
                                                         media_type=MediaType.NON_TEXT,
                                                         provider=self.NAME,
                                                         context={
                                                             "asset_name": asset["originalFileName"],
                                                             "asset_id": asset["id"],
                                                             "mime_type": 'image/webp',
                                                             "new_tab_url": f'{self.IMMICH_BASE_URL}/photos/{asset["id"]}'
                                                         })
                                                 )
                if data.get("assets", {}).get("nextPage") is None:
                    break

                page = data["assets"]['nextPage']

        print("Done fetching from Immich")
        return results

    async def get_timeline_bucket(self, size: str = 'DAY') -> Dict:
        url = f"{self.IMMICH_BASE_URL}/api/timeline/buckets?isArchived=false&size={size}&withPartners=true&withStacked=true"

        headers = {
            'Authorization': f'Bearer {await self.get_bearer_token()}',
        }

        if not self.WORKING:
            return {}

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)

        if response.status_code != 200:
            raise Exception(response.text)

        return response.json()

    async def get_start_end_date(self) -> Tuple[date | None, date | None]:
        timeline_bucket = await self.get_timeline_bucket()
        if not timeline_bucket:
            return None, None

        start_date = datetime.fromisoformat(timeline_bucket[-1]['timeBucket']).replace(tzinfo=None)
        end_date = datetime.fromisoformat(timeline_bucket[0]['timeBucket']).replace(tzinfo=None)
        return start_date.date(), end_date.date()

    async def get_asset(self, asset_id: str) -> List[str] or None:
        url = f"{self.IMMICH_BASE_URL}/api/assets/{asset_id}/thumbnail"

        headers = {
            'Authorization': f'Bearer {await self.get_bearer_token()}',
        }

        if not self.WORKING:
            return None, None

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)

        if response.status_code != 200:
            raise Exception(response.text)
        # with open("test_image.webp", "wb") as f:
        #     f.write(response.content)
        # print(response.headers['Content-Type']) # Should be 'image/webp' or similar
        return response.content, 'image/webp'
