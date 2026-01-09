import os, time, discord, asyncpg, random, string, datetime
from discord.ext import commands
from discord.gateway import DiscordWebSocket
from tools.utils import StartUp, create_db
from tools.ext import Client, HTTP
from humanfriendly import format_timespan
from typing import List, Optional, Set
from tools.utils import PaginatorView
from io import BytesIO 
import dotenv
from pathlib import Path
import asyncio

dotenv.load_dotenv(Path(__file__).parent / '.env', verbose=True)
token = os.environ['token']

# Guild configuration cache
class GuildConfigCache:
    """Simple cache for guild configurations"""
    def __init__(self):
        self._only_cmd = {}  # {guild_id: set(channel_ids)}
    
    def get_only_cmd(self, guild_id: int) -> Optional[Set[int]]:
        return self._only_cmd.get(guild_id)
    
    def set_only_cmd(self, guild_id: int, channel_ids: Set[int]):
        self._only_cmd[guild_id] = channel_ids
    
    def clear_only_cmd(self, guild_id: int):
        self._only_cmd.pop(guild_id, None)

guild_config_cache = GuildConfigCache()

def generate_key():
    return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(6))

async def checkthekey(key: str):
    check = await bot.db.fetchrow("SELECT * FROM cmderror WHERE code = $1", key)
    if check: 
        newkey = generate_key()
        return await checkthekey(newkey)
    return key  

DiscordWebSocket.identify = StartUp.identify

os.environ["JISHAKU_NO_UNDERSCORE"] = "True"
os.environ["JISHAKU_NO_DM_TRACEBACK"] = "True"
os.environ["JISHAKU_HIDE"] = "True"
os.environ["JISHAKU_FORCE_PAGINATOR"] = "True"
os.environ["JISHAKU_RETAIN"] = "True"

async def getprefix(bot, message):
    if not message.guild: 
        return ";"
    
    check = await bot.db.fetchrow("SELECT prefix FROM prefixes WHERE guild_id = $1", message.guild.id)
    if check is not None:
        return check['prefix']
    return ";"

intents = discord.Intents.all()

class NeoContext(commands.Context): 
    def __init__(self, **kwargs): 
        super().__init__(**kwargs) 

    def find_role(self, name: str): 
        for role in self.guild.roles:
            if role.name == "@everyone": continue  
            if name.lower() in role.name.lower(): return role 
        return None 
 
    async def send_success(self, message: str) -> discord.Message:  
        return await self.reply(embed=discord.Embed(color=0x3ba55d, description=f"{self.bot.yes} {self.author.mention}: {message}"))
 
    async def send_error(self, message: str) -> discord.Message: 
        return await self.reply(embed=discord.Embed(color=0xed4245, description=f"{self.bot.no} {self.author.mention}: {message}"))
 
    async def send_warning(self, message: str) -> discord.Message: 
        return await self.reply(embed=discord.Embed(color=0xfaa81a, description=f"{self.bot.warning} {self.author.mention}: {message}"))
 
    async def paginator(self, embeds: List[discord.Embed]):
        if len(embeds) == 1: return await self.send(embed=embeds[0]) 
        view = PaginatorView(self, embeds)
        view.message = await self.reply(embed=embeds[0], view=view) 
 
    async def cmdhelp(self): 
        command = self.command
        commandname = f"{str(command.parent)} {command.name}" if str(command.parent) != "None" else command.name
        if command.cog_name == "owner": return
        embed = discord.Embed(color=bot.color, title=commandname, description=command.description)
        embed.set_author(name=bot.user.name, icon_url=bot.user.avatar.url)
        embed.add_field(name="category", value=command.help)
        embed.add_field(name="aliases", value=', '.join(map(str, command.aliases)) or "none")
        embed.add_field(name="permissions", value=command.brief or "any")
        embed.add_field(name="usage", value=f"```{commandname} {command.usage if command.usage else ''}```", inline=False)
        await self.reply(embed=embed)

    async def create_pages(self): 
        embeds = []
        i = 0
        for command in self.command.commands: 
            commandname = f"{str(command.parent)} {command.name}" if str(command.parent) != "None" else command.name
            i += 1 
            embeds.append(discord.Embed(color=bot.color, title=f"{commandname}", description=command.description).set_author(name=bot.user.name, icon_url=bot.user.display_avatar.url).add_field(name="usage", value=f"```{commandname} {command.usage if command.usage else ''}```", inline=False).set_footer(text=f"aliases: {', '.join(a for a in command.aliases) if len(command.aliases) > 0 else 'none'} ・ {i}/{len(self.command.commands)}"))
     
        return await self.paginator(embeds)  

