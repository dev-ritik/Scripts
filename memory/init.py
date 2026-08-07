import os

import dotenv

DEBUG=True
MODE='public'
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')

def init():
    dotenv.load_dotenv()
    global DEBUG, MODE, DATA_DIR
    DEBUG = os.getenv("DEBUG") == "True"
    MODE = os.getenv("MODE", 'public')
    DATA_DIR = os.getenv("DATA_DIR", DATA_DIR)

    if not os.path.exists(DATA_DIR):
        raise Exception(f"Data directory {DATA_DIR} does not exist")

    if not os.path.exists(os.path.join(DATA_DIR, 'profile.json')):
        raise Exception(f"Profile file {os.path.join(DATA_DIR, 'profile.json')} does not exist")

    print(f"Init: {DEBUG=} {MODE=} {DATA_DIR=}")
