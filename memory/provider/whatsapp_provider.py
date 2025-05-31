import os
import re
from datetime import datetime
from typing import List, Dict, Optional

from provider.base_provider import MemoryProvider, MessageType


class WhatsAppProvider(MemoryProvider):
    NAME = "Whatsapp"
    USER = 'Ritik'
    SYSTEM = 'system'

    WHATSAPP_PATH = 'data/whatsapp'

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
        chat_entries = []

        current_datetime = None
        current_sender = None
        message_buffer = []

        chat_name = file_path.split('WhatsApp Chat with ')[1].split('.txt')[0]
        is_group = False

        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                msg_match = WhatsAppProvider.MSG_START_RE.match(line)

                if msg_match:
                    # Save previous message
                    if current_datetime and message_buffer:
                        text = "\n".join(message_buffer).strip()
                        if '<Media omitted>' in text:
                            text = '<Added media file>'
                        elif text == 'null':
                            text = '<View once message>'
                        edited = '<This message was edited>' in text
                        if len(chat_entries) < 5 and not is_group and 'created group' in text.lower():
                            is_group = True
                            if ignore_groups:
                                return []
                        chat_entries.append(
                            MemoryProvider.get_data_template(current_datetime,
                                                             message_type=MessageType.SENT if current_sender == WhatsAppProvider.USER else MessageType.RECEIVED,
                                                             message=text,
                                                             sender=current_sender or "System",
                                                             provider=WhatsAppProvider.NAME,
                                                             chat_name=chat_name,
                                                             is_group=is_group,
                                                             context={
                                                                 'edited': edited
                                                             })
                        )

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
                chat_entries.append(
                    MemoryProvider.get_data_template(current_datetime,
                                                     message_type=MessageType.SENT if current_sender == WhatsAppProvider.USER else MessageType.RECEIVED,
                                                     message="\n".join(message_buffer).strip(),
                                                     sender=current_sender or "System",
                                                     provider=WhatsAppProvider.NAME,
                                                     chat_name=chat_name,
                                                     is_group=is_group,
                                                     context={
                                                         'edited': edited
                                                     })
                )

        return chat_entries

    def fetch(self, on_date: datetime, ignore_groups: bool = False) -> List[Dict]:
        memories = []
        for found in os.listdir(WhatsAppProvider.WHATSAPP_PATH):
            if not found.endswith('.txt') or not found.startswith('WhatsApp Chat with '):
                continue

            chats = self.parse_whatsapp_chat(os.path.join(WhatsAppProvider.WHATSAPP_PATH, found), ignore_groups)

            memories.extend([chat for chat in chats if chat['datetime'].date() == on_date.date()])

        memories.sort(key=lambda memory: memory['datetime'])
        return memories
