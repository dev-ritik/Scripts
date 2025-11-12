# Memory
This is a small Python program to aggregate and output what happened on a particular date chronologically across various
memory providers.

![image](https://github.com/user-attachments/assets/50912aff-e470-498b-a66e-331e6d005d74)

## Usage
[Deprecated] Use the web app instead.
`python main.py --on 27-04-2025 --seek-days 1`

## Supported Memory Providers

## Planned Supported Memory Providers
- Call logs (not exportable in Samsung)
- Splitwise

## Setup
- Git clone the repo
- Set up the dependencies
- The data goes in the data/ folder
### Memory provider setup
#### Diary
The current implementation expects a folder with files containing the year.
The files should be a CSV file with one of the columns as a date field

Add `DIARY_PATH` to the `.env` file and set it to the folder path

#### Instagram
  - Go to this [link](https://accountscenter.instagram.com/info_and_permissions/dyi/?entry_point=deeplink_screen)
  - Select the 
    - Customize information >> Select messages
    - Date Range: All time
    - Format: JSON
    - Media quality: Lower quality (for smaller storage usage)
  - Make a new `data/instagram` subdirectory in the data directory. Extract the `messages/inbox` from the downloaded zip here.

#### Whatsapp
WhatsApp doesn't allow downloading all the chat data at once. We can get individual chats at once. To get that:
  - Go to `settings > Chats > Chat history > Export chat` in the app.
  - Select an individual chat.
  - Export the individual txt file with or without media.
  - Make a new `whatsapp` subdirectory in the data directory.
  - Paste / extract those `WhatsApp Chat with <friend_name>.txt` / Folder with assets there.

#### Immich
If you are using immich image photo and video management solution:
  - Add user `IMMICH_BASE_URL`, `IMMICH_EMAIL`, `IMMICH_PASSWORD` to the .env

#### Google Photos
Google Photos allows 3rd party apps to get access to (only explicitly user chosen) photos via the Photos Picker API.
However there are limitations:
- We have to create session and poll for the status
- Each session can only have at max 2000 images
- Sessions and media urls expire
- Authentication token expires

Steps to setup:
- Go to Google Cloud Console
- Create/select a project. 
- Enable Google Photos Library API. 
- Create OAuth 2.0 credentials:
  - Choose Web application (for Flask integration).
  - Download the credentials.json file. Save it in `data/google_photos/credentials.json`
  - Use `http://localhost:55433/` as Authorized redirect URIs
- Run the following with `create_new_session` as True (to enable fresh selection of pictures) or False (to just fetch from existing sessions)
    - You can also paste session ids in `data/google_photos/index.json` in

```json
{"sessions": {"<session_id>": ""}}
```

```python
import init
import asyncio
from provider.google_photos_provider import GooglePhotosProvider

provider = GooglePhotosProvider()
loop = asyncio.get_event_loop()
print(loop.run_until_complete(provider.setup(create_new_session=False)))
```
- Large files can readily bloat the local assets folder

### Web app setup
- Run `pip install -r requirements.txt`
- `python app.py`
- Go to `http://127.0.0.1:5000`

## Customizations
### User DP
Wanna make the UI for the web app more elegant? Add `profile.json` to the data folder with the structure:
```json
[
  {
    "display_name": "Ritik",
    "name_regex": "(?i)ritik",  // Used to club senders across platform
    "dp": "ritik.jpg" // Used to add a dp to the chats,
    "provider_details": {
      "immich": {
        "person_id": "" // Used to filter immich message by people. Use /api/people to get the person_id
      }
    }
  }
]
