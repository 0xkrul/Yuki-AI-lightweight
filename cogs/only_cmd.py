import discord
import asyncio
from discord.ext import commands
from tools.checks import Perms


class OnlyCmd(commands.Cog):
    def __init__(self, bot: commands.AutoShardedBot):
        self.bot = bot

    @commands.Cog.listener('on_message')
    async def delete_non_bot_messages(self, message: discord.Message):
        if not message.guild:
            return
        if message.author.bot:
            return
        
        # OPTIMIZATION: Check cache first
        from entry import guild_config_cache
        cached_channels = guild_config_cache.get_only_cmd(message.guild.id)
        
        if cached_channels is None:
            # Load from DB and cache
            rows = await self.bot.db.fetch(
                "SELECT channel_id FROM only_cmd WHERE guild_id = $1",
                message.guild.id
            )
            cached_channels = {row['channel_id'] for row in rows}
            guild_config_cache.set_only_cmd(message.guild.id, cached_channels)
        
        if message.channel.id not in cached_channels:
            return
        
        # CRITICAL: Fire-and-forget deletion to avoid blocking event loop
        asyncio.create_task(self._delete_after_delay(message))
    
    async def _delete_after_delay(self, message: discord.Message):
        """Non-blocking deletion with delay"""
        await asyncio.sleep(1)
        try:
            await message.delete()
        except (discord.NotFound, discord.Forbidden):
            pass

    @commands.hybrid_group(name="onlycmd", invoke_without_command=True, aliases=["only-cmd", "cmdonly"])
    async def only_cmd(self, ctx: commands.Context):
        await ctx.create_pages()

    @only_cmd.command(name="enable", description="enable only-cmd mode in a channel (deletes non-bot messages)", help="automod", brief="manage guild", usage="[channel]")
    @Perms.get_perms("manage_guild")
    async def only_cmd_enable(self, ctx: commands.Context, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        check = await self.bot.db.fetchrow(
            "SELECT * FROM only_cmd WHERE guild_id = $1 AND channel_id = $2",
            ctx.guild.id, channel.id
        )
        if check:
            return await ctx.send_warning(f"Only-cmd is **already** enabled in {channel.mention}")
        await self.bot.db.execute(
            "INSERT INTO only_cmd VALUES ($1, $2)",
            ctx.guild.id, channel.id
        )
        # Invalidate cache
        from entry import guild_config_cache
        guild_config_cache.invalidate_only_cmd(ctx.guild.id)
        return await ctx.send_success(f"Only-cmd is now enabled in {channel.mention}. Non-bot messages will be deleted after 1 second")

    @only_cmd.command(name="disable", description="disable only-cmd mode in a channel", help="automod", brief="manage guild", usage="[channel]")
    @Perms.get_perms("manage_guild")
    async def only_cmd_disable(self, ctx: commands.Context, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        check = await self.bot.db.fetchrow(
            "SELECT * FROM only_cmd WHERE guild_id = $1 AND channel_id = $2",
            ctx.guild.id, channel.id
        )
        if not check:
            return await ctx.send_warning(f"Only-cmd is **not** enabled in {channel.mention}")
        await self.bot.db.execute(
            "DELETE FROM only_cmd WHERE guild_id = $1 AND channel_id = $2",
            ctx.guild.id, channel.id
        )
        # Invalidate cache
        from entry import guild_config_cache
        guild_config_cache.invalidate_only_cmd(ctx.guild.id)
        return await ctx.send_success(f"Only-cmd is now disabled in {channel.mention}")

    @only_cmd.command(name="list", description="list all channels with only-cmd enabled", help="automod")
    async def only_cmd_list(self, ctx: commands.Context):
        results = await self.bot.db.fetch(
            "SELECT * FROM only_cmd WHERE guild_id = $1",
            ctx.guild.id
        )
        if len(results) == 0:
            return await ctx.send_warning("No channels have **only-cmd** enabled")
        
        channels = []
        for i, result in enumerate(results, 1):
            channel = ctx.guild.get_channel(result['channel_id'])
            if channel:
                channels.append(f"`{i}` {channel.mention}")
        
        if not channels:
            return await ctx.send_warning("No channels have **only-cmd** enabled")
        
        embed = discord.Embed(
            color=self.bot.color,
            title=f"Only-cmd channels ({len(channels)})",
            description="\n".join(channels)
        )
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(OnlyCmd(bot))

