import os
import mimetypes
import re
from datetime import datetime
from typing import List, Dict, Optional, Tuple

from provider.base_provider import MemoryProvider, MessageType, MediaType


class WhatsAppProvider(MemoryProvider):
    NAME = "Whatsapp"
    USER = 'Ritik'
    SYSTEM = 'system'

    WHATSAPP_PATH = 'data/whatsapp'
    WHATSAPP_FILE_NAME_PREFIX = 'WhatsApp Chat with '

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
    def parse_whatsapp_chat(file_path: str, ignore_groups: bool = False) -> List[dict]:
        # print(file_path)
        chat_entries = []

        current_datetime = None
        current_sender = None
        message_buffer = []

        media_included = not file_path.endswith('.txt')
        file_name_suffix = file_path.split(WhatsAppProvider.WHATSAPP_FILE_NAME_PREFIX)[1]

        chat_name = file_name_suffix.split('.txt')[0] if not media_included else file_name_suffix
        is_group = False

        folder_path = ''
        if media_included:
            folder_path = file_path
            file_path = os.path.join(folder_path, f'WhatsApp Chat with {chat_name}.txt')

        def _process_buffer(_message_buffer: List[str], sender: str) -> bool:
            nonlocal is_group
            context = {}
            media_type = MediaType.TEXT
            text = "\n".join(_message_buffer).strip()
            if media_included and '(file attached)' in text:
                media_file_name = text.split('(file attached)')[0].strip()
                media_file_path = os.path.join(folder_path, media_file_name)
                if os.path.exists(media_file_path):
                    context["asset_name"] = media_file_name
                    context["asset_id"] = WhatsAppProvider.generate_asset_id(chat_name, media_file_name)
                    context["mime_type"] = mimetypes.guess_type(media_file_path)[0]
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
                    return False
            chat_entries.append(
                MemoryProvider.get_data_template(current_datetime,
                                                 message_type=MessageType.SENT if sender == WhatsAppProvider.USER else MessageType.RECEIVED,
                                                 media_type=media_type,
                                                 message=text,
                                                 sender=sender or "System",
                                                 provider=WhatsAppProvider.NAME,
                                                 chat_name=chat_name,
                                                 is_group=is_group,
                                                 context=context)
            )
            return True

        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                msg_match = WhatsAppProvider.MSG_START_RE.match(line)

                if msg_match:
                    # Save previous message
                    if current_datetime and message_buffer:
                        if not _process_buffer(message_buffer, current_sender):
                            return chat_entries

                    date_str, content = msg_match.groups()
                    current_datetime = WhatsAppProvider.try_parse_date(date_str)
                    if not current_datetime:
                        # Invalid date → skip line
                        current_sender = None
                        message_buffer = []
                        continue

                    sender_match = WhatsAppProvider.SENDER_RE.match(content)
                    if sender_match:
                        current_sender, first_line = sender_match.groups()
                    else:
                        current_sender = None
                        first_line = content

                    message_buffer = [first_line]
                else:
                    # Continuation of a previous message
                    if message_buffer is not None:
                        message_buffer.append(line)

            # Save the final message
            if current_datetime and message_buffer:
                _process_buffer(message_buffer, current_sender)

        return chat_entries

    def fetch(self, on_date: datetime, ignore_groups: bool = False) -> List[Dict]:
        memories = []
        for found in os.listdir(WhatsAppProvider.WHATSAPP_PATH):
            if not found.startswith(WhatsAppProvider.WHATSAPP_FILE_NAME_PREFIX):
                continue

            chats = self.parse_whatsapp_chat(os.path.join(WhatsAppProvider.WHATSAPP_PATH, found), ignore_groups)

            memories.extend([chat for chat in chats if chat['datetime'].date() == on_date.date()])

        memories.sort(key=lambda memory: memory['datetime'])
        return memories

    @staticmethod
    def generate_asset_id(chat_name, file_name) -> str:
        return f"{chat_name}___{file_name}"

    @staticmethod
    def get_user_name_file_name(asset_id: str) -> List[str]:
        return asset_id.split('___')

    def get_asset(self, asset_id: str) -> Tuple[bytes, str]:
        user_name, file_name = WhatsAppProvider.get_user_name_file_name(asset_id)
        media_file_path = os.path.join(WhatsAppProvider.WHATSAPP_PATH, f'{WhatsAppProvider.WHATSAPP_FILE_NAME_PREFIX}{user_name}', file_name)
        if not os.path.exists(media_file_path):
            raise FileNotFoundError(f"{media_file_path} does not exist")

        mime_type, _ = mimetypes.guess_type(media_file_path)
        if mime_type is None:
            raise ValueError("Could not determine MIME type")

        with open(media_file_path, "rb") as media_file:
            media_data = media_file.read()
            return media_data, mime_type