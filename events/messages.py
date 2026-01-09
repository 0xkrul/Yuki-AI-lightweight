from discord.ext import commands
import discord

class Messages(commands.Cog):
    def __init__(self, bot: commands.AutoShardedBot):
        self.bot = bot
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Minimal - AI moderation handles this in its own cog
        pass

async def setup(bot: commands.AutoShardedBot) -> None:
    await bot.add_cog(Messages(bot))