class HelpCommand(commands.HelpCommand):
    def __init__(self, **kwargs):
        self.categories = {
            "home": "return to the main page", 
            "info": "view information about the bot", 
            "moderation": "AI and manual moderation tools", 
            "antinuke": "protect your server against unfaithful admins"
        } 
        super().__init__(**kwargs)
  
    async def send_bot_help(self, mapping):
        embed = discord.Embed(color=self.context.bot.color, title="yuki AI Moderation") 
        embed.add_field(name="help", value="Use the **dropdown** menu below to view commands", inline=False) 
        embed.set_author(name=self.context.author.name, icon_url=self.context.author.display_avatar.url)
        embed.set_footer(text=f"command count: {len(set(bot.walk_commands()))}")
        options = []
        for c in self.categories: 
            options.append(discord.SelectOption(label=c, description=self.categories.get(c)))
        select = discord.ui.Select(options=options, placeholder="Select a category")

        async def select_callback(interaction: discord.Interaction): 
            if interaction.user.id != self.context.author.id: 
                return await self.context.bot.ext.send_warning(interaction, "You are not the author of this embed", ephemeral=True)
            if select.values[0] == "home": 
                return await interaction.response.edit_message(embed=embed)
            com = []
            for c in [cm for cm in set(bot.walk_commands()) if cm.help == select.values[0]]:
                if c.parent: 
                    if str(c.parent) in com: continue 
                    com.append(str(c.parent))
                else: 
                    com.append(c.name)  
            e = discord.Embed(color=bot.color, title=f"{select.values[0]} commands", description=f"```{', '.join(com)}```").set_author(name=self.context.author.name, icon_url=self.context.author.display_avatar.url)  
            return await interaction.response.edit_message(embed=e)
        
        select.callback = select_callback

        view = discord.ui.View(timeout=None)
        view.add_item(select) 
        return await self.context.reply(embed=embed, view=view)
  
    async def send_command_help(self, command: commands.Command): 
        commandname = f"{str(command.parent)} {command.name}" if str(command.parent) != "None" else command.name
        if command.cog_name == "owner": return
        embed = discord.Embed(color=bot.color, title=commandname, description=command.description)
        embed.set_author(name=bot.user.name, icon_url=bot.user.avatar.url)
        embed.add_field(name="category", value=command.help)
        embed.add_field(name="aliases", value=', '.join(map(str, command.aliases)) or "none")
        embed.add_field(name="permissions", value=command.brief or "any")
        embed.add_field(name="usage", value=f"```{commandname} {command.usage if command.usage else ''}```", inline=False)
        channel = self.get_destination()
        await channel.send(embed=embed)

    async def send_group_help(self, group: commands.Group): 
        ctx = self.context
        embeds = []
        i = 0
        for command in group.commands: 
            commandname = f"{str(command.parent)} {command.name}" if str(command.parent) != "None" else command.name
            i += 1 
            embeds.append(discord.Embed(color=bot.color, title=f"{commandname}", description=command.description).set_author(name=bot.user.name, icon_url=bot.user.display_avatar.url).add_field(name="usage", value=f"```{commandname} {command.usage if command.usage else ''}```", inline=False).set_footer(text=f"aliases: {', '.join(a for a in command.aliases) if len(command.aliases) > 0 else 'none'} ・ {i}/{len(group.commands)}"))
     
        return await ctx.paginator(embeds) 

