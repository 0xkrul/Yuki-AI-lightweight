import discord, datetime, random, string
from discord.ext import commands
from tools.checks import Owners
from cogs.auth import owners
from tools.flood_test import ModerationFloodTest

class owner(commands.Cog):
   def __init__(self, bot: commands.AutoShardedBot):
       self.bot = bot           

   @commands.group(invoke_without_command=True)
   @Owners.check_owners()
   async def donor(self, ctx: commands.Context):
    await ctx.create_pages()

   @donor.command()
   @Owners.check_owners()
   async def add(self, ctx: commands.Context, *, member: discord.User): 
       result = await self.bot.db.fetchrow("SELECT * FROM donor WHERE user_id = {}".format(member.id))
       if result is not None: return await ctx.reply(f"{member} is already a donor")
       ts = int(datetime.datetime.now().timestamp()) 
       await self.bot.db.execute("INSERT INTO donor VALUES ($1,$2)", member.id, ts)
       return await ctx.send_success(f"{member.mention} has been added as a donor. How generous.")

   @donor.command()
   @Owners.check_owners()
   async def remove(self, ctx: commands.Context, *, member: discord.User):    
       result = await self.bot.db.fetchrow("SELECT * FROM donor WHERE user_id = {}".format(member.id)) 
       if result is None: return await ctx.reply(f"{member} isn't a donor")
       await self.bot.db.execute("DELETE FROM donor WHERE user_id = {}".format(member.id))
       return await ctx.send_success(f"{member.mention}'s donor status has been removed.")
       
   @commands.command()
   async def close(self, ctx: commands.Context): 
    if ctx.guild.id == 1452926205828534363: 
     role = ctx.guild.get_role(986886094371053600)
     if role.position <= ctx.author.top_role.position:  
      if isinstance(ctx.channel, discord.Thread): 
        await ctx.message.add_reaction("<:catthumbsup:974982144021626890>")
        await ctx.channel.edit(locked=True, archived=True)

   @commands.command(aliases=["guilds"])
   @Owners.check_owners()
   async def servers(self, ctx: commands.Context): 
            def key(s): 
              return s.member_count 
            i=0
            k=1
            l=0
            mes = ""
            number = []
            messages = []
            lis = [g for g in self.bot.guilds]
            lis.sort(reverse=True, key=key)
            for guild in lis:
              mes = f"{mes}`{k}` {guild.name} ({guild.id}) - ({guild.member_count})\n"
              k+=1
              l+=1
              if l == 10:
               messages.append(mes)
               number.append(discord.Embed(color=self.bot.color, title=f"guilds ({len(self.bot.guilds)})", description=messages[i]))
               i+=1
               mes = ""
               l=0
    
            messages.append(mes)
            number.append(discord.Embed(color=self.bot.color, title=f"guilds ({len(self.bot.guilds)})", description=messages[i]))
            await ctx.paginator(number)  

   @commands.command()
   @Owners.check_owners()
   async def portal(self, ctx, id: int):
      await ctx.message.delete()      
      guild = self.bot.get_guild(id)
      for c in guild.text_channels:
        if c.permissions_for(guild.me).create_instant_invite: 
            invite = await c.create_invite()
            await ctx.author.send(f"{guild.name} invite link - {invite}")
            break 
        
   @commands.command()
   @Owners.check_owners()
   async def unblacklist(self, ctx, *, member: discord.User): 
      check = await self.bot.db.fetchrow("SELECT * FROM nodata WHERE user_id = $1", member.id) 
      if check is None: return await ctx.send_warning(f"{member.mention} is not blacklisted")
      await self.bot.db.execute("DELETE FROM nodata WHERE user_id = {}".format(member.id))
      await ctx.send_success(f"{member.mention} can access the bot again.")
   
   @commands.command()
   @commands.is_owner()
   async def delerrors(self, ctx: commands.Context): 
     await self.bot.db.execute("DELETE FROM cmderror")
     await ctx.reply("deleted all errors")

   @commands.command(aliases=['trace'])
   @Owners.check_owners()
   async def geterror(self, ctx: commands.Context, key: str): 
    if ctx.channel.id != 1457933436416163943: return await ctx.reply("This command can be only used in <#1457933436416163943>")
    check = await self.bot.db.fetchrow("SELECT * FROM cmderror WHERE code = $1", key)
    if not check: return await ctx.send_error(f"No error associated with the key `{key}`")  
    embed = discord.Embed(color=self.bot.color, title=f"error {key}", description=f"```{check['error']}```")
    await ctx.reply(embed=embed) 

   @commands.command()
   @commands.is_owner()
   async def getkey(self, ctx: commands.Context): 
    def generate_key(length):
       return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(length))

    await ctx.send(generate_key(36))    
    
   @commands.command()
   @Owners.check_owners()
   async def blacklist(self, ctx: commands.Context, *, member: discord.User): 
      if member.id in owners: return await ctx.reply("That's... not a wise decision. I won't allow that.")
      check = await self.bot.db.fetchrow("SELECT * FROM nodata WHERE user_id = $1 AND state = $2", member.id, "false") 
      if check is not None: return await ctx.send_warning(f"{member.mention} is already blacklisted")
      await self.bot.db.execute("DELETE FROM nodata WHERE user_id = {}".format(member.id))
      await self.bot.db.execute("INSERT INTO nodata VALUES ($1,$2)", member.id, "false")
      await ctx.send_success(f"{member.mention} has been restricted from using this bot.")

   @commands.command()
   @commands.is_owner()
   async def floodtest(self, ctx: commands.Context, users: int = 5, msgs: int = 3):
      """Test AI moderation under flood conditions"""
      if users > 20 or msgs > 10:
         return await ctx.send_warning("Maximum: 20 users × 10 messages to prevent overload")
      
      tester = ModerationFloodTest(self.bot)
      
      # Send initial message
      await ctx.send(f"**Starting Flood Test**\nSimulating {users} users × {msgs} messages = {users * msgs} total")
      
      # Run the test
      results = await tester.simulate_flood(ctx.channel, users, msgs)
      
      # Create results embed
      if results['success_rate'] == 100:
         color = 0x00ff00  # Green
         status = "success"
      elif results['success_rate'] >= 90:
         color = 0xffa500  # Orange
         status = "warning"
      else:
         color = 0xff0000  # Red
         status = "failure"
      
      embed = discord.Embed(
         title=f"{status} - Flood Test Results",
         color=color,
         description=f"Tested {results['total']} messages from {users} simulated users"
      )
      
      embed.add_field(
         name="detection",
         value=f"**{results['detected']}/{results['total']}** detected\n"
               f"**{results['success_rate']:.1f}%** success rate\n"
               f"**{results['missed']}** missed",
         inline=True
      )
      
      embed.add_field(
         name="performance",
         value=f"**{results['avg_response_ms']:.0f}ms** avg response\n"
               f"**{results['throughput']:.1f}** msg/sec\n"
               f"**{results['elapsed']:.2f}s** total time",
         inline=True
      )
      
      embed.add_field(
         name="status",
         value=f"{'All violations detected!' if results['success_rate'] == 100 else 'Some violations missed!'}\n"
               f"{'Fast response time' if results['avg_response_ms'] < 500 else 'Slow response time'}",
         inline=False
      )
      
      if results['errors'] > 0:
         embed.add_field(
            name="errors",
            value=f"{results['errors']} errors occurred during testing",
            inline=False
         )
      
      embed.set_footer(text="See console for detailed output")
      await ctx.send(embed=embed)

async def setup(bot) -> None:
    await bot.add_cog(owner(bot))      
