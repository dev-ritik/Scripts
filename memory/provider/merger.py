from enum import Enum, auto
from typing import List, Optional

from tqdm import tqdm


class SetUnionMerger:

    def __init__(self, key):
        self.key = key

    def merge(self, old_items, new_items):
        merged = {}

        for item in old_items:
            merged[self.key(item)] = item

        for item in new_items:
            merged[self.key(item)] = item

        return sorted(
            merged.values(),
            key=lambda x: self.key(x)
        )


class MergeItem:
    # This is the object that shall be merged
    def get_unique_key(self) -> Optional[str]:
        return None

    def is_same_as(self, other: 'MergeItem') -> Optional[bool]:
        return None

    def merge(self, other: 'MergeItem') -> 'MergeItem':
        raise NotImplementedError

    def is_valid(self) -> bool:
        # Return False to ignore the item
        return True


class Parser:
    DATA_PATH = ''

    def __init__(self, path: Optional[str] = None):
        self.path = path

    async def load_raw_data(self):
        raise NotImplementedError

    def validate_raw_data(self, raw_data):
        raise NotImplementedError

    def parse_raw_data(self, raw_data) -> List[MergeItem]:
        raise NotImplementedError

    async def load(self, validate_raw_data=True) -> List[MergeItem]:
        raw_data = await self.load_raw_data()
        if validate_raw_data:
            self.validate_raw_data(raw_data)
        return self.parse_raw_data(raw_data)

    def validate(self):
        raise NotImplementedError

class MergeStrategy(Enum):
    REPLACE = auto()
    MERGE = auto()

class Merge:
    parser: Parser = Parser
    provider_class = None
    merge_strategy: MergeStrategy = MergeStrategy.REPLACE

    def __init__(self, new_path: str):
        self.new_path = new_path

    def merge_objects(self, old_object, new_object):
        raise NotImplementedError

    async def merge(self, validate_raw_data: bool = False) -> List[MergeItem]:
        old_data_parser = self.parser()
        new_data_parser = self.parser(self.new_path)
        older_data = await old_data_parser.load(validate_raw_data=validate_raw_data)
        new_data = await new_data_parser.load()

        older_data = [od for od in older_data if od.is_valid()]
        new_data = [nd for nd in new_data if nd.is_valid()]

        if self.merge_strategy == MergeStrategy.REPLACE:
            print("Replacing old data with new data as per merge strategy")
            return new_data

        old_item_unique_keys = {item.get_unique_key() for item in older_data}
        new_item_unique_keys = {item.get_unique_key() for item in new_data}

        old_item_unique_keys = old_item_unique_keys - {None}
        new_item_unique_keys = new_item_unique_keys - {None}

        final_data = []
        new_unseen_data_count = 0
        if old_item_unique_keys and new_item_unique_keys:
            # Merge using unique keys
            for new_item in tqdm(new_data, desc="Merging data"):
                if new_item.get_unique_key() in old_item_unique_keys:
                    # Find the corresponding old item
                    old_item = next((item for item in older_data if item.get_unique_key() == new_item.get_unique_key()),
                                    None)
                    if old_item:
                        merged_item = old_item.merge(new_item)
                        final_data.append(merged_item)
                        old_item_unique_keys.remove(old_item.get_unique_key())
                else:
                    new_unseen_data_count += 1
                    final_data.append(new_item)

            if len(old_item_unique_keys) > 0:
                print(f"Warning: {len(old_item_unique_keys)} items in old data not found in new data")
                for old_item in older_data:
                    if old_item.get_unique_key() in old_item_unique_keys:
                        final_data.append(old_item)

        elif not old_item_unique_keys and new_item_unique_keys:
            print("No old data found, using new data as is")
            return new_data
        elif not new_item_unique_keys and old_item_unique_keys:
            print("No new data found, using old data as is")
            return older_data
        else:
            # Merge using is_same_as method
            matched_indices = set()
            for new_item in tqdm(new_data, desc="Merging data"):
                matched = False
                for idx, old_item in enumerate(older_data):
                    if new_item.is_same_as(old_item):
                        merged_item = new_item.merge(old_item)
                        final_data.append(merged_item)
                        matched_indices.add(idx)
                        matched = True
                        break
                if not matched and new_item.is_valid():
                    new_unseen_data_count += 1
                    final_data.append(new_item)

            # Add unmatched items by index check
            if len(matched_indices) < len(older_data):
                print(f"Warning: {len(older_data) - len(matched_indices)} items in old data not found in new data")
                for idx, old_item in enumerate(older_data):
                    if idx not in matched_indices and old_item.is_valid():
                        print(f"Adding unmatched item: {old_item}")
                        final_data.append(old_item)

            print(f"New unseen data count: {new_unseen_data_count}")

        return final_data

    async def dump(self, data: List[MergeItem], dry_run: bool = True) -> bool:
        raise NotImplementedError
