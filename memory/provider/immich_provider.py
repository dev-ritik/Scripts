import os
from collections import defaultdict
from datetime import datetime, timedelta, date
from typing import Dict, List

import httpx

from provider.base_provider import MemoryProvider, MediaType
from utils import post_with_retries


class ImmichProvider(MemoryProvider):
    NAME = "immich"

    IMMICH_PATH = 'data/immich'
    IMMICH_BASE_URL = os.environ.get('IMMICH_BASE_URL')
    SEARCH_PAGE_SIZE = 100
    WORKING = True

    def __init__(self):
        if not self.WORKING:
            return

        self.bearer_token = None

    async def get_bearer_token(self):
        url = f"{self.IMMICH_BASE_URL}/api/auth/login"

        payload = {
            "email": os.environ.get('IMMICH_EMAIL'),
            "password": os.environ.get('IMMICH_PASSWORD')
        }

        response = await post_with_retries(url, payload, headers={}, retries=2)

        if not response or response.status_code != 201:
            print('Immich login failed: ', response.text if response else 'No response')
            self.WORKING = False
            return None

        return response.json()["accessToken"]

    async def fetch(self, on_date: date, ignore_groups: bool = False) -> List[Dict]:
        raise NotImplementedError

    async def fetch_dates(self, start_date: date, end_date: date, ignore_groups: bool = False) -> Dict[
        datetime, List[Dict]]:
        results = defaultdict(list)
        if not self.WORKING:
            return results

        print("Starting to fetch from Immich")
        if not self.bearer_token:
            self.bearer_token = await self.get_bearer_token()
            if not self.WORKING:
                return results

        url = f"{self.IMMICH_BASE_URL}/api/search/metadata"
        page = 1

        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': f'Bearer {self.bearer_token}',
        }

        async with httpx.AsyncClient() as client:
            while True:
                payload = {
                    "takenAfter": start_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "takenBefore": (end_date + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "order": "asc",
                    "page": page,
                    "size": self.SEARCH_PAGE_SIZE,
                }

                response = await post_with_retries(url, payload, headers)

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
                    results[_date.date()].append(MemoryProvider.get_data_template(
                        _datetime=_date,
                        media_type=MediaType.NON_TEXT,
                        provider=self.NAME,
                        context={
                            "asset_name": asset["originalFileName"],
                            "asset_id": asset["id"],
                            "mime_type": 'image/webp',
                            "new_tab_url": f'{self.IMMICH_BASE_URL}/photos/{asset["id"]}'
                        }
                    ))
                if data.get("assets", {}).get("nextPage") is None:
                    break

                page = data["assets"]['nextPage']

        print("Done fetching from Immich")
        return results

    async def get_asset(self, asset_id: str) -> List[str] or None:
        url = f"{self.IMMICH_BASE_URL}/api/assets/{asset_id}/thumbnail"

        headers = {
            'Authorization': f'Bearer {self.bearer_token}',
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)

        if response.status_code != 200:
            raise Exception(response.text)
        # with open("test_image.webp", "wb") as f:
        #     f.write(response.content)
        # print(response.headers['Content-Type']) # Should be 'image/webp' or similar
        return response.content, 'image/webp'
