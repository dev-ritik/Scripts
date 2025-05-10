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
