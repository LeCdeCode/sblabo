import asyncio
import json
import os
import random
import time
import websockets
import aiohttp

from config import TOKEN, HEADERS, BASE_URL
from utils.notifier import send_response, log
from utils.interaction_helper import trigger_button
from utils.jail_helper import extract_prisoner_ids, process_jail_pings

# ID Salons & Guildes ciblés
CHANNEL_GAV = "1465600954719010971"
GUILD_GAV = "1038108273703919746"
GUILD_CLAIM = "1038108273703919746"
GUILD_RECUPERER = "1038108273703919746"

CHANNEL_JAIL = "1465573805450723453"
BOT_UHQ_ID = "1418944648432586862"

MAX_CLICKED_CACHE = 3000

class LabClient:
    def __init__(self):
        self.ws = None
        self.session = None
        self.user_data = {}
        self.heartbeat_interval = 0
        self.sequence_number = None
        self.session_id = None
        self.heartbeat_task = None
        
        self.last_ping_sent = 0.0
        self.latency_ms = None
        self.missed_acks = 0

        self.clicked_messages = set()
        self.active_tickets = set()
        self.background_tasks = set()
        self.config = self.load_config()

    def load_config(self):
        if os.path.exists("snipe_config.json"):
            try:
                with open("snipe_config.json", "r") as f:
                    return json.load(f)
            except Exception as e:
                log("ERROR", f"Erreur lecture snipe_config.json: {e}")
        return {"recuperer": True, "claim": True, "gav": True, "ap": True}

    def save_config(self):
        try:
            with open("snipe_config.json", "w") as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            log("ERROR", f"Erreur sauvegarde config: {e}")

    def create_managed_task(self, coro):
        task = asyncio.create_task(coro)
        self.background_tasks.add(task)
        task.add_done_callback(self._on_task_complete)
        return task

    def _on_task_complete(self, task):
        self.background_tasks.discard(task)
        if not task.cancelled() and task.exception():
            log("ERROR", f"Tâche asynchrone non interceptée: {task.exception()}")

    def track_clicked_message(self, msg_id):
        self.clicked_messages.add(msg_id)
        if len(self.clicked_messages) > MAX_CLICKED_CACHE:
            discard_count = len(self.clicked_messages) - MAX_CLICKED_CACHE
            for _ in range(discard_count):
                self.clicked_messages.pop()

    def is_ws_open(self):
        if not self.ws:
            return False
        if hasattr(self.ws, 'closed'):
            return not self.ws.closed
        return self.ws.close_code is None

    async def send_heartbeat(self):
        while True:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                if self.is_ws_open():
                    if self.missed_acks >= 4:
                        log("WARN", f"Absence de {self.missed_acks} ACK(s) Heartbeat consécutifs. Reconnexion...")
                        await self.ws.close(4000)
                        break

                    self.missed_acks += 1
                    self.last_ping_sent = time.time()
                    payload = {"op": 1, "d": self.sequence_number}
                    await self.ws.send(json.dumps(payload))
                else:
                    break
            except asyncio.CancelledError:
                break
            except Exception as e:
                log("ERROR", f"Erreur Heartbeat: {e}")
                break

    def extract_buttons(self, components):
        buttons = []
        if not isinstance(components, list):
            return buttons

        for row in components:
            if isinstance(row, dict) and "components" in row:
                for comp in row.get("components", []):
                    if isinstance(comp, dict) and comp.get("type") == 2:
                        buttons.append(comp)
        return buttons

    async def handle_gav_click(self, data, btn, target_guild, msg_id):
        log("INFO", f"⏳ [GAV EXECUTION] Envoi de l'interaction bouton sur Msg {msg_id}...")
        success = await trigger_button(self.session, data, btn, self.session_id, target_guild)
        if success:
            self.track_clicked_message(msg_id)
            log("INFO", f"✅ [GAV SUCCESS] Bouton GAV cliqué avec succès !")
        else:
            log("WARN", f"❌ [GAV ERROR] Échec de l'interaction HTTP sur le GAV.")

    async def process_gav_snipe(self, data):
        msg_id = data.get("id")
        if not msg_id or msg_id in self.clicked_messages:
            return

        components = data.get("components", [])
        buttons = self.extract_buttons(components)

        if not buttons:
            log("INFO", f"🔍 [GAV SCAN] Message {msg_id} reçu sans bouton Gateway (En attente de UPDATE...)")
            return

        log("INFO", f"⚡ [GAV SNIPE] {len(buttons)} bouton(s) trouvé(s) via Gateway sur Msg {msg_id} !")

        for btn in buttons:
            if not btn.get("disabled", False):
                await self.handle_gav_click(data, btn, GUILD_GAV, msg_id)
                return

    async def handle_claim_flow(self, data, btn, target_guild, channel_id):
        click_success = await trigger_button(self.session, data, btn, self.session_id, target_guild)
        if click_success:
            human_delay = random.uniform(1.2, 2.5)
            log("INFO", f"⏳ Attente humaine de {human_delay:.2f}s avant envoi du message d'accueil...")
            await asyncio.sleep(human_delay)
            await self.send_welcome_message(channel_id)

    async def send_welcome_message(self, channel_id):
        msg = random.choice([
            "ouais dis moi", "salut, je t’ecoute", "salut, dis moi tout",
            "yo, dis moi,", "ça va? comment je peux t’aider", "yo, dis moi ce qu'il y’a"
        ])
        url = f"{BASE_URL}/channels/{channel_id}/messages"
        payload = {"content": msg}
        try:
            async with self.session.post(url, headers=HEADERS, json=payload) as resp:
                if resp.status not in [200, 201]:
                    body = await resp.text()
                    log("WARN", f"Échec send_welcome_message ({resp.status}): {body}")
        except Exception as e:
            log("ERROR", f"Exception send_welcome_message: {e}")

    async def handle_jail_automation(self, data):
        if not self.config.get("ap"):
            return

        channel_id = str(data.get("channel_id", ""))
        author_data = data.get("author", {})
        author_id = str(author_data.get("id", ""))
        is_bot = author_data.get("bot", False)

        if channel_id != CHANNEL_JAIL:
            return

        embeds = data.get("embeds", [])
        if not embeds:
            return

        if author_id != BOT_UHQ_ID and not is_bot:
            return

        content = data.get("content", "")
        full_text = content
        for emb in embeds:
            full_text += " " + str(emb.get("title", ""))
            full_text += " " + str(emb.get("description", ""))
            for f in emb.get("fields", []):
                full_text += " " + str(f.get("name", "")) + " " + str(f.get("value", ""))

        user_ids = extract_prisoner_ids(full_text)
        if user_ids:
            log("INFO", f"IDs Jail extraits: {user_ids}")
            self.create_managed_task(process_jail_pings(self.session, channel_id, user_ids))

    async def process_snipe(self, data):
        msg_id = data.get("id")
        channel_id = str(data.get("channel_id", ""))
        guild_id = data.get("guild_id") or GUILD_GAV

        # Module 1 : GAV Direct
        if self.config.get("gav", True) and channel_id == CHANNEL_GAV:
            self.create_managed_task(self.process_gav_snipe(data))
            return

        components = data.get("components", [])
        buttons = self.extract_buttons(components)
        if not buttons or msg_id in self.clicked_messages:
            return

        # Module 2 : Claim Tickets
        if self.config.get("claim", True):
            if len(self.active_tickets) < 2:
                for btn in buttons:
                    if btn.get("disabled", False):
                        continue
                    label = str(btn.get("label", "")).strip().lower()
                    custom_id = str(btn.get("custom_id", "")).strip().lower()

                    if ("claim" in label or "claim" in custom_id) and "unclaim" not in label and "unclaim" not in custom_id:
                        self.track_clicked_message(msg_id)
                        self.active_tickets.add(channel_id)
                        target_guild = guild_id or GUILD_CLAIM

                        log("INFO", f"⚡ [SNIPE ULTRA-FAST] Module Claim Déclenché | Channel: {channel_id}")
                        self.create_managed_task(self.handle_claim_flow(data, btn, target_guild, channel_id))
                        return

        # Module 3 : Récupérer
        if self.config.get("recuperer", True):
            for btn in buttons:
                if btn.get("disabled", False):
                    continue
                label = str(btn.get("label", "")).lower()
                custom_id = str(btn.get("custom_id", "")).lower()
                
                if "get" in custom_id or "recuperer" in label or "récupérer" in label or "recuperer" in custom_id:
                    self.track_clicked_message(msg_id)
                    target_guild = guild_id or GUILD_RECUPERER

                    self.create_managed_task(trigger_button(self.session, data, btn, self.session_id, target_guild))
                    log("INFO", f"⚡ [SNIPE ULTRA-FAST] Module Récupérer Déclenché | Label: {btn.get('label')} | Channel: {channel_id}")
                    return

    async def handle_command(self, data):
        author_id = data.get("author", {}).get("id")
        if author_id != self.user_data.get("id"):
            return

        content = data.get("content", "").strip()
        channel_id = data.get("channel_id")

        if content == ".ping":
            lat_str = f"{self.latency_ms} ms" if self.latency_ms is not None else "Calcul en cours..."
            embed_data = {
                "title": "🏓 Pong !",
                "color": 0x5865F2,
                "fields": [
                    {"name": "Latence Gateway", "value": f"`{lat_str}`", "inline": True},
                    {"name": "Statut", "value": "🟢 Opérationnel", "inline": True}
                ],
                "footer": {"text": "Lab Selfbot System"}
            }
            self.create_managed_task(send_response(self.session, channel_id, self.user_data, "", embed_data))

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
                self.create_managed_task(send_response(self.session, channel_id, self.user_data, "", embed_data))
            elif len(parts) == 3:
                action = parts[1].lower()
                target = parts[2].lower()
                if target in ["recuperer", "claim", "gav", "ap"]:
                    if action == "on":
                        self.config[target] = True
                        self.save_config()
                        self.create_managed_task(send_response(self.session, channel_id, self.user_data, f"✅ Module **{target.upper()}** activé."))
                    elif action == "off":
                        self.config[target] = False
                        self.save_config()
                        self.create_managed_task(send_response(self.session, channel_id, self.user_data, f"🛑 Module **{target.upper()}** désactivé."))

    async def subscribe_guild_events(self, ws):
        subscribe_payload = {
            "op": 37,
            "d": {
                "subscriptions": {
                    GUILD_GAV: {
                        "typing": False,
                        "threads": True,
                        "activities": False,
                        "members": [],
                        "channels": {
                            CHANNEL_GAV: [[0, 99]]
                        }
                    }
                }
            }
        }
        await ws.send(json.dumps(subscribe_payload))
        log("INFO", f"Abonnement Gateway actif pour le salon GAV ({CHANNEL_GAV}).")

    async def start(self):
        connector = aiohttp.TCPConnector(
            limit=0,
            ttl_dns_cache=600,
            keepalive_timeout=120,
            enable_cleanup_closed=True
        )
        self.session = aiohttp.ClientSession(connector=connector)
        
        try:
            async with self.session.get(f"{BASE_URL}/users/@me", headers=HEADERS) as resp:
                if resp.status != 200:
                    log("ERROR", f"Token invalide (Status HTTP {resp.status})")
                    return
                self.user_data = await resp.json()
                log("INFO", f"Authentifié sous l'utilisateur: {self.user_data['username']} ({self.user_data['id']})")

            backoff_delay = 2
            max_backoff = 60

            while True:
                try:
                    async with websockets.connect(
                        "wss://gateway.discord.gg/?v=9&encoding=json",
                        max_size=None,
                        ping_interval=None
                    ) as ws:
                        self.ws = ws
                        backoff_delay = 2

                        hello = json.loads(await ws.recv())
                        if hello.get("op") == 10:
                            self.heartbeat_interval = hello['d']['heartbeat_interval'] / 1000
                        
                        if self.heartbeat_task:
                            self.heartbeat_task.cancel()
                        self.missed_acks = 0
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

                            op = event.get("op")
                            if op == 11:
                                self.missed_acks = 0
                                if self.last_ping_sent > 0:
                                    self.latency_ms = round((time.time() - self.last_ping_sent) * 1000)

                            if "s" in event and event["s"] is not None:
                                self.sequence_number = event["s"]

                            t = event.get("t")
                            d = event.get("d", {})

                            if t == "READY":
                                self.session_id = d.get("session_id")
                                log("INFO", f"Gateway READY | Session ID: {self.session_id}")
                                await self.subscribe_guild_events(ws)
                            elif t == "CHANNEL_DELETE":
                                ch_id = str(d.get("id"))
                                if ch_id in self.active_tickets:
                                    self.active_tickets.remove(ch_id)
                                    log("INFO", f"Ticket supprimé/fermé: {ch_id}")
                            elif t in ["MESSAGE_CREATE", "MESSAGE_UPDATE"]:
                                self.create_managed_task(self.handle_command(d))
                                self.create_managed_task(self.process_snipe(d))
                                self.create_managed_task(self.handle_jail_automation(d))

                except Exception as e:
                    if self.heartbeat_task:
                        self.heartbeat_task.cancel()
                    log("ERROR", f"Interruption Gateway: {e}. Reconnexion dans {backoff_delay}s...")
                    await asyncio.sleep(backoff_delay)
                    backoff_delay = min(backoff_delay * 2, max_backoff)
        finally:
            for task in list(self.background_tasks):
                task.cancel()
            if self.session and not self.session.closed:
                await self.session.close()

if __name__ == "__main__":
    client = LabClient()
    try:
        asyncio.run(client.start())
    except KeyboardInterrupt:
        log("INFO", "Arrêt manuel exécuté.")
