import asyncio
import mimetypes
import os
import re
from datetime import datetime, date
from typing import List, Dict, Optional, Tuple

import aiofiles

from provider.base_provider import MemoryProvider, MessageType, MediaType, Message


class WhatsAppProvider(MemoryProvider):
    NAME = "Whatsapp"
    USER = 'Ritik'
    SYSTEM = 'system'

    WHATSAPP_PATH = 'data/whatsapp'
    WHATSAPP_FILE_NAME_PREFIX = 'WhatsApp Chat with '

    def is_working(self):
        return True

    @staticmethod
    def clean_message(message):
        return message.strip()

    # Try multiple date formats
    DATE_FORMATS = [
        "%d/%m/%Y, %H:%M",  # 31/07/2020, 16:10
        "%m/%d/%y, %I:%M %p",  # 10/24/16, 12:18 AM
    ]

    # WhatsApp line start regex: date, time, dash, then message content
    MSG_START_RE = re.compile(r"^(\d{1,2}/\d{1,2}/\d{2,4}, \d{1,2}:\d{2}(?: [APMapm]{2})?) - (.+)$")
    SENDER_RE = re.compile(r"^(.*?): (.*)$")

    @staticmethod
    def try_parse_date(date_str: str) -> Optional[datetime]:
        for fmt in WhatsAppProvider.DATE_FORMATS:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        return None

    @staticmethod
    async def parse_whatsapp_chat(file_path: str, target_date: date, ignore_groups: bool = False) -> List[Message]:
        # print(file_path)
        chat_entries = []

        media_included = not file_path.endswith('.txt')
        file_name_suffix = file_path.split(WhatsAppProvider.WHATSAPP_FILE_NAME_PREFIX)[1]

        chat_name = file_name_suffix.split('.txt')[0] if not media_included else file_name_suffix
        is_group = False

        folder_path = ''
        if media_included:
            folder_path = file_path
            file_path = os.path.join(folder_path, f'WhatsApp Chat with {chat_name}.txt')

        try:
            async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                lines = await f.readlines()
        except FileNotFoundError:
            return []

        index_datetime_pairs = []
        for i, line in enumerate(lines):
            match = WhatsAppProvider.MSG_START_RE.match(line)
            if match:
                dt = WhatsAppProvider.try_parse_date(match.group(1))
                if dt:
                    index_datetime_pairs.append((i, dt.date()))

        if not index_datetime_pairs:
            return []  # No valid messages at all

        # Early exit if date is out of range
        if target_date and (target_date < index_datetime_pairs[0][1] or target_date > index_datetime_pairs[-1][1]):
            return []

        def binary_search_date(target):
            low, high = 0, len(index_datetime_pairs) - 1
            result_index = None
            while low <= high:
                mid = (low + high) // 2
                mid_date = index_datetime_pairs[mid][1]
                if mid_date < target:
                    low = mid + 1
                elif mid_date > target:
                    high = mid - 1
                else:
                    result_index = mid
                    high = mid - 1  # Move to the earliest match
            return result_index

        if target_date:
            first_index = binary_search_date(target_date)
        else:
            first_index = 0
        if first_index is None:
            return []  # No messages on that date

        def _process_buffer():
            if not message_buffer:
                return
            nonlocal is_group
            context = {}
            media_type = MediaType.TEXT
            text = "\n".join(message_buffer).strip()
            if media_included and '(file attached)' in text:
                media_file_name = text.split('(file attached)')[0].strip()
                media_file_path = os.path.join(folder_path, media_file_name)
                if os.path.exists(media_file_path):
                    context["asset_name"] = media_file_name
                    context["asset_id"] = WhatsAppProvider.generate_asset_id(chat_name, media_file_name)
                    context["mime_type"] = mimetypes.guess_type(media_file_path)[0]
                    context["new_tab_url"] = f'/asset/{WhatsAppProvider.NAME}/{WhatsAppProvider.generate_asset_id(chat_name, media_file_name)}'
                text = text.split('(file attached)')[1].strip()
                # TODO: If text has (file attached) in it, the part before that is the file name and the part after is the actual message. Check Darakshan example
                media_type = MediaType.NON_TEXT if not text else MediaType.MIXED
            elif '<Media omitted>' in text:
                text = '<Added media file>'
            elif text == 'null':
                text = '<View once message>'
            context['edited'] = '<This message was edited>' in text
            if len(chat_entries) < 5 and not is_group and 'created group' in text.lower():
                is_group = True
                if ignore_groups:
                    return
            chat_entries.append(Message(
                current_datetime,
                message_type=MessageType.SENT if current_sender == WhatsAppProvider.USER else MessageType.RECEIVED,
                media_type=media_type,
                message=text,
                sender=current_sender or "System",
                provider=WhatsAppProvider.NAME,
                chat_name=chat_name,
                is_group=is_group,
                context=context)
            )

        start_line = index_datetime_pairs[first_index][0]
        chat_lines = lines[start_line:]
        current_datetime = None
        current_sender = None
        message_buffer = []

        for line in chat_lines:
            line = line.strip()
            match = WhatsAppProvider.MSG_START_RE.match(line)
            if match:
                dt = WhatsAppProvider.try_parse_date(match.group(1))
                if target_date and dt.date() != target_date:
                    break
                _process_buffer()
                current_datetime = dt
                content = match.group(2)
                sender_match = WhatsAppProvider.SENDER_RE.match(content)
                if sender_match:
                    current_sender, first_line = sender_match.groups()
                else:
                    current_sender = None
                    first_line = content
                message_buffer = [first_line]
            else:
                message_buffer.append(line)

        _process_buffer()

        return chat_entries

    async def fetch(self, on_date: datetime, ignore_groups: bool = False) -> List[Message]:
        print("Starting to fetch from WhatsApp")

        memories = []
        tasks = []
        for found in os.listdir(WhatsAppProvider.WHATSAPP_PATH):
            if not found.startswith(WhatsAppProvider.WHATSAPP_FILE_NAME_PREFIX):
                continue

            tasks.append(self.parse_whatsapp_chat(os.path.join(WhatsAppProvider.WHATSAPP_PATH, found), on_date, ignore_groups))

        # Run parsing concurrently
        results = await asyncio.gather(*tasks)

        for chat_list in results:
            memories.extend(chat_list)

        memories.sort(key=lambda memory: memory.datetime)

        print("Done fetching from Whatsapp")
        return memories

    @staticmethod
    def generate_asset_id(chat_name, file_name) -> str:
        return f"{chat_name}___{file_name}"

    @staticmethod
    def get_user_name_file_name(asset_id: str) -> List[str]:
        return asset_id.split('___')

    async def get_asset(self, asset_id: str) -> Tuple[bytes, str]:
        user_name, file_name = WhatsAppProvider.get_user_name_file_name(asset_id)
        media_file_path = os.path.join(WhatsAppProvider.WHATSAPP_PATH, f'{WhatsAppProvider.WHATSAPP_FILE_NAME_PREFIX}{user_name}', file_name)
        if not os.path.exists(media_file_path):
            raise FileNotFoundError(f"{media_file_path} does not exist")

        mime_type, _ = mimetypes.guess_type(media_file_path)
        if mime_type is None:
            raise ValueError("Could not determine MIME type")

        async with aiofiles.open(media_file_path, "rb") as media_file:
            media_data = await media_file.read()
        return media_data, mime_type