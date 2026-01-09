"""
AI MODERATION FLOOD TESTING UTILITY
====================================
Test how the bot handles multiple simultaneous violations
"""

import asyncio
import time
from typing import List

class ModerationFloodTest:
    """Test AI moderation under flood conditions"""
    
    def __init__(self, bot):
        self.bot = bot
        self.test_results = []
    
    async def simulate_flood(self, channel, num_users: int = 5, messages_per_user: int = 3):
        """
        Simulate flood attack with multiple users spamming violations
        
        Args:
            channel: Discord channel to test in
            num_users: Number of simulated users (default 5)
            messages_per_user: Messages each user sends (default 3)
        """
        print(f"🧪 Starting flood test: {num_users} users × {messages_per_user} messages")
        print("=" * 60)
        
        # Test messages with violations - using guaranteed triggers
        test_messages = [
            "nigger retard faggot",  # Hard-coded hate speech (guaranteed catch)
            "kys yourself loser",  # Self-harm encouragement (guaranteed catch)
            "192.168.1.1 is my ip address",  # PII - IP address (guaranteed catch)
        ]
        
        # Create fake message objects
        class FakeMessage:
            def __init__(self, content, user_id):
                self.content = content
                self.author = type('Author', (), {'id': user_id, 'bot': False})()
                self.guild = channel.guild
                self.channel = channel
                self.mentions = []
                self.role_mentions = []
        
        # Get AI moderation cog
        mod_cog = self.bot.get_cog("LocalPolicyModeration")
        if not mod_cog:
            print("❌ AI Moderation cog not loaded!")
            return
        
        start_time = time.time()
        tasks = []
        
        # Create concurrent tasks
        for user_id in range(1000, 1000 + num_users):
            for msg_idx in range(messages_per_user):
                content = test_messages[msg_idx % len(test_messages)]
                fake_msg = FakeMessage(content, user_id)
                
                # Schedule moderation check
                task = asyncio.create_task(
                    self._test_single_message(mod_cog, fake_msg, user_id, msg_idx)
                )
                tasks.append(task)
        
        # Wait for all to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        elapsed = time.time() - start_time
        
        # Analyze results
        total_messages = num_users * messages_per_user
        detected = sum(1 for r in results if r and r.get('detected'))
        missed = sum(1 for r in results if r and not r.get('detected'))
        errors = sum(1 for r in results if isinstance(r, Exception))
        
        print("\n" + "=" * 60)
        print("📊 FLOOD TEST RESULTS")
        print("=" * 60)
        print(f"Total Messages: {total_messages}")
        print(f"✅ Detected: {detected} ({detected/total_messages*100:.1f}%)")
        print(f"❌ Missed: {missed} ({missed/total_messages*100:.1f}%)")
        print(f"⚠️ Errors: {errors}")
        print(f"⏱️ Total Time: {elapsed:.2f}s")
        print(f"📈 Throughput: {total_messages/elapsed:.1f} msg/sec")
        print(f"⚡ Avg Response Time: {elapsed/total_messages*1000:.0f}ms per message")
        
        # Success criteria
        print("\n" + "=" * 60)
        if detected == total_messages:
            print("✅ SUCCESS: 100% detection rate achieved!")
        else:
            print(f"⚠️ WARNING: {missed} violations missed ({missed/total_messages*100:.1f}%)")
        
        if elapsed / total_messages < 0.5:  # <500ms per message
            print("✅ SUCCESS: Fast response time (<500ms avg)")
        else:
            print(f"⚠️ WARNING: Slow response time ({elapsed/total_messages*1000:.0f}ms avg)")
        
        print("=" * 60)
        
        return {
            'total': total_messages,
            'detected': detected,
            'missed': missed,
            'errors': errors,
            'elapsed': elapsed,
            'throughput': total_messages / elapsed,
            'avg_response_ms': elapsed / total_messages * 1000,
            'success_rate': detected / total_messages * 100
        }
    
    async def _test_single_message(self, mod_cog, message, user_id, msg_idx):
        """Test a single message for moderation"""
        start = time.time()
        
        try:
            reason = await mod_cog.should_moderate(message)
            elapsed = time.time() - start
            
            detected = reason is not None
            
            if detected:
                status = "✅ DETECTED"
            else:
                status = "❌ MISSED"
            
            result = {
                'user_id': user_id,
                'msg_idx': msg_idx,
                'content': message.content[:30] + "...",
                'detected': detected,
                'reason': reason,
                'response_time_ms': elapsed * 1000,
                'status': status
            }
            
            # Print ALL results for debugging
            print(f"{status} User{user_id} Msg{msg_idx}: '{message.content[:40]}' - {elapsed*1000:.0f}ms - {reason or 'NONE'}")
            
            return result
            
        except Exception as e:
            print(f"⚠️ ERROR User{user_id} Msg{msg_idx}: {e}")
            return {'user_id': user_id, 'msg_idx': msg_idx, 'error': str(e), 'detected': False}


# Usage in bot:
# from tools.flood_test import ModerationFloodTest
# 
# @bot.command()
# @commands.is_owner()
# async def floodtest(ctx, users: int = 5, msgs: int = 3):
#     """Test AI moderation under flood conditions"""
#     tester = ModerationFloodTest(bot)
#     await ctx.send(f"🧪 Starting flood test: {users} users × {msgs} messages...")
#     results = await tester.simulate_flood(ctx.channel, users, msgs)
#     
#     embed = discord.Embed(
#         title="Flood Test Results",
#         color=0x00ff00 if results['success_rate'] == 100 else 0xff0000
#     )
#     embed.add_field(name="Detection Rate", value=f"{results['success_rate']:.1f}%")
#     embed.add_field(name="Throughput", value=f"{results['throughput']:.1f} msg/s")
#     embed.add_field(name="Avg Response", value=f"{results['avg_response_ms']:.0f}ms")
#     await ctx.send(embed=embed)
