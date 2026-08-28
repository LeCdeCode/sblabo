"""Gestion des notifications et envoi de messages avec webhooks intelligents."""
from utils.logger import log
import asyncio

WEBHOOK_CACHE = {}


async def get_or_create_webhook(session, channel_id, headers, base_url):
    """Récupère ou crée un webhook pour un salon.
    
    Args:
        session: Session aiohttp
        channel_id (str): ID du salon
        headers (dict): Headers pour l'authentification
        base_url (str): URL de base de l'API Discord
    
    Returns:
        tuple: (webhook_id, webhook_token) ou (None, None) si échec/pas de perms
    """
    if channel_id in WEBHOOK_CACHE:
        return WEBHOOK_CACHE[channel_id]

    url = f"{base_url}/channels/{channel_id}/webhooks"
    
    try:
        # Essai de récupération des webhooks existants
        async with session.get(url, headers=headers, timeout=10) as resp:
            if resp.status == 200:
                webhooks = await resp.json()
                for wh in webhooks:
                    if wh.get("type") == 1:  # Type webhook
                        WEBHOOK_CACHE[channel_id] = (wh["id"], wh["token"])
                        return wh["id"], wh["token"]
            elif resp.status == 403:
                # Pas de perms pour créer webhook
                log("DEBUG", f"Pas de perms webhook pour {channel_id}, fallback REST direct")
                WEBHOOK_CACHE[channel_id] = (None, None)
                return None, None

        # Si aucun webhook existant, on en crée un
        payload = {"name": "LabAutoNotifier"}
        async with session.post(url, headers=headers, json=payload, timeout=10) as resp:
            if resp.status in [200, 201]:
                wh = await resp.json()
                WEBHOOK_CACHE[channel_id] = (wh["id"], wh["token"])
                log("DEBUG", f"Webhook créé pour le salon {channel_id}")
                return wh["id"], wh["token"]
            elif resp.status == 403:
                # Pas de perms pour créer webhook
                log("DEBUG", f"Pas de perms pour créer webhook {channel_id}, fallback REST direct")
                WEBHOOK_CACHE[channel_id] = (None, None)
                return None, None
            else:
                body = await resp.text()
                log("DEBUG", f"Impossible créer Webhook ({resp.status}): {body[:100]}")
    except asyncio.TimeoutError:
        log("DEBUG", f"Timeout get_or_create_webhook pour {channel_id}")
    except Exception as e:
        log("DEBUG", f"Exception get_or_create_webhook: {type(e).__name__}")

    WEBHOOK_CACHE[channel_id] = (None, None)
    return None, None


def get_user_avatar_url(user_data):
    """Construit l'URL de l'avatar Discord de l'utilisateur.
    
    Args:
        user_data (dict): Données utilisateur (id, avatar, etc.)
    
    Returns:
        str: URL complète de l'avatar ou None
    """
    user_id = user_data.get("id")
    avatar = user_data.get("avatar")
    
    if not user_id or not avatar:
        return None
    
    # Format: https://cdn.discordapp.com/avatars/{user_id}/{avatar}.png
    return f"https://cdn.discordapp.com/avatars/{user_id}/{avatar}.png"


async def send_response(session, channel_id, user_data, content="", embed=None, headers=None, base_url=None):
    """Envoie une réponse via webhook (si perms) ou message direct.
    
    **Hiérarchie d'envoi:**
    1. Webhook + Embed (si perms webhook ET embed fourni)
       - Nom: Display name du compte
       - Avatar: PP du compte utilisateur
    2. Message REST + Embed (si embed fourni, webhook échoué)
    3. Message REST texte (fallback)
    
    Args:
        session: Session aiohttp
        channel_id (str): ID du salon cible
        user_data (dict): Données utilisateur (username, global_name, avatar, id)
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

    # Récupère le display name et l'avatar
    display_name = user_data.get("global_name") or user_data.get("username", "LabSystem")
    avatar_url = get_user_avatar_url(user_data)

    # Essai webhook si embed disponible
    if embed:
        wh_id, wh_token = await get_or_create_webhook(session, channel_id, headers, base_url)
        
        if wh_id and wh_token:
            wh_url = f"{base_url}/webhooks/{wh_id}/{wh_token}"
            
            wh_payload = {
                "username": display_name,
                "embeds": [embed]
            }
            
            if avatar_url:
                wh_payload["avatar_url"] = avatar_url
            
            if content:
                wh_payload["content"] = content
            
            try:
                async with session.post(wh_url, json=wh_payload, timeout=10) as resp:
                    if resp.status in [200, 204]:
                        log("SUCCESS", f"Message (webhook) envoyé à {channel_id} par {display_name}")
                        return True
                    else:
                        log("DEBUG", f"Webhook échec ({resp.status}), fallback REST+embed")
            except Exception as e:
                log("DEBUG", f"Webhook erreur: {type(e).__name__}, fallback REST+embed")

    # Fallback: Message REST direct avec embed
    msg_url = f"{base_url}/channels/{channel_id}/messages"
    msg_payload = {}
    
    if content:
        msg_payload["content"] = content
    if embed:
        msg_payload["embeds"] = [embed]
    
    # Assurer qu'on n'envoie jamais un message vide
    if not msg_payload:
        msg_payload["content"] = "..."
    
    try:
        async with session.post(msg_url, headers=headers, json=msg_payload, timeout=10) as resp:
            if resp.status in [200, 201]:
                log("SUCCESS", f"Message (REST) envoyé à {channel_id}")
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
