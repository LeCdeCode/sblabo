import datetime
import time
import random
from config import BASE_URL, HEADERS

def log(level, message):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] [{level}] {message}")

def generate_discord_nonce():
    # Génération d'un Snowflake Discord valide basé sur le temps présent
    discord_epoch = 1420070400000
    current_ms = int(time.time() * 1000)
    increment = random.randint(0, 4095)
    return str(((current_ms - discord_epoch) << 22) | increment)

async def trigger_button(session, data, component, session_id, target_guild=None):
    url = f"{BASE_URL}/interactions"

    guild_id = target_guild or data.get("guild_id")
    channel_id = data.get("channel_id")
    message_id = data.get("id")
    application_id = data.get("application_id") or data.get("author", {}).get("id")

    custom_id = str(component.get("custom_id", ""))

    payload = {
        "type": 3,
        "nonce": generate_discord_nonce(),
        "channel_id": str(channel_id),
        "message_id": str(message_id),
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
        async with session.post(url, headers=HEADERS, json=payload) as resp:
            if resp.status in [200, 204]:
                log("INFO", f"⚡ [SNIPE SUCCESS] Bouton cliqué ! CustomID: '{custom_id}' | Message: {message_id} | Salon: {channel_id}")
                return True
            else:
                body = await resp.text()
                log("ERROR", f"Échec Click ({resp.status}) | CustomID: '{custom_id}' | Channel: {channel_id} | Guild: {guild_id} | Body: {body}")
                return False
    except Exception as e:
        log("ERROR", f"Exception trigger_button ({custom_id}): {e}")
        return False
