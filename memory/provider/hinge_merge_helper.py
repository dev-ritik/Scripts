import csv
import os
from dataclasses import dataclass, field
from typing import List, Tuple, Dict

from init import DATA_DIR
from provider.base_provider import MessageType
from provider.merger import Parser


@dataclass
class LikeItem:
    timestamp: str
    comment: str
    is_rose: bool

    def get_unique_key(self) -> str:
        return f"{self.timestamp}_{self.comment[:10]}"


@dataclass
class Message:
    message_type: MessageType  # Not all received messages are available in backup
    timestamp: str
    body: str | None = None

    # Ignoring is_reply

    def get_unique_key(self) -> str:
        return f"{self.timestamp}_{self.body[:10]}"

    @staticmethod
    def get_message_type(action: str) -> MessageType:
        if action == "sent":
            return MessageType.SENT
        elif action == "received":
            return MessageType.RECEIVED
        else:
            raise ValueError("Message type must be SENT or RECEIVED.")


@dataclass
class Conversation:
    match_id: str
    messages: List[Message] = field(default_factory=list)

    def has_messages(self) -> bool:
        return len(self.messages) > 0

    def __str__(self):
        return f"Conversation with {len(self.messages)} messages"


class HingeParser(Parser):
    DATA_PATH = os.path.join(DATA_DIR, 'hinge')

    def __init__(self, path: str = None):
        if not path:
            path = self.DATA_PATH
        super().__init__(path)

    async def load_data(self):
        results = []
        with open(f"{self.path}/chat_message/chat_message.csv", mode="r", newline="", encoding="utf-8") as file:
            reader = csv.reader(file)
            next(reader)  # Skip the header row (remove if there is no header)
            results.append(list(reader))

        with open(f"{self.path}/match_likes/match_likes.csv", mode="r", newline="", encoding="utf-8") as file:
            reader = csv.reader(file)
            next(reader)  # Skip the header row (remove if there is no header)
            results.append(list(reader))

        with open(f"{self.path}/match_roses/match_roses.csv", mode="r", newline="", encoding="utf-8") as file:
            reader = csv.reader(file)
            next(reader)  # Skip the header row (remove if there is no header)
            results.append(list(reader))

        return results

    def validate_data(self, raw_data):
        if not isinstance(raw_data, list):
            raise ValueError("Raw data must be a list of conversations.")

        if not len(raw_data) == 3:
            raise ValueError("Raw data must have 3 folder's data.")

        # TODO: Validate more

    def parse_data(self, raw_data) -> Tuple[List[Conversation], List[LikeItem]]:
        match_conversations: Dict[str, Conversation] = {}
        like_data: List[LikeItem] = []

        for chat_message in raw_data[0]:
            message = chat_message[0]
            action = chat_message[1]
            timestamp = chat_message[2]
            match_id = chat_message[3]
            # Ignoring has quote

            if match_id not in match_conversations:
                match_conversations[match_id] = Conversation(
                    match_id=match_id,
                    messages=[]
                )

            conversation = match_conversations[match_id]

            conversation.messages.append(Message(
                message_type=Message.get_message_type(action),
                timestamp=timestamp,
                body=message
            ))

        for like_message in raw_data[1]:
            like_data.append(LikeItem(
                timestamp=like_message[0],
                comment=like_message[1],
                is_rose=False
            ))

        for like_message in raw_data[2]:
            like_data.append(LikeItem(
                timestamp=like_message[0],
                comment=like_message[1],
                is_rose=True
            ))
        return list(match_conversations.values()), like_data
