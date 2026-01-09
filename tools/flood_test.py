"""
AI MODERATION FLOOD TESTING UTILITY
====================================
Test how the optimized bot handles multiple simultaneous violations
"""

import asyncio
import time
from typing import List, Dict


class ModerationFloodTest:
    """Test AI moderation under flood conditions with actual violations"""
    
    def __init__(self, bot):
        self.bot = bot
        self.test_results = []
    
    async def simulate_flood(self, channel, num_users: int = 5, messages_per_user: int = 3) -> Dict:
        """
        Simulate flood attack with multiple users spamming violations
        
        Args:
            channel: Discord channel to test in
            num_users: Number of simulated users (default 5)
            messages_per_user: Messages each user sends (default 3)
            
        Returns:
            dict with comprehensive test results
        """
        print(f"🧪 Starting flood test: {num_users} users × {messages_per_user} messages")
        print("=" * 60)
        
        # Test messages with GUARANTEED violations
        test_messages = [
            "nigger retard faggot",  # Hate speech (guaranteed catch)
            "kys yourself loser",  # Self-harm (guaranteed catch)
            "192.168.1.1 is my ip address",  # PII - IP (guaranteed catch)
            "im gonna kill you",  # Threat (guaranteed catch)
            "send nudes pussy pics",  # Sexual harassment (guaranteed catch)
            "join my discord discord.gg/test",  # Self-promo (guaranteed catch)
        ]
        
        # Create fake message objects for testing
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
            return {
                'success_rate': 0,
                'throughput': 0,
                'avg_response_ms': 0,
                'detected': 0,
                'total': 0,
                'missed': 0,
                'errors': 1,
                'elapsed': 0
            }
        
        # Run flood test
        start_time = time.time()
        detected = 0
        total = 0
        response_times = []
        errors = 0
        
        for user_id in range(1000, 1000 + num_users):
            for _ in range(messages_per_user):
                total += 1
                test_msg = test_messages[total % len(test_messages)]
                fake_msg = FakeMessage(test_msg, user_id)
                
                try:
                    # Time the detection
                    msg_start = time.time()
                    reason = await mod_cog.should_moderate(fake_msg)
                    msg_end = time.time()
                    
                    response_ms = (msg_end - msg_start) * 1000
                    response_times.append(response_ms)
                    
                    if reason:
                        detected += 1
                        print(f"✅ User {user_id}: Detected '{test_msg[:30]}...' ({response_ms:.1f}ms) - {reason}")
                    else:
                        print(f"❌ User {user_id}: MISSED '{test_msg[:30]}...' ({response_ms:.1f}ms)")
                
                except Exception as e:
                    errors += 1
                    print(f"⚠️  Error testing message: {e}")
                
                # Small delay to simulate realistic timing
                await asyncio.sleep(0.01)
        
        elapsed = time.time() - start_time
        success_rate = (detected / total * 100) if total > 0 else 0
        avg_response_ms = sum(response_times) / len(response_times) if response_times else 0
        throughput = total / elapsed if elapsed > 0 else 0
        
        print("=" * 60)
        print(f"📊 Test Complete!")
        print(f"   Detection Rate: {detected}/{total} ({success_rate:.1f}%)")
        print(f"   Avg Response: {avg_response_ms:.1f}ms")
        print(f"   Throughput: {throughput:.1f} messages/second")
        print(f"   Total Time: {elapsed:.2f}s")
        print("=" * 60)
        
        return {
            'success_rate': success_rate,
            'throughput': throughput,
            'avg_response_ms': avg_response_ms,
            'detected': detected,
            'total': total,
            'missed': total - detected,
            'errors': errors,
            'elapsed': elapsed
        }
    
    async def cleanup_test_messages(self, messages: List):
        """Delete test messages after testing"""
        for msg in messages:
            try:
                await msg.delete()
            except:
                pass
