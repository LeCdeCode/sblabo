"""Gestion des notifications et envoi de messages."""
from utils.logger import log
import asyncio


async def send_response(session, channel_id, user_data, content="", embed=None, headers=None, base_url=None):
    """Envoie une réponse directe via message (pas de webhook pour éviter erreurs permission).
    
    Args:
        session: Session aiohttp
        channel_id (str): ID du salon cible
        user_data (dict): Données utilisateur
        content (str): Contenu du message
        embed (dict): Données d'embed (optionnel)
        headers (dict): Headers personnalisés (optionnel)
        base_url (str): URL de base (optionnel)
    
    Returns:
        bool: True si envoi réussi, False sinon
    """
    from config import HEADERS as DEFAULT_HEADERS, BASE_URL as DEFAULT_BASE_URL
    
    headers = headers or DEFAULT_HEADERS
    base_url = base_url or DEFAULT_BASE_URL

    # Prépare le payload du message
    msg_payload = {}
    if content:
        msg_payload["content"] = content
    if embed:
        msg_payload["embeds"] = [embed]

    # Utilise l'API REST directe (plus fiable que webhook)
    msg_url = f"{base_url}/channels/{channel_id}/messages"
    
    try:
        async with session.post(msg_url, headers=headers, json=msg_payload, timeout=10) as resp:
            if resp.status in [200, 201]:
                log("SUCCESS", f"Message envoyé au salon {channel_id}")
                return True
            else:
                body = await resp.text()
                log("WARN", f"Échec envoi message REST ({resp.status}): {body[:150]}")
                return False
    except asyncio.TimeoutError:
        log("WARN", f"Timeout send_response pour channel {channel_id}")
        return False
    except Exception as e:
        log("ERROR", f"Exception send_response: {type(e).__name__}: {e}")
        return False
