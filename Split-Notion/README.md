# Splitwise-Notion Connector
This connector is return to manage my financials in a Notion database.
This works by pulling the expense report from Splitwise and pushing it to Notion.

- This creates all the expenses in the staging select option column

## Setup
- Install tqdm
- Get the notion db id from db link (the uuid before the `?`)
- Run the command below

## Usage
```shell
usage: main.py [-h] [--days DAYS] --notiondb NOTIONDB

Run the Splitwise to Notion data connection. This will add all the splitwise records to the Notion database in a column

options:
  -h, --help           show this help message and exit
  --days DAYS          Number of days in the past to get records from
  --notiondb NOTIONDB  Notion DB id
```
### Example
`python main.py --days 10 --notiondb d9824bdc84454327be8b5b47500af6ce`