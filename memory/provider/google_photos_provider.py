import json
import mimetypes
import os
import pickle
import webbrowser
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import List, Dict

import aiofiles
import httpx
import pytz
from anyio import sleep
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

from provider.base_provider import MemoryProvider, MediaType
from utils import post_with_retries


class GooglePhotosProvider(MemoryProvider):
    NAME = "Google Photos"
    WORKING = True
    GOOGLE_PHOTOS_PATH = 'data/google_photos'

    SCOPES = ['https://www.googleapis.com/auth/photoslibrary.readonly.appcreateddata',
              'https://www.googleapis.com/auth/photoslibrary.readonly',
              'https://www.googleapis.com/auth/photospicker.mediaitems.readonly']

    def __init__(self):
        if not self.WORKING:
            return
        self.token = None
        self.metadata_context_by_dates = defaultdict(set)
        self.metadata_context_by_id = defaultdict(dict)
        self.session_ids = {}
        os.makedirs(self.GOOGLE_PHOTOS_PATH, exist_ok=True)
        if not os.path.exists(os.path.join(self.GOOGLE_PHOTOS_PATH, "index.json")):
            print("No index.json file found")
            with open(os.path.join(self.GOOGLE_PHOTOS_PATH, "index.json"), "w") as f:
                json.dump({
                    "sessions": [],
                    "mediaItems": {}
                }, f)
        else:
            with open(os.path.join(self.GOOGLE_PHOTOS_PATH, "index.json")) as f:
                d = json.load(f)
                self.metadata_context_by_id = d.get('mediaItems', {})
                for _id, item in self.metadata_context_by_id.items():
                    item['createTime'] = datetime.fromisoformat(item.get('createTime'))
                    self.metadata_context_by_dates[item['createTime'].date()].add(_id)
                self.session_ids = d.get('sessions', {}) if d else {}

    def is_working(self):
        return self.WORKING

    async def setup(self, create_new_session: bool = False):
        """
        Process the index file and cache the session medias.
        :param create_new_session: If True, a new session will be created. If False, the existing sessions will be processed. Defaults to False.
        :return:
        """
        self.token = self.get_gphotos_token()
        if create_new_session:
            session_id = await self.start_session(self.token)
            self.session_ids[session_id] = "PROCESSING"
            self._save_index_file()

        for session_id, status in self.session_ids.items():
            if status != "PROCESSED":
                status = await self.cache_session(session_id)
                if status:
                    self.session_ids[session_id] = "PROCESSED"
                    self._save_index_file()

    @staticmethod
    def get_gphotos_token():
        creds = None
        token_file = os.path.join(GooglePhotosProvider.GOOGLE_PHOTOS_PATH, "token.pkl")

        # Load existing token if available
        if os.path.exists(token_file):
            with open(token_file, "rb") as token:
                creds = pickle.load(token)

        # If no valid creds, log in
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    os.path.join(GooglePhotosProvider.GOOGLE_PHOTOS_PATH, "credentials.json"),
                    GooglePhotosProvider.SCOPES)
                creds = flow.run_local_server(port=55433)

            # Save creds
            with open(token_file, "wb") as token:
                pickle.dump(creds, token)

        return creds.token

    @staticmethod
    async def get_session_status(token: str, session_id: str):
        """
        Get the status of a session.
        :param token: The access token.
        :param session_id: The session ID.
        :return: The expiry time for the session and if the pictures are available for the session
        """
        url = f"https://photospicker.googleapis.com/v1/sessions/{session_id}"
        headers = {
            'Authorization': f'Bearer {token}'
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)

        if response.status_code != 200:
            print("Session status failed: ", response.text)
            return

        return response.json()['expireTime'], response.json()['mediaItemsSet']

    @staticmethod
    async def start_session(token):
        url = "https://photospicker.googleapis.com/v1/sessions"

        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }

        response = await post_with_retries(url, payload={}, headers=headers)

        session_id = response.json()['id']
        picker_url = response.json()['pickerUri']
        # TODO: Parse expiry time

        print(f"Session ID: {session_id}")
        print(f"Picker URL: {picker_url}")

        webbrowser.open(picker_url)

        while True:
            await sleep(5)

            expiry_time, media_items_set = GooglePhotosProvider.get_session_status(token, session_id)
            if media_items_set:
                return session_id
            else:
                print("Waiting for pictures to be available")

    @staticmethod
    async def get_media_items_for_session(token: str, session_id: str):
        url = f"https://photospicker.googleapis.com/v1/mediaItems?sessionId={session_id}"

        headers = {
            'Authorization': f'Bearer {token}'
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)

        if response.status_code != 200:
            print("Media items failed: ", response.text)
            return None

        return response.json()['mediaItems']

    async def cache_session(self, session_id: str) -> bool:
        expiry_time, media_available = await GooglePhotosProvider.get_session_status(self.token, session_id)
        if not media_available:
            print(f"No media available for session {session_id}")
            return False
        media = await self.get_media_items_for_session(self.token, session_id)
        for media_item in media:
            _id = media_item.get('id')
            mime_type = media_item.get('mediaFile').get('mimeType')
            base_url = media_item.get('mediaFile').get('baseUrl')
            file_name = media_item.get('mediaFile').get('filename')
            file_name = f'{_id}___{file_name}'
            utc_dt = datetime.fromisoformat(media_item.get('createTime').replace('Z', '+00:00'))
            ist_timezone = pytz.timezone('Asia/Kolkata')
            ist_dt = utc_dt.astimezone(ist_timezone)
            _type = media_item.get('type')

            await self.fetch_asset(self.token, base_url, os.path.join(self.GOOGLE_PHOTOS_PATH, file_name), _type)
            self.metadata_context_by_id[_id] = {
                "base_url": base_url,
                "file_name": file_name,
                "mime_type": mime_type,
                "createTime": ist_dt
            }
            self.metadata_context_by_dates[ist_dt.date()].add(_id)

        return True

    def _save_index_file(self):
        for k, v in self.metadata_context_by_id.items():
            v['createTime'] = v['createTime'].isoformat()

        with open(os.path.join(self.GOOGLE_PHOTOS_PATH, "index.json"), "w") as f:
            json.dump({
                "sessions": self.session_ids,
                "mediaItems": self.metadata_context_by_id
            }, f)

    async def fetch_dates(self, start_date: date, end_date: date, ignore_groups: bool = False) -> Dict[
        datetime.date, List[Dict]]:
        results = defaultdict(list)
        if not self.WORKING:
            return results

        print("Starting to fetch from Google Photos")

        current_date = start_date
        while current_date <= end_date:
            item_ids = self.metadata_context_by_dates.get(current_date, set())
            for item_id in item_ids:
                item = self.metadata_context_by_id.get(item_id)
                if not item:
                    continue
                _date = item.get('createTime')
                results[current_date].append(MemoryProvider.get_data_template(
                    _datetime=_date,
                    media_type=MediaType.NON_TEXT,
                    provider=self.NAME,
                    context={
                        "asset_name": item.get('file_name'),
                        "asset_id": item_id,
                        "mime_type": item.get('mime_type'),
                        "new_tab_url": f'/asset/{GooglePhotosProvider.NAME}/{item_id}'
                    }
                ))
            current_date += timedelta(days=1)

        print("Done fetching from Google Photos")
        return results

    async def fetch(self, on_date: date, ignore_groups: bool = False) -> List[Dict]:
        date_assets = await self.fetch_dates(start_date=on_date, end_date=on_date, ignore_groups=ignore_groups)
        return date_assets.get(on_date, []) if date_assets else []

    @staticmethod
    async def fetch_asset(token: str, url: str, file_name: str, _type) -> List[str] or None:
        # Base URLs remain active for 60 minutes: https://developers.google.com/photos/library/guides/access-media-items#base-urls
        headers = {
            'Authorization': f'Bearer {token}',
        }

        if _type == 'PHOTO':
            url += '=d'
        elif _type == 'VIDEO':
            url += '=dv'

        if os.path.exists(file_name):
            # The file is already downloaded
            return

        print(f"Downloading {url} to {file_name}")
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, headers=headers)

            # Handle redirect manually
            if response.status_code in (301, 302, 303, 307, 308):
                redirect_url = response.headers.get("Location")
                if not redirect_url:
                    raise Exception("Redirect response but no Location header")
                # Follow the redirect explicitly
                response = await client.get(redirect_url, headers=headers)

        if response.status_code != 200:
            raise Exception(response.status_code, response.text)

        with open(file_name, "wb") as f:
            f.write(response.content)

    async def get_asset(self, asset_id: str) -> List[str] or None:
        if not self.WORKING:
            return None, None

        if asset_id not in self.metadata_context_by_id:
            print(f"No metadata found for asset {asset_id}")
            return None, None

        file_path = os.path.join(self.GOOGLE_PHOTOS_PATH, self.metadata_context_by_id[asset_id].get('file_name'))
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"{file_path} does not exist")

        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type is None:
            raise ValueError("Could not determine MIME type")

        async with aiofiles.open(file_path, "rb") as media_file:
            media_data = await media_file.read()
        return media_data, mime_type
