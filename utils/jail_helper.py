import re
import asyncio
from config import BASE_URL, HEADERS
from utils.logger import log

SEMAPHORE_JAIL = asyncio.Semaphore(3)

def extract_prisoner_ids(text):
    """Extrait tous les identifiants Discord (17-20 chiffres) du texte"""
    if not text:
        return []
    matches = re.findall(r'\b\d{17,20}\b', text)
    return list(set(matches))

async def ping_prisoner(session, channel_id, user_id):
    """Envoie un ping à un prisonnier dans le salon jail"""
    async with SEMAPHORE_JAIL:
        url = f"{BASE_URL}/channels/{channel_id}/messages"
        payload = {"content": f"<@{user_id}>"}
        try:
            async with session.post(url, headers=HEADERS, json=payload) as resp:
                if resp.status in [200, 201]:
                    log("SUCCESS", f"✅ Jail Ping réussi pour l'ID {user_id}")
                    return True
                else:
                    body = await resp.text()
                    log("WARN", f"❌ Échec Jail Ping ({resp.status}) pour {user_id}: {body}")
        except Exception as e:
            log("ERROR", f"Exception ping_prisoner ({user_id}): {e}")
        return False

async def process_jail_pings(session, channel_id, user_ids):
    """Traite tous les pings jail en parallèle"""
    if not user_ids:
        return
    log("INFO", f"🔔 Traitement de {len(user_ids)} pings Jail dans le salon {channel_id}")
    tasks = [ping_prisoner(session, channel_id, uid) for uid in user_ids]
    await asyncio.gather(*tasks, return_exceptions=True)
