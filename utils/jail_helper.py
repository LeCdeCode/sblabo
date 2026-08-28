"""Gestion de l'automatisation Jail (Auto-Ping)."""
import re
import asyncio
from config import BASE_URL, HEADERS
from utils.logger import log

SEMAPHORE_JAIL = asyncio.Semaphore(3)  # Limite 3 requêtes simultanées


def extract_prisoner_ids(text):
    """Extrait tous les identifiants Discord (17-20 chiffres) du texte.
    
    Args:
        text (str): Texte contenant potentiellement des IDs Discord
    
    Returns:
        list: Liste unique d'IDs trouvées
    """
    if not text:
        return []
    
    # Regex pour capturer les IDs Discord (snowflakes)
    matches = re.findall(r'\b\d{17,20}\b', text)
    return list(set(matches))


async def ping_prisoner(session, channel_id, user_id):
    """Envoie un ping (mention) à un prisonnier dans le salon jail.
    
    Args:
        session: Session aiohttp
        channel_id (str): ID du salon jail
        user_id (str): ID de l'utilisateur à ping
    
    Returns:
        bool: True si ping réussi, False sinon
    """
    async with SEMAPHORE_JAIL:
        url = f"{BASE_URL}/channels/{channel_id}/messages"
        payload = {"content": f"<@{user_id}>"}
        
        try:
            async with session.post(url, headers=HEADERS, json=payload, timeout=10) as resp:
                if resp.status in [200, 201]:
                    log("SUCCESS", f"✅ Jail Ping réussi pour l'ID {user_id}")
                    return True
                else:
                    body = await resp.text()
                    log("WARN", f"❌ Échec Jail Ping ({resp.status}) pour {user_id}: {body[:150]}")
                    return False
        except asyncio.TimeoutError:
            log("WARN", f"Timeout Jail Ping pour {user_id}")
            return False
        except Exception as e:
            log("ERROR", f"Exception ping_prisoner (user_id: {user_id}): {type(e).__name__}: {e}")
            return False


async def process_jail_pings(session, channel_id, user_ids):
    """Traite tous les pings jail en parallèle avec limitation de concurrence.
    
    Args:
        session: Session aiohttp
        channel_id (str): ID du salon jail
        user_ids (list): Liste des IDs utilisateur à ping
    """
    if not user_ids:
        return
    
    log("INFO", f"🔔 Traitement de {len(user_ids)} pings Jail dans le salon {channel_id}")
    
    tasks = [ping_prisoner(session, channel_id, uid) for uid in user_ids]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    success_count = sum(1 for r in results if r is True)
    log("INFO", f"🔔 Jail Pings terminés: {success_count}/{len(user_ids)} réussis")
