import sqlite3
from datetime import datetime, date
from typing import List, Tuple, Optional

from configs import USER
from profile import get_all_imessage_chat_ids_from_senders
from provider.base_provider import MemoryProvider, Message, MediaType, MessageType


class IMessageProvider(MemoryProvider):
    NAME = "iMessage"
    USER = 'Ritik'

    IMESSAGE_PATH = 'data/imessage'
    APPLE_EPOCH = datetime(2001, 1, 1)
    WORKING = True

    def __init__(self):
        if not self.WORKING:
            return

    # ------------------------------
    # Convert human → Apple timestamp
    # Apple epoch = 2001-01-01
    # iMessage stores nanoseconds → multiply seconds by 1e9
    # ------------------------------
    @staticmethod
    def to_apple_time(_datetime: datetime) -> int:
        delta = (_datetime - IMessageProvider.APPLE_EPOCH).total_seconds()
        return int(delta * 1_000_000_000)  # nanoseconds

    def is_working(self):
        return self.WORKING

    @staticmethod
    def _read_apple_length(blob, offset=73):
        """
        Reads Apple-style variable-length length from a blob starting at offset.
        Returns (length, new_offset)
        Example:
            81 c6 00 -> 198
            81 3b 01 -> 315
        """
        first_byte = blob[offset]
        offset += 1

        if first_byte <= 0x7F:
            # Single-byte length
            return first_byte, offset
        else:
            # Multi-byte length
            num_extra_bytes = first_byte & 0x7F  # lower 7 bits
            length_bytes = blob[offset:offset + num_extra_bytes]
            multiplier_bytes = blob[offset + num_extra_bytes:offset + num_extra_bytes + 1]
            offset += 1  # An extra byte 00 follows
            offset += num_extra_bytes

            multiplier = int.from_bytes(multiplier_bytes)
            length = int.from_bytes(length_bytes)
            length = 256 * multiplier + length
            return length, offset

    @staticmethod
    def _decode_attributed_body(blob):
        if not blob:
            return None
        try:
            if int.from_bytes(blob[22:23]) == 25:
                # This is NSMutableAttributedString. Parsing is different. This is infrequent
                constant_stuff_length = 121
            elif int.from_bytes(blob[22:23]) == 18:
                constant_stuff_length = 73
            else:
                raise Exception("UNKNOWN ATTRIBUTED BODY FORMAT")
            variable_text_length, offset = IMessageProvider._read_apple_length(blob, constant_stuff_length)
            text = blob[offset: offset + variable_text_length]
            if text:
                text = text.decode('utf-8').strip().replace('\ufffc', '').replace('\uFFFC', '')
                return text
            else:
                raise Exception("EMPTY ATTRIBUTED BODY")
        except Exception as e:
            print(e)
            raise e

    @staticmethod
    def query_sms_db(query, params):
        conn = sqlite3.connect(f'{IMessageProvider.IMESSAGE_PATH}/sms.db')
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        rows = cur.execute(query, params).fetchall()
        conn.close()

        return rows

    async def fetch(self, on_date: Optional[date] = None,
                    start_date: Optional[date] = None,
                    end_date: Optional[date] = None,
                    ignore_groups: bool = False,
                    senders: List[str] = None) -> List[Message]:
        print("Starting to fetch from iMessage")
        messages = []
        start_ns = self.to_apple_time(datetime.combine(start_date, datetime.min.time()))
        end_ns = self.to_apple_time(datetime.combine(end_date, datetime.max.time()))

        sender_chat_identifiers = await get_all_imessage_chat_ids_from_senders()
        if senders and not USER in senders:
            # Get messages from only the requested senders
            # Since this is admin's own messages, we should get all messages from all senders if admin is in requested senders

            requested_chat_identifiers = {}
            for sender in senders:
                if sender in sender_chat_identifiers:
                    requested_chat_identifiers[sender] = sender_chat_identifiers[sender]
                else:
                    continue
            if not requested_chat_identifiers:
                return []
            sender_chat_identifiers = requested_chat_identifiers

        # Create a reverse mapping of chat_identifier to sender
        chat_identifier_sender = {}
        for sender, chat_identifiers in sender_chat_identifiers.items():
            for chat_identifier in chat_identifiers:
                chat_identifier_sender[chat_identifier] = sender

        chat_identifiers = chat_identifier_sender.keys()

        if len(chat_identifiers) == 0:
            return []
        chat_identifiers = f"('{"','".join(chat_identifiers)}')"

        query = f"""
                SELECT m.ROWID          AS message_id,
                       m.text           AS message_text,
                       m.attributedBody AS attributed_body,
                       m.handle_id,
                       h.id             AS handle_identifier,
                       m.date,
                       m.guid,
                       m.account,
                       c.chat_identifier,
                       datetime(m.date / 1000000000 + strftime('%s', '2001-01-01'), 'unixepoch') AS timestamp,
    m.is_from_me,
    m.service,
    m.cache_has_attachments,
    -- attachment data
    a.ROWID AS attachment_id,
    a.filename AS attachment_filename,
    a.mime_type AS attachment_mime,
    a.transfer_name AS attachment_original_name
                FROM message m
                    LEFT JOIN handle h
                ON m.handle_id = h.ROWID
                    LEFT JOIN message_attachment_join maj
                    ON m.ROWID = maj.message_id
                    LEFT JOIN attachment a
                    ON maj.attachment_id = a.ROWID

-- REQUIRED: restrict to a specific chat
                    JOIN chat_message_join cmj
                    ON m.ROWID = cmj.message_id
                    JOIN chat c
                    ON cmj.chat_id = c.ROWID

                WHERE
                    c.chat_identifier IN {chat_identifiers}
                  AND m.date BETWEEN {start_ns} AND {end_ns}

                ORDER BY
                    m.date ASC;
                """

        rows = IMessageProvider.query_sms_db(query, ())

        for row in rows:
            # print(row['guid'])
            text = row["message_text"] or IMessageProvider._decode_attributed_body(row["attributed_body"])
            if not text:
                # TODO: Add support for attachments
                # TODO: Add support for emoji reactions
                continue
            # print("Timestamp:", row["timestamp"])
            _dt = datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S")
            user_id = row["handle_identifier"] if row["handle_identifier"] and row["handle_identifier"] != 0 else row[
                'chat_identifier']
            if row["is_from_me"] == 1:
                message_type = MessageType.SENT
                sender_name = self.USER
            else:
                message_type = MessageType.RECEIVED
                sender_name = chat_identifier_sender[user_id]

            if senders and sender_name not in senders:
                continue
            # print("Service:", row["service"])
            # print("Has Attachments:", row["cache_has_attachments"])

            # if row["attachment_id"]:
            #     print("  --- Attachment ---")
            #     print("  Attachment ID:", row["attachment_id"])
            #     print("  Filename:", row["attachment_filename"])
            #     print("  MIME:", row["attachment_mime"])
            #     print("  Original Name:", row["attachment_original_name"])

            if not sender_name:
                continue

            messages.append(
                Message(
                    _dt,
                    message_type,
                    text,
                    sender=sender_name,
                    provider=IMessageProvider.NAME,
                    chat_name=sender_name,
                    media_type=MediaType.TEXT,  # TODO: Fix
                    context={},  # TODO: Add more details
                    is_group=False  # TODO: Fix
                )
            )

        messages.sort(key=lambda memory: memory.datetime)
        print("Done fetching from iMessage")
        return messages

    @staticmethod
    def _get_all_chats(ignore_companies=True, imessage_only=False):
        imessage_where_clause = "WHERE service_name = 'iMessage'" if imessage_only else ''
        query = f"SELECT ROWID, chat_identifier from chat {imessage_where_clause}"
        rows = IMessageProvider.query_sms_db(query, ())
        chat_identifiers = []
        for row in rows:
            chat_identifier = row['chat_identifier']
            if ignore_companies:
                if len(chat_identifier) > 2 and chat_identifier[2] == '-':
                    continue
                if chat_identifier[-4:] == 'goog':
                    continue
            chat_identifiers.append(chat_identifier)
            print(row['ROWID'], row['chat_identifier'])
        return chat_identifiers

    async def get_start_end_date(self) -> Tuple[date | None, date | None]:
        sender_chat_identifiers = await get_all_imessage_chat_ids_from_senders()

        # Create a reverse mapping of chat_identifier to sender
        all_chat_identifiers = []
        for sender, chat_identifiers in sender_chat_identifiers.items():
            all_chat_identifiers.extend(chat_identifiers)

        if len(all_chat_identifiers) == 0:
            return None, None

        chat_identifiers = f"('{"','".join(all_chat_identifiers)}')"

        query = f"""
                SELECT MIN(timestamp) AS min_timestamp,
                       MAX(timestamp) AS max_timestamp
                FROM (SELECT datetime(
                                     m.date / 1000000000 + strftime('%s', '2001-01-01'),
                                     'unixepoch'
                             ) AS timestamp
                      FROM message m
                          JOIN chat_message_join cmj
                      ON cmj.message_id = m.ROWID
                          JOIN chat c ON c.ROWID = cmj.chat_id
                      WHERE c.chat_identifier IN {chat_identifiers});
                """

        rows = IMessageProvider.query_sms_db(query, ())
        if not rows or not len(rows) == 1:
            return None, None
        row = rows[0]
        min_timestamp = row['min_timestamp']
        max_timestamp = row['max_timestamp']
        if min_timestamp and max_timestamp:
            min_date = datetime.strptime(min_timestamp, "%Y-%m-%d %H:%M:%S")
            max_date = datetime.strptime(max_timestamp, "%Y-%m-%d %H:%M:%S")
            return min_date.date(), max_date.date()
        return None, None


    async def get_asset(self, asset_id: str) -> List[str] or None:
        pass
