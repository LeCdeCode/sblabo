import os
from dotenv import load_dotenv

# Charge les variables contenues dans le fichier .env
load_dotenv()

TOKEN = os.getenv("TOKEN")
BASE_URL = "https://discord.com/api/v9"

HEADERS = {
    "Authorization": TOKEN,
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
