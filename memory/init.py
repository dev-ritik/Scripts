import os

import dotenv

DEBUG=True
MODE='public'

def init():
    dotenv.load_dotenv()
    global DEBUG, MODE
    DEBUG = os.getenv("DEBUG") == "True"
    MODE = os.getenv("MODE", 'public')

    print(f"Init: {DEBUG=} {MODE=}")
