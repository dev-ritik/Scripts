import json
import os
from datetime import datetime, timedelta
from typing import Dict, List

import requests
from black.trans import defaultdict

from provider.base_provider import MemoryProvider, MessageType


class ImmichProvider(MemoryProvider):
    NAME = "immich"

    IMMICH_PATH = 'data/immich'
    IMMICH_BASE_URL = os.environ.get('IMMICH_BASE_URL')
    SEARCH_PAGE_SIZE = 100
    WORKING = True

    def __init__(self):
        if not self.WORKING:
            return

        url = f"{self.IMMICH_BASE_URL}/api/auth/login"

        payload = json.dumps({
            "email": os.environ.get('IMMICH_EMAIL'),
            "password": os.environ.get('IMMICH_PASSWORD')
        })
        headers = {
            'Content-Type': 'application/json',
        }

        try:
            response = requests.request("POST", url, headers=headers, data=payload)
        except Exception as e:
            print(f"Immich login failed: {e}")
            self.WORKING = False
            return

        if response.status_code != 201:
            print('Immich login failed: ', response.text)
            self.WORKING = False
            return

        self.bearer_token = response.json()["accessToken"]

    def fetch(self, on_date: datetime, ignore_groups: bool = False) -> List[Dict]:
        pass

    def fetch_dates(self, start_date: datetime, end_date: datetime, ignore_groups: bool = False) -> Dict[
        datetime, List[Dict]]:
        print(start_date, end_date, ignore_groups, self.WORKING)
        results = defaultdict(list)
        if not self.WORKING:
            return results

        url = f"{self.IMMICH_BASE_URL}/api/search/metadata"
        page = 1

        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': f'Bearer {self.bearer_token}',
        }

        while True:
            payload = json.dumps({
                "takenAfter": start_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "takenBefore": (end_date + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "order": "asc",
                "page": page,
                "size": self.SEARCH_PAGE_SIZE,
            })

            response = requests.post(url, headers=headers, data=payload)

            if response.status_code != 200:
                print('Fetching failed', response.text)
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
                    message_type=MessageType.IMAGE if asset["originalMimeType"].startswith(
                        "image/") else MessageType.VIDEO,
                    provider=self.NAME,
                    context={
                        "asset_name": asset["originalFileName"],
                        "asset_id": asset["id"]
                    }
                ))
            if data.get("assets", {}).get("nextPage") is None:
                break

            page = data["assets"]['nextPage']

        return results

    def get_asset(self, asset_id: str) -> str:
        url = f"{self.IMMICH_BASE_URL}/api/assets/{asset_id}/thumbnail"

        payload = {}
        headers = {
            'Authorization': f'Bearer {self.bearer_token}',
        }

        response = requests.request("GET", url, headers=headers, data=payload)
        if response.status_code != 200:
            raise Exception(response.text)
        with open("test_image.webp", "wb") as f:
            f.write(response.content)
        print(response.headers['Content-Type'])  # Should be 'image/webp' or similar
        return response.content
