"""
Flood Test Utility for Testing Moderation Performance
"""
import asyncio
import time
from typing import List, Optional
import discord


class ModerationFloodTest:
    """Test moderation system with simulated message floods"""
    
    def __init__(self, bot):
        self.bot = bot
        self.test_messages = [
            "This is a test message",
            "Another test message here",
            "Testing the moderation system",
            "Flood test in progress",
            "Performance test message"
        ]
    
    async def simulate_flood(
        self, 
        channel: discord.TextChannel, 
        count: int = 10,
        delay: float = 0.1
    ) -> dict:
        """
        Simulate a message flood for testing
        
        Args:
            channel: Channel to send messages to
            count: Number of messages to send
            delay: Delay between messages in seconds
            
        Returns:
            dict with test results
        """
        start_time = time.time()
        sent_messages = []
        
        for i in range(count):
            try:
                msg = await channel.send(f"Test {i+1}/{count}: {self.test_messages[i % len(self.test_messages)]}")
                sent_messages.append(msg)
                await asyncio.sleep(delay)
            except Exception as e:
                print(f"Error sending test message: {e}")
                break
        
        end_time = time.time()
        duration = end_time - start_time
        
        return {
            "messages_sent": len(sent_messages),
            "duration": duration,
            "messages_per_second": len(sent_messages) / duration if duration > 0 else 0,
            "messages": sent_messages
        }
    
    async def cleanup_test_messages(self, messages: List[discord.Message]):
        """Delete test messages after testing"""
        for msg in messages:
            try:
                await msg.delete()
            except:
                pass
