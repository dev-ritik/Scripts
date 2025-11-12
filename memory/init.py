import os

import dotenv

DEBUG=True

def init():
    dotenv.load_dotenv()
    global DEBUG
    DEBUG = os.getenv("DEBUG") == "True"

    print("DEBUG mode:", DEBUG)
