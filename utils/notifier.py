from utils.logger import log

WEBHOOK_CACHE = {}

async def get_or_create_webhook(session, channel_id, headers, base_url):
    """Récupère ou crée un webhook pour un salon"""
    if channel_id in WEBHOOK_CACHE:
        return WEBHOOK_CACHE[channel_id]

    url = f"{base_url}/channels/{channel_id}/webhooks"
    try:
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                webhooks = await resp.json()
                for wh in webhooks:
                    if wh.get("type") == 1:
                        WEBHOOK_CACHE[channel_id] = wh["id"], wh["token"]
                        return wh["id"], wh["token"]

        # Si aucun webhook existant, on en crée un
        payload = {"name": "LabNotifier"}
        async with session.post(url, headers=headers, json=payload) as resp:
            if resp.status in [200, 201]:
                wh = await resp.json()
                WEBHOOK_CACHE[channel_id] = wh["id"], wh["token"]
                return wh["id"], wh["token"]
            else:
                body = await resp.text()
                log("ERROR", f"Échec création Webhook ({resp.status}): {body}")
    except Exception as e:
        log("ERROR", f"Exception get_or_create_webhook: {e}")

    return None, None

async def send_response(session, channel_id, user_data, content, embed=None, headers=None, base_url=None):
    """Envoie une réponse via webhook ou message standard"""
    from config import HEADERS as DEFAULT_HEADERS, BASE_URL as DEFAULT_BASE_URL
    headers = headers or DEFAULT_HEADERS
    base_url = base_url or DEFAULT_BASE_URL

    wh_id, wh_token = await get_or_create_webhook(session, channel_id, headers, base_url)
    
    payload = {
        "content": content,
        "username": user_data.get("username", "LabSystem"),
        "avatar_url": f"https://cdn.discordapp.com/avatars/{user_data.get('id')}/{user_data.get('avatar')}.png" if user_data.get("avatar") else None
    }
    if embed:
        payload["embeds"] = [embed]

    if wh_id and wh_token:
        wh_url = f"{base_url}/webhooks/{wh_id}/{wh_token}"
        try:
            async with session.post(wh_url, json=payload) as resp:
                if resp.status in [200, 204]:
                    return True
                log("WARN", f"Webhook d'envoi refusé ({resp.status}), fallback REST direct.")
        except Exception as e:
            log("ERROR", f"Erreur envoi Webhook: {e}")

    # Fallback message standard si webhook échoue
    msg_url = f"{base_url}/channels/{channel_id}/messages"
    msg_payload = {"content": content}
    if embed:
        msg_payload["embeds"] = [embed]

    try:
        async with session.post(msg_url, headers=headers, json=msg_payload) as resp:
            if resp.status in [200, 201]:
                return True
            body = await resp.text()
            log("ERROR", f"Échec envoi message REST ({resp.status}): {body}")
    except Exception as e:
        log("ERROR", f"Exception send_response REST: {e}")

    return False
