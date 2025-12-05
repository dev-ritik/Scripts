import asyncio
import mimetypes
import os
import re
from datetime import datetime, date
from typing import List, Optional, Tuple

import aiofiles

from profile import get_regex_from_name
from provider.base_provider import MemoryProvider, MessageType, MediaType, Message


class WhatsAppProvider(MemoryProvider):
    NAME = "Whatsapp"
    USER = 'Ritik'

    WHATSAPP_PATH = 'data/whatsapp'
    WHATSAPP_ANDROID_FILE_NAME_PREFIX = 'WhatsApp Chat with '
    WHATSAPP_IOS_FOLDER_NAME_PREFIX = 'WhatsApp Chat - '

    def is_working(self):
        return True

    @staticmethod
    def clean_message(message):
        return message.strip()

    SUPPORTED_OS = [
        'android',
        'ios'
    ]


    # Try multiple date formats
    DATE_FORMATS_ANDROID = [
        "%d/%m/%Y, %H:%M",  # 31/07/2020, 16:10
        "%m/%d/%y, %I:%M %p",  # 10/24/16, 12:18 AM
    ]

    DATE_FORMATS_IOS = [
        "%d/%m/%y, %I:%M:%S %p",  # "26/09/25, 12:28:21 AM"   # contains U+202F narrow no-break space
    ]

    # WhatsApp line start regex: date, time, dash, then message content
    ANDROID_MSG_START_RE = re.compile(r"^(\d{1,2}/\d{1,2}/\d{2,4}, \d{1,2}:\d{2}(?: [APMapm]{2})?) - (.+)$")
    # Example "[26/09/25, 12:28:21 AM] Sasi Kiran: Woahh"
    IOS_MSG_START_RE = re.compile(
        r'^‎?\[(\d{1,2}/\d{1,2}/\d{2,4},\s+\d{1,2}:\d{2}:\d{2}\s*[APMapm]{2})\] (.+)$')
    SENDER_RE = re.compile(r"^([^:]+):\s*(.*)$")

    @staticmethod
    def try_parse_date(date_str: str, _os: str) -> Optional[datetime]:
        formats = WhatsAppProvider.DATE_FORMATS_IOS if _os == 'ios' else WhatsAppProvider.DATE_FORMATS_ANDROID
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        return None

    @staticmethod
    async def parse_android_chat(file_path: str,
                                  on_date: Optional[date] = None,
                                  start_date: Optional[date] = None,
                                  end_date: Optional[date] = None,
                                  ignore_groups: bool = False,
                                  sender_regexes: List[str] = None,
                                  pattern = None) -> List[Message]:
        chat_entries = []
        _os = 'android'

        media_included = not file_path.endswith('.txt')
        file_name_suffix = file_path.split(WhatsAppProvider.WHATSAPP_ANDROID_FILE_NAME_PREFIX)[1]

        if media_included:
            folder_path = file_path
            chat_name = file_name_suffix
            # In the folder, search for the file starting with WHATSAPP_ANDROID_FILE_NAME_PREFIX
            prefixed = [entry for entry in os.listdir(folder_path) if
                        entry.startswith(WhatsAppProvider.WHATSAPP_ANDROID_FILE_NAME_PREFIX)]
            if len(prefixed) != 1:
                print(
                    f"Expected exactly one file starting with {WhatsAppProvider.WHATSAPP_ANDROID_FILE_NAME_PREFIX}, found {len(prefixed)}")
                return []
            chat_file_path = os.path.join(folder_path, prefixed[0])
        else:
            folder_path = ''
            chat_name = file_name_suffix.split('.txt')[0]
            chat_file_path = file_path

        try:
            async with aiofiles.open(chat_file_path, "r", encoding="utf-8") as f:
                lines = await f.readlines()
        except FileNotFoundError:
            print(f"File not found: {chat_file_path}")
            return []

        index_datetime_pairs = []
        for i, line in enumerate(lines):
            match = WhatsAppProvider.ANDROID_MSG_START_RE.match(line)
            if match:
                dt = WhatsAppProvider.try_parse_date(match.group(1), "android")
                if dt:
                    index_datetime_pairs.append((i, dt.date()))

        if not index_datetime_pairs:
            return []  # No valid messages at all

        is_group = len(lines) >= 2 and 'created group' in lines[1].lower()
        if is_group and ignore_groups:
            return []

        if not is_group and sender_regexes:
            # Skip chat if none of the participants match the provided sender regex patterns in case of DM
            if not MemoryProvider._sender_matched(chat_name, sender_regexes) and not MemoryProvider._sender_matched(
                    WhatsAppProvider.USER, sender_regexes):
                return []

        # Early exit if the date is out of range
        first_date, last_date = index_datetime_pairs[0][1], index_datetime_pairs[-1][1]
        if on_date and (on_date < first_date or on_date > last_date):
            return []
        elif start_date and start_date > last_date:
            return []
        elif end_date and end_date < first_date:
            return []

        def binary_search_on_date(target):
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

        def binary_search_start_date(target):
            """Find the index of the first message on or after the target date."""
            low, high = 0, len(index_datetime_pairs) - 1
            result_index = None
            while low <= high:
                mid = (low + high) // 2
                mid_date = index_datetime_pairs[mid][1]
                if mid_date < target:
                    low = mid + 1
                else:
                    result_index = mid
                    high = mid - 1
            return result_index

        if on_date:
            first_index = binary_search_on_date(on_date)
        elif start_date:
            first_index = binary_search_start_date(start_date)
        else:
            first_index = 0
        if first_index is None:
            return []  # No relevant messages found

        def _process_buffer():
            if not message_buffer:
                return
            if sender_regexes and (not current_sender or not MemoryProvider._sender_matched(current_sender, sender_regexes)):
                return
            nonlocal is_group
            context = {}
            media_type = MediaType.TEXT
            text = "\n".join(message_buffer).strip()
            if "Messages to this chat and calls are now secured with end-to-end encryption. Tap for more info." in text:
                return
            if media_included and '(file attached)' in text:
                media_file_name = text.split('(file attached)')[0].strip()
                media_file_path = os.path.join(folder_path, media_file_name)
                if os.path.exists(media_file_path):
                    context["asset_name"] = media_file_name
                    context["asset_id"] = WhatsAppProvider.generate_asset_id(_os, chat_name, media_file_name)
                    context["mime_type"] = mimetypes.guess_type(media_file_path)[0]
                    context[
                        "new_tab_url"] = f'/asset/{WhatsAppProvider.NAME}/{WhatsAppProvider.generate_asset_id(_os, chat_name, media_file_name)}'
                text = text.split('(file attached)')[1].strip()
                # TODO: If text has (file attached) in it, the part before that is the file name and the part after is the actual message. Check Darakshan example
                media_type = MediaType.NON_TEXT if not text else MediaType.MIXED
            elif '<Media omitted>' in text:
                text = '<Added media file>'
            elif text == 'null':
                text = '<View once message>'

            if '<This message was edited>' in text:
                context['edited'] = True
                text = text.replace('<This message was edited>', '')

            if 'This message was deleted' in text:
                context['deleted'] = True
                text = text.replace('This message was deleted', '')

            if not text and not context:
                return

            if pattern and pattern.search(text) is None:
                return

            chat_entries.append(Message(
                current_datetime,
                message_type=MessageType.SENT if current_sender == WhatsAppProvider.USER else MessageType.RECEIVED,
                media_type=media_type,
                message=text.strip(),
                sender=current_sender or MemoryProvider.SYSTEM,
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
            match = WhatsAppProvider.ANDROID_MSG_START_RE.match(line)
            if match:
                dt = WhatsAppProvider.try_parse_date(match.group(1), "android")
                if on_date and dt.date() != on_date:
                    break
                if start_date and dt.date() < start_date:
                    continue
                elif end_date and dt.date() > end_date:
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

    @staticmethod
    async def parse_ios_chat(folder_path: str,
                             on_date: Optional[date] = None,
                             start_date: Optional[date] = None,
                             end_date: Optional[date] = None,
                             ignore_groups: bool = False,
                             sender_regexes: List[str] = None,
                             pattern=None) -> List[Message]:
        chat_entries = []
        _os = 'ios'

        chat_name = folder_path.split(WhatsAppProvider.WHATSAPP_IOS_FOLDER_NAME_PREFIX)[1]

        chat_file_name = '_chat.txt'
        chat_file_path = os.path.join(folder_path, chat_file_name)

        try:
            async with aiofiles.open(chat_file_path, "r", encoding="utf-8") as f:
                lines = await f.readlines()
        except FileNotFoundError:
            return []

        index_datetime_pairs = []
        for i, line in enumerate(lines):
            match = WhatsAppProvider.IOS_MSG_START_RE.match(line)
            if match:
                dt = WhatsAppProvider.try_parse_date(match.group(1), _os="ios")
                if dt:
                    index_datetime_pairs.append((i, dt.date()))

        if not index_datetime_pairs:
            return []  # No valid messages at all

        is_group = len(lines) >= 2 and 'created this' in lines[1].lower()
        if is_group and ignore_groups:
            return []

        if not is_group and sender_regexes:
            # Skip chat if none of the participants match the provided sender regex patterns in case of DM
            if not MemoryProvider._sender_matched(chat_name, sender_regexes) and not MemoryProvider._sender_matched(
                    WhatsAppProvider.USER, sender_regexes):
                return []

        # Early exit if the date is out of range
        first_date, last_date = index_datetime_pairs[0][1], index_datetime_pairs[-1][1]
        if on_date and (on_date < first_date or on_date > last_date):
            return []
        elif start_date and start_date > last_date:
            return []
        elif end_date and end_date < first_date:
            return []

        def binary_search_on_date(target):
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

        def binary_search_start_date(target):
            """Find the index of the first message on or after the target date."""
            low, high = 0, len(index_datetime_pairs) - 1
            result_index = None
            while low <= high:
                mid = (low + high) // 2
                mid_date = index_datetime_pairs[mid][1]
                if mid_date < target:
                    low = mid + 1
                else:
                    result_index = mid
                    high = mid - 1
            return result_index

        if on_date:
            first_index = binary_search_on_date(on_date)
        elif start_date:
            first_index = binary_search_start_date(start_date)
        else:
            first_index = 0
        if first_index is None:
            return []  # No relevant messages found

        def _process_buffer():
            if not message_buffer:
                return
            if sender_regexes and (
                    not current_sender or not MemoryProvider._sender_matched(current_sender, sender_regexes)):
                return
            nonlocal is_group
            context = {}
            media_type = MediaType.TEXT
            text = "\n".join(message_buffer).strip()
            if "Messages and calls are end-to-end encrypted" in text:
                return
            elif "created this group" in text:
                return
            elif "You were added" in text:
                return
            if '‎<attached: ' in text:
                media_file_name = text.split('‎<attached: ')[1].strip()[:-1]
                media_file_path = os.path.join(folder_path, media_file_name)
                if os.path.exists(media_file_path):
                    context["asset_name"] = media_file_name
                    context["asset_id"] = WhatsAppProvider.generate_asset_id(_os, chat_name, media_file_name)
                    context["mime_type"] = mimetypes.guess_type(media_file_path)[0]
                    context[
                        "new_tab_url"] = f'/asset/{WhatsAppProvider.NAME}/{WhatsAppProvider.generate_asset_id(_os, chat_name, media_file_name)}'
                text = ""  # iOS doesn't give picture captions
                media_type = MediaType.NON_TEXT
            elif '‎image omitted' in text or 'sticker omitted' in text or 'video omitted' in text:
                text = '<Added media file>'
            elif text == 'null':
                # TODO: Verify
                text = '<View once message>'

            if '‎<This message was edited>' in text:
                context['edited'] = True
                text = text.replace('‎<This message was edited>', '')

            if 'This message was deleted' in text:
                # TODO: Verify
                context['deleted'] = True
                text = text.replace('This message was deleted', '')

            if not text and not context:
                return

            if pattern and pattern.search(text) is None:
                return

            chat_entries.append(Message(
                current_datetime,
                message_type=MessageType.SENT if current_sender == WhatsAppProvider.USER else MessageType.RECEIVED,
                media_type=media_type,
                message=text.strip(),
                sender=current_sender or MemoryProvider.SYSTEM,
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
            match = WhatsAppProvider.IOS_MSG_START_RE.match(line)
            if match:
                dt = WhatsAppProvider.try_parse_date(match.group(1), _os)
                if on_date and dt.date() != on_date:
                    break
                if start_date and dt.date() < start_date:
                    continue
                elif end_date and dt.date() > end_date:
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

    async def fetch(self,
                    on_date: Optional[date] = None,
                    start_date: Optional[date] = None,
                    end_date: Optional[date] = None,
                    ignore_groups: bool = False,
                    senders: List[str] = None,
                    search_regex: str = None) -> List[Message]:
        print(f"Starting to fetch from WhatsApp {on_date=} {start_date=} {end_date=}")
        sender_regexes = [await get_regex_from_name(sender) for sender in senders] if senders else None

        memories = []
        tasks = []
        pattern = re.compile(search_regex) if search_regex else None
        for _folder in os.listdir(WhatsAppProvider.WHATSAPP_PATH):
            if _folder not in self.SUPPORTED_OS:
                continue

            base_path = os.path.join(WhatsAppProvider.WHATSAPP_PATH, _folder)
            for found in os.listdir(base_path):
                if _folder == 'android':
                    if not found.startswith(WhatsAppProvider.WHATSAPP_ANDROID_FILE_NAME_PREFIX):
                        continue

                    tasks.append(self.parse_android_chat(os.path.join(base_path, found),
                                                         on_date=on_date,
                                                         start_date=start_date,
                                                         end_date=end_date,
                                                         ignore_groups=ignore_groups,
                                                         sender_regexes=sender_regexes,
                                                         pattern=pattern))
                else:
                    if not found.startswith(WhatsAppProvider.WHATSAPP_IOS_FOLDER_NAME_PREFIX):
                        continue

                    tasks.append(self.parse_ios_chat(os.path.join(base_path, found),
                                                     on_date=on_date,
                                                     start_date=start_date,
                                                     end_date=end_date,
                                                     ignore_groups=ignore_groups,
                                                     sender_regexes=sender_regexes,
                                                     pattern=pattern))

        # Run parsing concurrently
        results = await asyncio.gather(*tasks)

        for chat_list in results:
            memories.extend(chat_list)

        memories.sort(key=lambda memory: memory.datetime)

        print("Done fetching from Whatsapp")
        return memories

    @staticmethod
    def generate_asset_id(_os, chat_name, file_name) -> str:
        return f"{_os}___{chat_name}___{file_name}"

    @staticmethod
    def get_user_name_file_name(asset_id: str) -> List[str]:
        return asset_id.split('___')

    async def get_asset(self, asset_id: str) -> Tuple[bytes, str]:
        _os, user_name, file_name = WhatsAppProvider.get_user_name_file_name(asset_id)
        if _os == 'ios':
            media_file_path = os.path.join(WhatsAppProvider.WHATSAPP_PATH, _os,
                                           f'{WhatsAppProvider.WHATSAPP_IOS_FOLDER_NAME_PREFIX}{user_name}', file_name)
        else:
            media_file_path = os.path.join(WhatsAppProvider.WHATSAPP_PATH, _os,
                                           f'{WhatsAppProvider.WHATSAPP_ANDROID_FILE_NAME_PREFIX}{user_name}',
                                           file_name)
        if not os.path.exists(media_file_path):
            raise FileNotFoundError(f"{media_file_path} does not exist")

        mime_type, _ = mimetypes.guess_type(media_file_path)
        if mime_type is None:
            raise ValueError("Could not determine MIME type")

        async with aiofiles.open(media_file_path, "rb") as media_file:
            media_data = await media_file.read()
        return media_data, mime_type