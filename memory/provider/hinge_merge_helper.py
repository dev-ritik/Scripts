import json
from dataclasses import dataclass, field
from typing import List
from typing import Optional

import aiofiles
from pydantic import BaseModel, model_validator, ConfigDict

from provider.merger import MergeItem
from provider.merger import Parser, Merge, MergeStrategy


@dataclass(frozen=True)
class LikeItem:
    timestamp: str
    comment: str | None = None

    def get_unique_key(self) -> str:
        return f"{self.timestamp}_{self.comment}"


@dataclass(frozen=True)
class Message:
    timestamp: str
    body: str

    def get_unique_key(self) -> str:
        return f"{self.timestamp}_{self.body}"


@dataclass
class Conversation(MergeItem):
    likes: List[LikeItem] = field(default_factory=list)
    matches: List[str] = field(default_factory=list)
    messages: List[Message] = field(default_factory=list)

    # Ignoring blocks and we_mets

    def has_likes(self) -> bool:
        return len(self.likes) > 0

    def has_matches(self) -> bool:
        return len(self.matches) > 0

    def has_messages(self) -> bool:
        return len(self.messages) > 0

    def is_same_as(self, other: 'Conversation') -> bool:
        # Conversation is same if any like time or any match time matches
        for match_time in self.matches:
            if match_time in other.matches:
                return True

        other_like_times = {like_item.timestamp for like_item in other.likes}
        for like_item in self.likes:
            if like_item.timestamp in other_like_times:
                return True
        return False

    def is_valid(self) -> bool:
        return self.has_likes() or self.has_matches() or self.has_messages()

    def __str__(self):
        return f"Conversation with {len(self.likes)} likes and {len(self.matches)} matches and {len(self.messages)} messages"

    def merge(self, other: 'Conversation') -> 'Conversation':
        # Implement the logic to merge two Conversation objects
        for match_time in other.matches:
            if match_time not in self.matches:
                print(f"Merging match time {match_time} into conversation")
                self.matches.append(match_time)

        our_unique_likes = {like.get_unique_key() for like in self.likes}
        for like in other.likes:
            if like.get_unique_key() not in our_unique_likes:
                print(f"Merging like {like} into conversation")
                self.likes.append(like)

        our_unique_messages = {message.get_unique_key() for message in self.messages}
        for message in other.messages:
            if message.get_unique_key() not in our_unique_messages:
                print(f"Merging message {message} into conversation")
                self.messages.append(message)

        return self


class HingeParser(Parser):
    DATA_PATH = 'data/hinge'

    def __init__(self, path: str = None):
        if not path:
            path = self.DATA_PATH
        super().__init__(path)

    async def load_raw_data(self) -> List[Conversation]:
        try:
            async with aiofiles.open(f'{self.path}/matches.json', 'r') as f:
                return json.loads(await f.read())
        except FileNotFoundError:
            print("Error reading matches file.")
            return []

    def validate_raw_data(self, raw_data):
        if not isinstance(raw_data, list):
            raise ValueError("Raw data must be a list of conversations.")

        if len(raw_data) == 0:
            raise ValueError("Raw data is empty.")

        for person_data in raw_data:
            if "likes" in person_data or "matches" in person_data or "messages" in person_data:
                # This is our custom formatted dump
                CustomPersonModel.model_validate(person_data)
            else:
                PersonModel.model_validate(person_data)

    def parse_raw_data(self, raw_data) -> List[Conversation]:
        conversations: List[Conversation] = []
        for match in raw_data:
            conversation = Conversation()

            if "likes" in match or "matches" in match or "messages" in match:
                # This is our custom formatted dump
                conversation.likes = [LikeItem(**like) for like in match.get("likes", [])]
                conversation.matches = match.get("matches", [])
                conversation.messages = [Message(**msg) for msg in match.get("messages", [])]
            else:
                for like_data in match.get("like", []):
                    # Timestamp at the top is ignored as per validator, it's a repeat
                    like_items = like_data.get("like", [])
                    for like_item in like_items:
                        like_items_obj = LikeItem(
                            comment=like_item.get("comment"),
                            timestamp=like_item["timestamp"]
                        )
                        conversation.likes.append(like_items_obj)

                for chat_data in match.get("chats", []):
                    conversation.messages.append(
                        Message(
                            timestamp=chat_data["timestamp"],
                            body=chat_data["body"],
                        )
                    )

                for match_data in match.get("match", []):
                    conversation.matches.append(match_data["timestamp"])
            conversations.append(conversation)

        return conversations


class HingeMerge(Merge):
    merge_strategy = MergeStrategy.MERGE
    parser = HingeParser

    def __init__(self, new_path: str):
        super().__init__(new_path)

    async def dump(self, data: List[Conversation], dry_run=True) -> bool:
        file_name = f"{self.parser.DATA_PATH}/matches{'_dry_run' if dry_run else ''}.json"
        try:
            # Convert objects to dictionaries if data elements are custom objects (e.g. dataclasses or Pydantic models)
            # If 'data' is already a list of dicts/primitives, `default=str` or custom serializer can be used.
            async with aiofiles.open(file_name, "w") as f:
                await f.write(
                    json.dumps(
                        data,
                        default=lambda o: (
                            o.__dict__ if hasattr(o, "__dict__") else str(o)
                        ),
                        indent=4,
                    )
                )
            return True
        except Exception as e:
            print(f"Error writing to matches file: {e}")
            return False


class LikeItemModel(BaseModel):
    model_config = ConfigDict(extra='forbid')
    timestamp: str
    comment: str | None = None


class LikeModel(BaseModel):
    model_config = ConfigDict(extra='forbid')
    timestamp: str
    like: list[LikeItemModel]

    @model_validator(mode="after")
    def timestamps_match(self):
        # Not sure if this is necessary, but just in case
        for item in self.like:
            if item.timestamp != self.timestamp:
                raise ValueError("Timestamp mismatch")
        return self


class ChatModel(BaseModel):
    model_config = ConfigDict(extra='forbid')
    timestamp: str
    body: str


class MatchItemModel(BaseModel):
    model_config = ConfigDict(extra='forbid')
    timestamp: str


class PersonModel(BaseModel):
    model_config = ConfigDict(extra='forbid')
    like: list[LikeModel] = []
    chats: list[ChatModel] = []
    match: list[MatchItemModel] = []
    we_met: list[dict] = []
    block: Optional[list] = []

    @model_validator(mode="after")
    def keys_validation(self):
        if self.block:
            if self.like or self.chats or self.match or self.we_met:
                raise ValueError(f"Block data should be the only attribute, {self.model_dump_json(indent=2)}")
            if len(self.block) != 1:
                raise ValueError(
                    f"Block data should be a list of length 1, {self.model_dump_json(indent=2)}"
                )
        elif self.we_met:
            pass
        elif self.like and not self.match:
            if self.chats:
                raise ValueError(f"Chats should not be present without a match, {self.model_dump_json(indent=2)}")
        elif self.match and not self.like:
            pass
        elif not self.like and not self.match:
            raise ValueError(f"Either like or match data is required, {self.model_dump_json(indent=2)}")
        return self


class CustomPersonModel(BaseModel):
    # This class is to validate our own customized dump of Hinge backup
    model_config = ConfigDict(extra='forbid')
    likes: list[LikeItemModel] = []
    messages: list[ChatModel] = []
    matches: list[str] = []

    @model_validator(mode="after")
    def is_valid(self):
        return len(self.likes) > 0 or len(self.messages) > 0 or len(self.matches) > 0
