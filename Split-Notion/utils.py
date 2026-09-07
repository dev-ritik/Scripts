import random

import requests
from requests.adapters import HTTPAdapter
from urllib3 import Retry


def get_unique_by_key(data, key, keep="first"):
    """
    Returns a list of unique dictionaries from `data`, removing duplicates by `key`.

    Parameters:
        data (list): List of dictionaries.
        key (str): Key to deduplicate by.
        keep (str): "first" or "last" occurrence to keep.

    Returns:
        list: Deduplicated list of dictionaries.
    """
    if keep == "last":
        data = reversed(data)

    seen = set()
    unique = []
    for item in data:
        value = item.get(key)
        if value not in seen:
            seen.add(value)
            unique.append(item)

    return list(reversed(unique)) if keep == "last" else unique


def get_request_headers(base_url=None, origin_url=None):
    rand = random.uniform(0, 1)

    # Adding randomness
    user_agents = [
        "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:86.0) Gecko/20100101 Firefox/86.0",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.90 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 5.1; rv:9.0.1) Gecko/20100101 Firefox/9.0.1",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/60.0.3112.113 Safari/537.36",
    ]

    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "DNT": "1",
        "Sec-Ch-Ua": '"Google Chrome";v="89", "Chromium";v="89", ";Not A Brand";v="99"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "User-Agent": user_agents[int(rand * len(user_agents))],
    }

    if base_url:
        headers["Host"] = base_url
        headers["authority"] = base_url

    if origin_url:
        headers["Referer"] = origin_url
        headers["Origin"] = origin_url

    return headers


def get_scraping_session(base_url=None, origin_url=None):
    headers = get_request_headers(base_url, origin_url)
    _session = requests.Session()

    _session.headers.update(headers)

    # Retries with backoff
    retries = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )

    adapter = HTTPAdapter(max_retries=retries)
    _session.mount("http://", adapter)
    _session.mount("https://", adapter)
    return _session
