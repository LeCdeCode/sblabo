import discord
from discord.ext import commands
import json
import os
import asyncio

TOKEN = "MTU0MjU2OTczNDkyNTU5MDUzOA.G9Cf8s.yddQx7HA2R4o_s9XDFVfw3fb9SGkXJtho5anGM"

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="+", intents=intents)
BACKUP_FILE = "guild_backups.json"

def load_backups():
    if os.path.exists(BACKUP_FILE):
        try:
            with open(BACKUP_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_backups(data):
    with open(BACKUP_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

@bot.event
async def on_ready():
    print(f"[+] Bot Officiel Connecté : {bot.user.name} ({bot.user.id})")

@bot.command(name="clear")
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int):
    await ctx.message.delete()
    deleted_total = 0
    while amount > 0:
        batch = min(amount, 100)
        deleted = await ctx.channel.purge(limit=batch)
        if not deleted:
            break
        deleted_total += len(deleted)
        amount -= len(deleted)
        await asyncio.sleep(1)

    confirm = await ctx.send(f"✅ `{deleted_total}` messages supprimés.")
    await asyncio.sleep(3)
    await confirm.delete()

@bot.command(name="liste", aliases=["list"])
async def list_backups(ctx):
    backups = load_backups()
    if not backups:
        await ctx.send("📋 Aucune sauvegarde trouvée.")
        return

    embed = discord.Embed(title="📋 Sauvegardes Disponibles", color=0x3498DB)
    for idx, b in enumerate(backups, 1):
        name = b.get("guild_name", "Inconnu")
        embed.add_field(
            name=f"Slot #{idx} | `{b['guild_id']}` ({name})",
            value=f"• Rôles: `{len(b.get('roles', []))}` | Salons: `{len(b.get('channels', []))}`",
            inline=False
        )
    await ctx.send(embed=embed)

@bot.command(name="del")
async def delete_backup(ctx, slot: int):
    backups = load_backups()
    idx = slot - 1
    if 0 <= idx < len(backups):
        removed = backups.pop(idx)
        save_backups(backups)
        await ctx.send(f"🗑️ Sauvegarde Slot **#{slot}** (`{removed['guild_id']}`) supprimée.")
    else:
        await ctx.send("⚠️ Numéro de slot invalide.")

@bot.command(name="past", aliases=["paste"])
@commands.has_permissions(administrator=True)
async def paste_structure(ctx, target: str = None):
    backup_data = None

    if ctx.message.attachments:
        attachment = ctx.message.attachments[0]
        if attachment.filename.endswith(".json"):
            content = await attachment.read()
            backup_data = json.loads(content.decode("utf-8"))

    if not backup_data and target:
        backups = load_backups()
        if target.isdigit() and len(target) < 5:
            idx = int(target) - 1
            if 0 <= idx < len(backups):
                backup_data = backups[idx]
        else:
            backup_data = next((b for b in backups if str(b["guild_id"]) == target), None)

    if not backup_data:
        await ctx.send("❌ Aucune donnée de sauvegarde valide trouvée.")
        return

    guild = ctx.guild
    await ctx.send("⏳ **Injection 1:1 en cours (Rôles, Salons, Slowmode, Dérogations)...**")

    # 1. Suppression des salons actuels
    for channel in guild.channels:
        try:
            await channel.delete()
            await asyncio.sleep(0.2)
        except Exception:
            pass

    # 2. Re-création des Rôles & Mapping
    roles_map = {guild.default_role.id: guild.default_role}
    sorted_roles = sorted(backup_data.get("roles", []), key=lambda x: x.get("position", 0))

    for r in sorted_roles:
        if r["name"] == "@everyone":
            roles_map[r["id"]] = guild.default_role
            continue
        try:
            new_role = await guild.create_role(
                name=r["name"],
                permissions=discord.Permissions(int(r.get("permissions", 0))),
                color=discord.Color(r.get("color", 0)),
                hoist=r.get("hoist", False),
                mentionable=r.get("mentionable", False)
            )
            roles_map[r["id"]] = new_role
            await asyncio.sleep(0.2)
        except Exception:
            pass

    # 3. Re-création des Catégories & Dérogations
    categories_map = {}
    channels_sorted = sorted(backup_data.get("channels", []), key=lambda c: c.get("position", 0))

    for c in channels_sorted:
        if c["type"] == 4: # Catégorie
            overwrites = {}
            for ow in c.get("permission_overwrites", []):
                target_obj = roles_map.get(ow["id"])
                if target_obj:
                    allow_perm = discord.Permissions(int(ow.get("allow", 0)))
                    deny_perm = discord.Permissions(int(ow.get("deny", 0)))
                    overwrites[target_obj] = discord.PermissionOverwrite.from_pair(allow_perm, deny_perm)

            cat = await guild.create_category(name=c["name"], overwrites=overwrites)
            categories_map[c["id"]] = cat
            await asyncio.sleep(0.2)

    # 4. Re-création des Salons Textuels & Vocaux
    for c in channels_sorted:
        if c["type"] != 4:
            parent = categories_map.get(c.get("parent_id"))
            overwrites = {}
            for ow in c.get("permission_overwrites", []):
                target_obj = roles_map.get(ow["id"])
                if target_obj:
                    allow_perm = discord.Permissions(int(ow.get("allow", 0)))
                    deny_perm = discord.Permissions(int(ow.get("deny", 0)))
                    overwrites[target_obj] = discord.PermissionOverwrite.from_pair(allow_perm, deny_perm)

            if c["type"] == 0: # Text
                await guild.create_text_channel(
                    name=c["name"],
                    category=parent,
                    topic=c.get("topic"),
                    slowmode_delay=c.get("rate_limit_per_user", 0),
                    nsfw=c.get("nsfw", False),
                    overwrites=overwrites
                )
            elif c["type"] == 2: # Voice
                await guild.create_voice_channel(
                    name=c["name"],
                    category=parent,
                    bitrate=c.get("bitrate") or 64000,
                    user_limit=c.get("user_limit", 0),
                    overwrites=overwrites
                )
            await asyncio.sleep(0.2)

    await ctx.send("✅ **Structure collée 1:1 avec succès !**")

bot.run(TOKEN)
