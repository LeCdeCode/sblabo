"""Gestion des interactions de boutons Discord."""
import asyncio
import time
import random
from config import BASE_URL, HEADERS
from utils.logger import log


def generate_discord_nonce():
    """Génération d'un Snowflake Discord valide basé sur le temps présent."""
    discord_epoch = 1420070400000
    current_ms = int(time.time() * 1000)
    increment = random.randint(0, 4095)
    return str(((current_ms - discord_epoch) << 22) | increment)


async def trigger_button(session, data, component, session_id, target_guild=None):
    """Déclenche un clic de bouton via l'API Discord.
    
    Args:
        session: Session aiohttp
        data: Données du message contenant channel_id, guild_id, etc.
        component: Composant bouton à cliquer
        session_id: ID de session Gateway
        target_guild: Guild ID à cibler (optionnel)
    
    Returns:
        bool: True si succès, False sinon
    """
    url = f"{BASE_URL}/interactions"

    guild_id = target_guild or data.get("guild_id")
    channel_id = str(data.get("channel_id", ""))
    message_id = str(data.get("id", ""))
    application_id = data.get("application_id") or data.get("author", {}).get("id")

    custom_id = str(component.get("custom_id", "")).strip()

    payload = {
        "type": 3,
        "nonce": generate_discord_nonce(),
        "channel_id": channel_id,
        "message_id": message_id,
        "application_id": str(application_id),
        "session_id": str(session_id),
        "message_flags": 0,
        "data": {
            "component_type": component.get("type", 2),
            "custom_id": custom_id
        }
    }

    if guild_id:
        payload["guild_id"] = str(guild_id)

    if "sku_id" in component:
        payload["data"]["sku_id"] = component["sku_id"]

    try:
        async with session.post(url, headers=HEADERS, json=payload, timeout=10) as resp:
            if resp.status in [200, 204]:
                log("SUCCESS", f"⚡ [SNIPE SUCCESS] Bouton cliqué ! CustomID: '{custom_id}' | Message: {message_id} | Salon: {channel_id}")
                return True
            else:
                body = await resp.text()
                log("ERROR", f"Échec Click ({resp.status}) | CustomID: '{custom_id}' | Channel: {channel_id} | Guild: {guild_id} | Response: {body[:200]}")
                return False
    except asyncio.TimeoutError:
        log("WARN", f"Timeout trigger_button pour CustomID: '{custom_id}'")
        return False
    except Exception as e:
        log("ERROR", f"Exception trigger_button (CustomID: '{custom_id}'): {type(e).__name__}: {e}")
        return False
