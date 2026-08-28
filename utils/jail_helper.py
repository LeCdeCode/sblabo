import re
import asyncio
import datetime
from config import BASE_URL, HEADERS

def log(level, message):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] [{level}] {message}")

SEMAPHORE_JAIL = asyncio.Semaphore(3)

def extract_prisoner_ids(text):
    if not text:
        return []
    # Capture tous les identifiants numériques de 17 à 20 chiffres
    matches = re.findall(r'\b\d{17,20}\b', text)
    return list(set(matches))

async def ping_prisoner(session, channel_id, user_id):
    async with SEMAPHORE_JAIL:
        url = f"{BASE_URL}/channels/{channel_id}/messages"
        payload = {"content": f"<@{user_id}>"}
        try:
            async with session.post(url, headers=HEADERS, json=payload) as resp:
                if resp.status in [200, 201]:
                    log("INFO", f"Jail Ping réussi pour l'ID {user_id}")
                    return True
                else:
                    body = await resp.text()
                    log("WARN", f"Échec Jail Ping ({resp.status}) pour {user_id}: {body}")
        except Exception as e:
            log("ERROR", f"Exception ping_prisoner ({user_id}): {e}")
        return False

async def process_jail_pings(session, channel_id, user_ids):
    if not user_ids:
        return
    log("INFO", f"Traitement de {len(user_ids)} pings Jail dans le salon {channel_id}")
    tasks = [ping_prisoner(session, channel_id, uid) for uid in user_ids]
    await asyncio.gather(*tasks, return_exceptions=True)
