#!/usr/bin/env python3
"""
Minimal database setup for yuki AI Moderation Bot
"""

import asyncpg
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

async def setup_database():
    """Create essential database tables"""
    conn = await asyncpg.connect(
        host="localhost",
        port=5432,
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME")
    )
    
    print("Creating essential tables...")
    
    # Essential tables only
    await conn.execute("CREATE TABLE IF NOT EXISTS prefixes (guild_id BIGINT, prefix TEXT)")
    await conn.execute("CREATE TABLE IF NOT EXISTS cmderror (code TEXT, error TEXT)")
    await conn.execute("CREATE TABLE IF NOT EXISTS whitelist (guild_id BIGINT, module TEXT, object_id BIGINT, mode TEXT)")
    await conn.execute("CREATE TABLE IF NOT EXISTS antinuke (guild_id BIGINT, module TEXT)")
    await conn.execute("CREATE TABLE IF NOT EXISTS mod_config (guild_id BIGINT, toxicity_threshold REAL, delete_toxic BOOLEAN, log_channel BIGINT)")
    await conn.execute("CREATE TABLE IF NOT EXISTS mod_violations (guild_id BIGINT, user_id BIGINT, message_id BIGINT, toxicity_score REAL, action TEXT, timestamp TIMESTAMPTZ)")
    await conn.execute("CREATE TABLE IF NOT EXISTS only_cmd (guild_id BIGINT, channel_id BIGINT)")
    
    print("Creating indexes...")
    
    # Performance indexes
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_whitelist_guild_module ON whitelist(guild_id, module)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_antinuke_guild ON antinuke(guild_id)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_mod_config_guild ON mod_config(guild_id)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_mod_violations_guild ON mod_violations(guild_id)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_prefixes_guild ON prefixes(guild_id)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_only_cmd_guild_channel ON only_cmd(guild_id, channel_id)")
    
    print(" Database setup complete!")
    
    await conn.close()

if __name__ == "__main__":
    asyncio.run(setup_database())
