import discord, random
from discord.ext import commands
from discord.ui import View, Button

class info(commands.Cog):
   def __init__(self, bot: commands.AutoShardedBot):
        self.bot = bot        

   @commands.hybrid_command(description="check how long the bot has been online for", help="info")
   async def uptime(self, ctx: commands.Context):
     e = discord.Embed(color=self.bot.color, description=f"I've been operational for **{self.bot.ext.uptime}**. Efficient, wouldn't you say?")
     await ctx.reply(embed=e)

   @commands.hybrid_command(help="info", description="shows bot information", aliases=["about", "info", "bi"]) 
   async def botinfo(self, ctx: commands.Context):
    embed = discord.Embed(color=self.bot.color, title="stats", description=f">>> • ping `{self.bot.ping}`\n• uptime `{(self.bot.ext.uptime.split(','))[0]}`\n• version `{discord.__version__}`\n• commands `{len(set(self.bot.walk_commands()))}`\n• guilds `{len(self.bot.guilds)}`\n• members `{sum(g.member_count for g in self.bot.guilds):,}`")   
    await ctx.reply(embed=embed)
    
   @commands.hybrid_command(description="check bot connection", help="info")
   async def ping(self, ctx):
    await ctx.reply(f"Response time: `{self.bot.ping}ms`. Satisfactory.")
   
   @commands.hybrid_command(description="show credits to contributors of the bot", help="info")
   async def credits(self, ctx: commands.Context): 
     embed = discord.Embed(color=self.bot.color, description=f">>> **{self.bot.get_user(1406842730587623556)}** - the one who made this possible").set_author(icon_url=self.bot.user.display_avatar, name="yuki credits")
     await ctx.reply(embed=embed)

   @commands.hybrid_command(description="invite the bot", help="info", aliases=["support", "inv"])
   async def invite(self, ctx):
    avatar_url = self.bot.user.avatar.url
    embed = discord.Embed(color=self.bot.color, description="Add the bot in your server!")
    embed.set_author(name=self.bot.user.name, icon_url=f"{avatar_url}")
    button1 = Button(label="invite", url=f"https://discord.com/api/oauth2/authorize?client_id={self.bot.user.id}&permissions=8&scope=bot%20applications.commands")
    button2 = Button(label="support", url="https://https://discord.gg/ZTTXMkk8ua")
    view = View()
    view.add_item(button1)
    view.add_item(button2)
    await ctx.reply(embed=embed, view=view)

async def setup(bot) -> None:
    await bot.add_cog(info(bot))      