class CommandClient(commands.AutoShardedBot):
    def __init__(self):
        super().__init__(
            shard_count=2,
            command_prefix=getprefix, 
            allowed_mentions=discord.AllowedMentions(roles=False, everyone=False, users=True, replied_user=False), 
            intents=intents, 
            help_command=HelpCommand(), 
            strip_after_prefix=True, 
            activity=discord.Activity(name="AI Moderation", type=discord.ActivityType.watching), 
            owner_ids=[1406842730587623556],
            max_messages=500,
            chunk_guilds_at_startup=False,
            member_cache_flags=discord.MemberCacheFlags.none()
        )
        self.uptime = time.time()
        self.cogs_loaded = False
        self.color = 0x6d827d
        
        self.yes = "✅"
        self.no = "❌"
        self.warning = "⚠️"
        
        self.left = "<:left:1018156480991612999>"
        self.right = "<:right:1018156484170883154>"
        self.goto = "<:filter:1039235211789078628>"
        self.proxy_url = "http://dtgrlmjf-rotate:p0bl5bes07qp@p.webshare.io:80"
        self.m_cd = commands.CooldownMapping.from_cooldown(3, 5, commands.BucketType.member)
        self.global_cd = commands.CooldownMapping.from_cooldown(5, 3, commands.BucketType.member)
        self.ext = Client(self) 
        
    async def create_db_pool(self):
        """Create optimized database connection pool"""
        self.db = await asyncpg.create_pool(
            host="localhost",
            port=5432,
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME"),
            min_size=5,
            max_size=20,
            max_queries=50000,
            max_inactive_connection_lifetime=300,
            command_timeout=30,
            statement_cache_size=200,
        )
        print("✓ Database pool created")
    
    async def get_context(self, message, *, cls=NeoContext):
        return await super().get_context(message, cls=cls)

    async def setup_hook(self) -> None:
        """Minimal setup"""
        print("Starting yuki AI Moderation Bot...")
        self.session = HTTP()
        await self.create_db_pool()
        asyncio.create_task(self.load_extension("jishaku"))
        asyncio.create_task(StartUp.startup(bot))     
    
    @property
    def ping(self) -> int: 
        if self.latency == float('inf') or self.latency == float('-inf'):
            return 0
        return round(self.latency * 1000) 
    
    def is_dangerous(self, role: discord.Role) -> bool:
        permissions = role.permissions
        return any([
            permissions.kick_members, permissions.ban_members,
            permissions.administrator, permissions.manage_channels,
            permissions.manage_guild, permissions.manage_messages,
            permissions.manage_roles, permissions.manage_webhooks,
            permissions.manage_emojis_and_stickers, permissions.manage_threads,
            permissions.mention_everyone, permissions.moderate_members
        ])
    
    async def prefixes(self, message: discord.Message) -> List[str]: 
        return [await self.command_prefix(self, message)]

    async def on_ready(self):
        asyncio.create_task(create_db(self))
        
        if self.cogs_loaded == False:
            self.cogs_loaded = True
            await StartUp.loadcogs(self)
       
        print(f"✓ Connected as {self.user} ({self.user.id})")
        
        # Wait a moment for latency to stabilize
        await asyncio.sleep(2)
        
        # Check if latency is valid
        if self.ping > 0 and self.ping < 5000:
            print(f"✓ Latency: {self.ping}ms")
        else:
            print(f"✓ Latency: Measuring...")
            
        print(f"✓ Guilds: {len(self.guilds)}")
        print(f"✓ AI Moderation Ready")
    
    async def on_message_edit(self, before, after):
        if before.content != after.content: 
            await self.process_commands(after)

    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        
        await self.process_commands(message)
        
        if message.content == f"<@{self.user.id}>": 
            prefix = await self.command_prefix(self, message)
            await message.reply(content=f"prefix: `{prefix}`")

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.CommandNotFound): 
            return 
        elif isinstance(error, commands.NotOwner): 
            pass
        elif isinstance(error, commands.CheckFailure): 
            if isinstance(error, commands.MissingPermissions): 
                return await ctx.send_warning(f"Missing **{error.missing_permissions[0]}** permission")
        elif isinstance(error, commands.CommandOnCooldown):
            return await ctx.reply(embed=discord.Embed(color=0xE1C16E, description=f"⌛ {ctx.author.mention}: Cooldown. Try again in {format_timespan(error.retry_after)}"), mention_author=False)    
        elif isinstance(error, commands.MissingRequiredArgument):
            return await ctx.cmdhelp()
        elif isinstance(error, commands.EmojiNotFound):
            return await ctx.send_warning(f"Unable to convert {error.argument} into an emoji")
        elif isinstance(error, commands.MemberNotFound):
            return await ctx.send_warning(f"Unable to find member **{error.argument}**")
        elif isinstance(error, commands.UserNotFound):
            return await ctx.send_warning(f"Unable to find user **{error.argument}**")
        elif isinstance(error, commands.RoleNotFound):
            return await ctx.send_warning(f"Couldn't find role **{error.argument}**")
        elif isinstance(error, commands.ChannelNotFound):
            return await ctx.send_warning(f"Couldn't find channel **{error.argument}**")
        elif isinstance(error, commands.BadArgument):
            return await ctx.send_warning(error.args[0])
        elif isinstance(error, commands.BotMissingPermissions):
            return await ctx.send_warning("I don't have enough permissions")
        elif isinstance(error, discord.HTTPException):
            return await ctx.send_warning("Unable to execute this command")
        else:
            import traceback
            traceback.print_exception(type(error), error, error.__traceback())

            key = await checkthekey(generate_key())
            await self.db.execute("INSERT INTO cmderror VALUES ($1,$2)", key, str(error))
            await self.ext.send_error(ctx, f"Error code: `{key}`. Report in support server")

bot = CommandClient()

@bot.check
async def cooldown_check(ctx: commands.Context):
    bucket = bot.global_cd.get_bucket(ctx.message)
    retry_after = bucket.update_rate_limit()
    if retry_after: 
        raise commands.CommandOnCooldown(bucket, retry_after, commands.BucketType.member)
    return True

@bot.check
async def is_chunked(ctx: commands.Context):
    if ctx.guild and not ctx.guild.chunked: 
        await ctx.guild.chunk(cache=True)
    return True

if __name__ == '__main__':
    print("=" * 50)
    print("YUKI AI MODERATION BOT")
    print("=" * 50)
    bot.run(token)
