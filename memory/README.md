# Memory
This is a small python program to aggregate and output what happened on a particular date chronologically across various
memory providers.

## Usage
`python main.py --on 27-04-2025 --seek-days 1`

## Supported Memory Providers

## Planned Supported Memory Providers
- Diary
- WhatsApp
- Instagram
- Splitwise

## Setup
- Git clone the repo
- Set up the dependencies
- The data goes in the data/ folder
### Memory provider setup
#### Diary
The current implementation expects a folder with files having year in it.
The files should be a CSV file with one of the column as date field

Add `DIARY_PATH` to the `.env` file and set it to the folder path

#### Instagram
  - Go to this [link](https://www.instagram.com/download/request/)
  - Make a new `data/instagram` subdirectory in the data directory. Extract the `messages/inbox` from the downloaded zip here.

#### Whatsapp
Whatsapp doesn't allow downloading all the chat data at once. We can get individual chats at once. To get that:
  - Go to `settings > Chats > Chat history > Export chat` in the app.
  - Select an individual chat.
  - Export the individual txt file `WITHOUT MEDIA`.
  - Make a new `whatsapp` subdirectory in the data directory.
  - Paste those `WhatsApp Chat with <friend_name>.txt` here.s