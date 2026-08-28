"""Gestion des interactions de boutons Discord avec logging détaillé."""
import asyncio
import time
import random
import datetime
from config import BASE_URL, HEADERS
from utils.logger import log


# IDs des salons pour logging
LOGS_CHANNELS = {
    "claim": "1542720652002468009",      # Tickets
    "gav": "1542720752279756821",        # GAV
    "recuperer": "1542720841765093396"   # Récupérer
}

GUILD_ID = "1496360520549269524"  # Serveur principal


def generate_discord_nonce():
    """Génération d'un Snowflake Discord valide basé sur le temps présent."""
    discord_epoch = 1420070400000
    current_ms = int(time.time() * 1000)
    increment = random.randint(0, 4095)
    return str(((current_ms - discord_epoch) << 22) | increment)


async def send_button_log(session, module_name, data, component, success, latency_ms=None):
    """Envoie un log détaillé d'un bouton cliqué.
    
    Args:
        session: Session aiohttp
        module_name: "claim", "gav", ou "recuperer"
        data: Données du message
        component: Composant bouton
        success: True si clic réussi
        latency_ms: Latence en ms (optionnel)
    """
    log_channel = LOGS_CHANNELS.get(module_name)
    if not log_channel:
        return
    
    # Récupère les infos
    msg_id = data.get("id", "?")
    channel_id = data.get("channel_id", "?")
    guild_id = data.get("guild_id", GUILD_ID)
    custom_id = component.get("custom_id", "?")
    label = component.get("label", "Sans label")
    
    now = datetime.datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    latency_str = f"{latency_ms}ms" if latency_ms else "N/A"
    
    # Détermine la couleur et le statut
    if module_name == "claim":
        color = 0x00FF00 if success else 0xFF0000  # Vert ou Rouge
        title_prefix = "✅" if success else "❌"
    elif module_name == "gav":
        color = 0x0099FF if success else 0xFF0000  # Bleu ou Rouge
        title_prefix = "⚡" if success else "❌"
    else:  # recuperer
        color = 0xFFAA00 if success else 0xFF0000  # Orange ou Rouge
        title_prefix = "🎁" if success else "❌"
    
    # Crée l'embed
    embed = {
        "title": f"{title_prefix} [{module_name.upper()}] {'Succès' if success else 'Erreur'}",
        "color": color,
        "timestamp": now.isoformat(),
        "fields": [
            {"name": "📩 Custom ID", "value": f"`{custom_id}`", "inline": True},
            {"name": "🏷️ Label", "value": f"`{label}`", "inline": True},
            {"name": "⏱️ Latence", "value": f"`{latency_str}`", "inline": True},
            {"name": "💬 Message ID", "value": f"`{msg_id}`", "inline": True},
            {"name": "🏘️ Salon ID", "value": f"`{channel_id}`", "inline": True},
            {"name": "🔗 Serveur ID", "value": f"`{guild_id}`", "inline": True},
            {"name": "🕐 Heure", "value": f"`{timestamp}`", "inline": False}
        ],
        "footer": {"text": "Lab Snipe System"}
    }
    
    # Pour les tickets (claim), ajoute la mention en haut et le user ID
    if module_name == "claim":
        author = data.get("author", {})
        user_id = author.get("id", "?")
        username = author.get("username", "Utilisateur")
        
        # Ajoute la mention au titre
        embed["title"] = f"{title_prefix} [{module_name.upper()}] {'Succès' if success else 'Erreur'} - <@{user_id}>"
        
        # Ajoute le user ID aux fields
        embed["fields"].insert(0, {"name": "👤 User ID", "value": f"<@{user_id}> (`{user_id}`)", "inline": False})
    
    # Envoie le log
    url = f"{BASE_URL}/channels/{log_channel}/messages"
    payload = {"embeds": [embed]}
    
    try:
        async with session.post(url, headers=HEADERS, json=payload, timeout=10) as resp:
            if resp.status in [200, 201]:
                log("DEBUG", f"Log {module_name.upper()} envoyé au salon {log_channel}")
            else:
                body = await resp.text()
                log("WARN", f"Échec envoi log {module_name} ({resp.status}): {body[:100]}")
    except Exception as e:
        log("ERROR", f"Exception send_button_log ({module_name}): {type(e).__name__}: {e}")


async def trigger_button(session, data, component, session_id, target_guild=None, on_success_log=None):
    """Déclenche un clic de bouton via l'API Discord.
    
    Args:
        session: Session aiohttp
        data: Données du message contenant channel_id, guild_id, etc.
        component: Composant bouton à cliquer
        session_id: ID de session Gateway
        target_guild: Guild ID à cibler (optionnel)
        on_success_log: Callback(success, latency_ms) pour logging (optionnel)
    
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

    start_time = time.time()
    
    try:
        async with session.post(url, headers=HEADERS, json=payload, timeout=10) as resp:
            latency_ms = round((time.time() - start_time) * 1000)
            
            if resp.status in [200, 204]:
                log("SUCCESS", f"⚡ [SNIPE SUCCESS] Bouton cliqué ! CustomID: '{custom_id}' | Message: {message_id} | Salon: {channel_id} | Latence: {latency_ms}ms")
                if on_success_log:
                    await on_success_log(True, latency_ms)
                return True
            else:
                body = await resp.text()
                log("ERROR", f"Échec Click ({resp.status}) | CustomID: '{custom_id}' | Channel: {channel_id} | Guild: {guild_id} | Response: {body[:200]}")
                if on_success_log:
                    await on_success_log(False, latency_ms)
                return False
    except asyncio.TimeoutError:
        latency_ms = round((time.time() - start_time) * 1000)
        log("WARN", f"Timeout trigger_button pour CustomID: '{custom_id}'")
        if on_success_log:
            await on_success_log(False, latency_ms)
        return False
    except Exception as e:
        latency_ms = round((time.time() - start_time) * 1000)
        log("ERROR", f"Exception trigger_button (CustomID: '{custom_id}'): {type(e).__name__}: {e}")
        if on_success_log:
            await on_success_log(False, latency_ms)
        return False
