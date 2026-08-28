import asyncio
import json
import os
import random
import time
import websockets
import aiohttp
from config import TOKEN, HEADERS, BASE_URL
from utils.notifier import send_response
from utils.interaction_helper import trigger_button
from utils.jail_helper import extract_prisoner_ids, process_jail_pings

CHANNEL_GAV = "1465600954719010971"
GUILD_GAV = "1038108273703919746"
GUILD_CLAIM = "1038108273703919746"
GUILD_RECUPERER = "1038108273703919746"

# Cibles strictes pour l'Auto-Ping
CHANNEL_JAIL = "1465573805450723453"
BOT_UHQ_ID = "1418944648432586862"

class LabClient:
    def __init__(self):
        self.ws = None
        self.session = None
        self.user_data = {}
        self.heartbeat_interval = 0
        self.sequence_number = None
        self.session_id = None
        self.heartbeat_task = None
        
        self.clicked_messages = set()
        self.active_tickets = set()
        self.last_ping_time = None
        self.config = self.load_config()

    def load_config(self):
        if os.path.exists("snipe_config.json"):
            try:
                with open("snipe_config.json", "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"recuperer": True, "claim": True, "gav": True, "ap": True}

    def save_config(self):
        try:
            with open("snipe_config.json", "w") as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            print(f"[!] Erreur sauvegarde config : {e}")

    async def send_heartbeat(self):
        while True:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                if self.ws:
                    payload = {"op": 1, "d": self.sequence_number}
                    await self.ws.send(json.dumps(payload))
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[HEARTBEAT STOP] {e}")
                break

    def extract_buttons(self, components):
        buttons = []
        for row in components:
            for comp in row.get("components", []):
                if comp.get("type") == 2:
                    buttons.append(comp)
        return buttons

    async def log_snipe_event(self, module_name, label, guild_id, channel_id, msg_id, success):
        print(f"[⚡ SNIPE SUCCESS] Module: {module_name} | Label: {label} | Channel: {channel_id}")

    async def send_welcome_message(self, channel_id):
        await asyncio.sleep(random.uniform(0.4, 0.9))
        msg = random.choice([
            "ouais dis moi", "salut, je t’ecoute", "salut, dis moi tout",
            "yo, dis moi,", "ça va? comment je peux t’aider", "yo, dis moi ce qu'il y’a"
        ])
        url = f"{BASE_URL}/channels/{channel_id}/messages"
        payload = {"content": msg}
        try:
            async with self.session.post(url, headers=HEADERS, json=payload) as resp:
                pass
        except Exception:
            pass

    async def handle_jail_automation(self, data):
        if not self.config.get("ap"):
            return
            
        channel_id = str(data.get("channel_id", ""))
        author_id = str(data.get("author", {}).get("id", ""))

        # Filtrage strict du salon et du bot UHQ
        if channel_id != CHANNEL_JAIL:
            return
            
        if author_id != BOT_UHQ_ID:
            return

        embeds = data.get("embeds", [])
        if not embeds:
            return

        print(f"[DEBUG AP] Message UHQ40 détecté dans le salon Jail {channel_id}")

        content = data.get("content", "")
        full_text = content
        for emb in embeds:
            full_text += " " + str(emb.get("title", ""))
            full_text += " " + str(emb.get("description", ""))
            for f in emb.get("fields", []):
                full_text += " " + str(f.get("name", "")) + " " + str(f.get("value", ""))

        user_ids = extract_prisoner_ids(full_text)
        if user_ids:
            print(f"[DEBUG AP] IDs détectés dans l'embed : {user_ids}")
            asyncio.create_task(process_jail_pings(self.session, channel_id, user_ids))

    async def process_snipe(self, data):
        msg_id = data.get("id")
        if not msg_id or msg_id in self.clicked_messages:
            return

        channel_id = str(data.get("channel_id", ""))
        guild_id = data.get("guild_id")
        components = data.get("components", [])
        
        buttons = self.extract_buttons(components)
        if not buttons:
            return

        print(f"[DEBUG BUTTONS] Bouton(s) détecté(s) dans le salon {channel_id}")

        # Module 1 : GAV Direct
        if channel_id == CHANNEL_GAV and self.config.get("gav", True):
            target_guild = guild_id if guild_id else GUILD_GAV
            for btn in buttons:
                if btn.get("disabled", False):
                    continue
                self.clicked_messages.add(msg_id)
                btn_label = btn.get("label") or btn.get("custom_id") or "Bouton GAV"

                asyncio.create_task(trigger_button(self.session, data, btn, self.session_id, target_guild))
                asyncio.create_task(self.log_snipe_event("gav", btn_label, target_guild, channel_id, msg_id, True))
                return

        # Module 2 : Claim Tickets
        if (guild_id == GUILD_CLAIM or not guild_id) and self.config.get("claim", True):
            if len(self.active_tickets) < 2:
                for btn in buttons:
                    if btn.get("disabled", False):
                        continue
                    label = str(btn.get("label", "")).strip()
                    custom_id = str(btn.get("custom_id", "")).strip()
                    if (label.lower() == "claim" or "claim" in custom_id.lower()) and "unclaim" not in label.lower() and "unclaim" not in custom_id.lower():
                        self.clicked_messages.add(msg_id)
                        self.active_tickets.add(channel_id)
                        target_guild = guild_id or GUILD_CLAIM

                        asyncio.create_task(trigger_button(self.session, data, btn, self.session_id, target_guild))
                        asyncio.create_task(self.log_snipe_event("claim", label or custom_id, target_guild, channel_id, msg_id, True))
                        asyncio.create_task(self.send_welcome_message(channel_id))
                        return

        # Module 3 : Récupérer
        if (guild_id == GUILD_RECUPERER or not guild_id) and self.config.get("recuperer", True):
            for btn in buttons:
                if btn.get("disabled", False):
                    continue
                label = str(btn.get("label", ""))
                if "récupérer !" in label.lower() or "recuperer !" in label.lower():
                    self.clicked_messages.add(msg_id)
                    asyncio.create_task(trigger_button(self.session, data, btn, self.session_id, guild_id or GUILD_RECUPERER))
                    asyncio.create_task(self.log_snipe_event("recuperer", label, guild_id or GUILD_RECUPERER, channel_id, msg_id, True))
                    return

    async def handle_command(self, data):
        author_id = data.get("author", {}).get("id")
        if author_id != self.user_data.get("id"):
            return
        content = data.get("content", "").strip()
        channel_id = data.get("channel_id")
        
        if content == ".ping":
            latency = round((time.time() - self.last_ping_time) * 1000) if self.last_ping_time else "N/A"
            embed_data = {
                "title": "🏓 Pong !",
                "color": 0x5865F2,
                "fields": [
                    {"name": "Latence Gateway", "value": f"`{latency} ms`", "inline": True},
                    {"name": "Statut", "value": "🟢 Opérationnel", "inline": True}
                ],
                "footer": {"text": "Lab Selfbot System"}
            }
            await send_response(self.session, channel_id, self.user_data, "", embed_data)
            
        elif content.startswith(".snipe"):
            parts = content.split()
            if len(parts) == 1 or (len(parts) == 2 and parts[1].lower() == "status"):
                embed_data = {
                    "title": "📊 Statut des Modules",
                    "color": 0x3498DB,
                    "fields": [
                        {"name": "Récupérer", "value": "🟢 Actif" if self.config.get("recuperer") else "🔴 Désactivé", "inline": True},
                        {"name": "Claim Tickets", "value": "🟢 Actif" if self.config.get("claim") else "🔴 Désactivé", "inline": True},
                        {"name": "GAV Direct", "value": "🟢 Actif" if self.config.get("gav") else "🔴 Désactivé", "inline": True},
                        {"name": "Auto Ping (AP)", "value": "🟢 Actif" if self.config.get("ap") else "🔴 Désactivé", "inline": True},
                        {"name": "Tickets Ouverts", "value": f"`{len(self.active_tickets)}/2`", "inline": False}
                    ],
                    "footer": {"text": "Lab Selfbot Config"}
                }
                await send_response(self.session, channel_id, self.user_data, "", embed_data)
            elif len(parts) == 3:
                action = parts[1].lower()
                target = parts[2].lower()
                if target in ["recuperer", "claim", "gav", "ap"]:
                    if action == "on":
                        self.config[target] = True
                        self.save_config()
                        await send_response(self.session, channel_id, self.user_data, f"✅ Module **{target.upper()}** activé.")
                    elif action == "off":
                        self.config[target] = False
                        self.save_config()
                        await send_response(self.session, channel_id, self.user_data, f"🛑 Module **{target.upper()}** désactivé.")

    async def subscribe_guild_events(self, ws):
        """Abonne le websocket aux événements des serveurs clés (GAV, Claim, AP)."""
        guild_ids = list(set([GUILD_GAV, GUILD_CLAIM, GUILD_RECUPERER]))
        for g_id in guild_ids:
            subscribe_payload = {
                "op": 37,
                "d": {
                    "subscriptions": {
                        g_id: {
                            "typing": False,
                            "threads": False,
                            "activities": False,
                            "members": []
                        }
                    }
                }
            }
            await ws.send(json.dumps(subscribe_payload))
        print("[+] Abonnements Gateway envoyés pour recevoir tous les événements de salons.")

    async def start(self):
        connector = aiohttp.TCPConnector(
            limit=0,
            ttl_dns_cache=600,
            keepalive_timeout=120,
            enable_cleanup_closed=True
        )
        self.session = aiohttp.ClientSession(connector=connector)
        async with self.session.get(f"{BASE_URL}/users/@me", headers=HEADERS) as resp:
            if resp.status != 200:
                print(f"[AUTH ERROR] Token invalide (Status {resp.status})")
                await self.session.close()
                return
            self.user_data = await resp.json()
            print(f"[+] Connecté : {self.user_data['username']} ({self.user_data['id']})")
            
        while True:
            try:
                async with websockets.connect(
                    "wss://gateway.discord.gg/?v=9&encoding=json",
                    max_size=None,
                    ping_interval=None
                ) as ws:
                    self.ws = ws

                    hello = json.loads(await ws.recv())
                    if hello.get("op") == 10:
                        self.heartbeat_interval = hello['d']['heartbeat_interval'] / 1000
                    if self.heartbeat_task:
                        self.heartbeat_task.cancel()
                    self.heartbeat_task = asyncio.create_task(self.send_heartbeat())
                    
                    identify = {
                        "op": 2,
                        "d": {
                            "token": TOKEN,
                            "properties": {
                                "$os": "linux",
                                "$browser": "Discord Client",
                                "$device": "desktop"
                            }
                        }
                    }
                    await ws.send(json.dumps(identify))
                    
                    while True:
                        msg = await ws.recv()
                        event = json.loads(msg)
                        
                        if "s" in event and event["s"] is not None:
                            self.sequence_number = event["s"]
                            
                        t = event.get("t")
                        d = event.get("d", {})
                        
                        if t == "READY":
                            self.session_id = d.get("session_id")
                            print(f"[+] Gateway READY | Session ID: {self.session_id}")
                            await self.subscribe_guild_events(ws)
                        elif t == "CHANNEL_DELETE":
                            ch_id = str(d.get("id"))
                            if ch_id in self.active_tickets:
                                self.active_tickets.remove(ch_id)
                        elif t in ["MESSAGE_CREATE", "MESSAGE_UPDATE"]:
                            asyncio.create_task(self.handle_command(d))
                            asyncio.create_task(self.process_snipe(d))
                            asyncio.create_task(self.handle_jail_automation(d))
            except Exception as e:
                if self.heartbeat_task:
                    self.heartbeat_task.cancel()
                print(f"[WS ERROR] {e}")
                await asyncio.sleep(2)
