import argparse
import json
import os
import time
from datetime import datetime, timedelta
from typing import Optional

import dotenv
import requests
from dateutil import parser, tz
from requests import HTTPError
from tqdm import tqdm

SPLIT_LIMIT = 75
MAX_RETRIES = 3
BACK_OFF_FACTOR = 2
USER_ID: Optional[str] = None


def get_user_id() -> str:
    """
    Get the splitwise user id
    :return:
    """
    global USER_ID

    if USER_ID:
        return USER_ID

    url = "https://secure.splitwise.com/api/v3.0/get_current_user"

    headers = {
        'Authorization': f'Bearer {os.getenv("SPLITWISE_TOKEN")}'
    }

    response = requests.request("GET", url, headers=headers, data={})

    if response.status_code == 200:
        USER_ID = response.json()["user"]["id"]
    else:
        raise HTTPError(f'Invalid Notion response {response.status_code} {response.text}', response=response)

    return USER_ID


def uploadNotionPagesToDb(db_id: str, pages: list):
    """
    Upload items as Notion pages to DB in Staging property row: https://developers.notion.com/reference/post-page
    :param db_id: Notion DB id (get from DB url)
    :param pages: List of Splitwise items in <created, name, amount> order
    :return:
    """
    url = "https://api.notion.com/v1/pages"
    headers = {
        'Content-Type': 'application/json',
        'Notion-Version': '2022-06-28',
        'Authorization': f'Bearer {os.getenv("NOTION_TOKEN")}',
    }

    for page in tqdm(pages):
        for i in range(MAX_RETRIES):
            payload = json.dumps({
                "parent": {
                    "type": "database_id",
                    "database_id": db_id
                },
                "properties": {
                    "Amount": {
                        "type": "number",
                        "number": page[2]
                    },
                    "Name": {
                        "type": "title",
                        "title": [
                            {
                                "type": "text",
                                "text": {
                                    "content": page[1]
                                }
                            }
                        ]
                    },
                    "Status": {
                        "select": {
                            "name": "Staging"
                        }
                    },
                    "Date": {
                        "date": {
                            "start": page[0]
                        }
                    }
                }
            })
            response = requests.request("POST", url, headers=headers, data=payload)

            if response.status_code != 200:
                if i == MAX_RETRIES - 1:
                    print(response.text)
                    raise HTTPError(f'Error uploading item {page[1]} to Notion', response=response)
                else:
                    print(f"Error response {response.text}\nRetrying")
                    time.sleep(BACK_OFF_FACTOR ** i)
            else:
                if i != 0:
                    print('Worked after retrying')
                break


def getNotionDatabase(db_id):
    """
    Get Notion target DB schema: https://developers.notion.com/reference/retrieve-a-database
    :param db_id: Notion DB id (get from DB url)
    :return: Result json
    """
    url = f"https://api.notion.com/v1/databases/{db_id}"

    headers = {
        'Notion-Version': '2022-06-28',
        'Authorization': f'Bearer {os.getenv("NOTION_TOKEN")}',
    }

    response = requests.request("GET", url, headers=headers)

    if response.status_code == 200:
        return response.json()
    else:
        raise HTTPError(f'Invalid Notion response {response.status_code} {response.text}', response=response)


def getSplitwiseLastNDays(days: int, split_items_limit: int = SPLIT_LIMIT):
    """
    Get Splitwise items added in the last n days: https://dev.splitwise.com/#tag/expenses/paths/~1get_expenses/get
    :param days: Last n days
    :param split_items_limit: Number of items in splitwise to fetch
    :return: Response json
    """
    dated_after = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = f"https://secure.splitwise.com/api/v3.0/get_expenses?dated_after={dated_after}&limit={split_items_limit}"

    headers = {
        'Authorization': f'Bearer {os.getenv("SPLITWISE_TOKEN")}'
    }

    response = requests.request("GET", url, headers=headers)

    if response.status_code == 200:
        return response.json()["expenses"]
    else:
        raise HTTPError('Invalid Splitwise response', response=response)


def main(days, notiondb, split_items_limit):
    if not days:
        raise ValueError('Days not found')
    if not notiondb:
        raise ValueError('notiondb not found')

    split_items = getSplitwiseLastNDays(days, split_items_limit)
    items = []
    for item in split_items:
        created = parser.parse(item['date'])
        deleted = item['deleted_at']
        name = item['description'].strip()
        if deleted:
            name += "(Deleted)"

        created = created.astimezone(tz.tzlocal())
        result = [created.strftime("%Y-%m-%d"), name]
        for user in item['users']:
            if user['user_id'] == get_user_id():
                result.append(float(user['owed_share'].strip()))
                items.append(result)
    print('Following records were found from Splitwise')
    for res in items:
        print(res)

    notionDb = getNotionDatabase(notiondb)
    print(f'Adding these to Notion table `{notionDb["title"][0]["text"]["content"]}` at {notionDb["url"]}')

    staging_column_id = None
    # properties = list(notionDb['properties'].keys())

    for option in notionDb['properties']['Status']['select']['options']:
        if option['name'] == 'Staging':
            staging_column_id = option['id']

    if not staging_column_id:
        raise ValueError("Target table doesn't has a Staging status column. Create Staging column to start adding")

    uploadNotionPagesToDb(notiondb, items)
    print("Expense upload to Staging successful")


dotenv.load_dotenv()

arg_parser = argparse.ArgumentParser(description="Run the Splitwise to Notion data connection. This will add all the "
                                                 "splitwise records to the Notion database in a column")
arg_parser.add_argument(
    "--days", help="Number of days in the past to get records from", default=11, type=int
)
arg_parser.add_argument(
    "--notiondb", help="Notion DB id", type=str, required=True
)
arg_parser.add_argument(
    "--splitItems", help="Number of items in splitwise to fetch", type=int, required=False, default=SPLIT_LIMIT
)

_days = arg_parser.parse_args().days
_notiondb = arg_parser.parse_args().notiondb
_split_items_limit = arg_parser.parse_args().splitItems
main(_days, _notiondb, _split_items_limit)
