import json
import re
from typing import List, Dict

import aiofiles

PROFILE_DATA = {}
NAME_TO_DISPLAY_NAME = {}
NON_IDENTIFIED_NAMES = set()


async def get_profile_json():
    global PROFILE_DATA
    if PROFILE_DATA:
        return PROFILE_DATA

    try:
        async with aiofiles.open('data/profile.json', 'r') as f:
            profile_data_list = json.loads(await f.read())
            for profile_data in profile_data_list:
                PROFILE_DATA[profile_data['display_name']] = profile_data
    except FileNotFoundError:
        pass
    return PROFILE_DATA


def is_sender_profile(profile_data, name, use_regex=False):
    if not profile_data:
        return False

    if profile_data["display_name"].lower() == name.lower():
        return True

    if use_regex and profile_data.get('name_regex'):
        # Return true if name regex matches name
        pattern = profile_data.get('name_regex')
        # Compile the regex pattern if it's a string, then match
        if isinstance(pattern, str):
            return bool(re.match(pattern, name))
        # If it's already a compiled pattern, use it directly
        return bool(pattern.match(name))

    return False


async def get_user_profile_from_name(name, use_regex=False):
    return next(
        (profile_data for profile_data in (await get_profile_json()).values() if
         is_sender_profile(profile_data, name, use_regex=use_regex)),
        None)


async def get_user_dp(name, use_regex=False):
    global NAME_TO_DISPLAY_NAME
    global NON_IDENTIFIED_NAMES

    display_name = await get_display_name_from_name(name, use_regex=use_regex)
    if not display_name:
        return None

    user_profile = (await get_profile_json()).get(display_name)
    return f'data/dp/{user_profile["dp"]}' if user_profile else None


async def get_display_name_from_name(name, use_regex=False):
    global NAME_TO_DISPLAY_NAME
    global NON_IDENTIFIED_NAMES

    if name in NON_IDENTIFIED_NAMES:
        return None

    if name in NAME_TO_DISPLAY_NAME:
        return NAME_TO_DISPLAY_NAME[name]

    user_profile = await get_user_profile_from_name(name, use_regex=use_regex)
    if user_profile:
        NAME_TO_DISPLAY_NAME[name] = user_profile['display_name']

    return NAME_TO_DISPLAY_NAME.get(name)

async def get_regex_from_name(_name):
    user_profile = await get_user_profile_from_name(_name)
    if not user_profile:
        raise ValueError("User not found")
    return user_profile.get('name_regex')


async def get_immich_ids_from_senders(senders: List[str]) -> List[str]:
    profile_json = await get_profile_json()
    immich_ids = []
    for sender in senders:
        if sender not in profile_json:
            continue
        user_profile = profile_json[sender]
        immich_id = user_profile.get('provider_details', {}).get('immich', {}).get('person_id')
        if immich_id:
            immich_ids.append(immich_id)
    return immich_ids


async def get_all_imessage_chat_ids_from_senders() -> Dict[str, list]:
    profile_json = await get_profile_json()
    chat_identifiers = {}
    for sender, user_profile in profile_json.items():
        chat_identifier: list = user_profile.get('provider_details', {}).get('imessage', {}).get('chat_identifier', [])
        if chat_identifier:
            chat_identifiers[sender] = chat_identifier
    return chat_identifiers
