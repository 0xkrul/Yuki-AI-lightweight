"""
ULTRA-OPTIMIZED AI MODERATION COG
==================================
Optimized for low-resource VPS (1GB RAM, 2 vCPUs):
1. NO heavy models (PyTorch/BERT removed)
2. Lightweight async HTTP API calls OR fast heuristic fallback
3. Aggressive LRU cache (2hr TTL, 5000 entries)
4. Precompiled regex patterns
5. Memory-efficient data structures
6. Works WITHOUT GPU/CUDA
7. Can run completely offline with heuristic mode
"""

import asyncio
import logging
import re
import time
import unicodedata
from typing import Dict, List, Optional, Tuple
from functools import lru_cache
import hashlib
import os

import discord
from discord.ext import commands

# Lightweight AI deps - uses free APIs instead of heavy local models
try:
    import aiohttp
    AI_AVAILABLE = True
except Exception:
    aiohttp = None
    AI_AVAILABLE = False

log = logging.getLogger("policy_moderation")
if not log.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s", "%Y-%m-%d %H:%M:%S"))
    log.addHandler(h)
log.setLevel(logging.INFO)


class LocalPolicyModeration(commands.Cog):
    """
    OPTIMIZED: Comprehensive moderation with performance enhancements
    - Non-blocking AI inference via thread pool
    - Result caching for repeated content
    - Reduced memory footprint
    - Strike-based progressive enforcement
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # ---------------- CONFIG ----------------
        self.enabled = True
        self.allow_manage_messages_bypass = True

        # Actions
        self.delete_on_violation = True
        self.warn_in_channel = True
        self.warn_text = "your message violated the server's rules."
        self.warn_delete_after_seconds: Optional[int] = 10

        # Mod-log channel
        self.log_channel_id: Optional[int] = None

        # Timeout configurations (minutes)
        self.timeout_minutes_for_addresses = 10
        self.timeout_minutes_for_threats = 30
        self.timeout_minutes_for_severe_harassment = 20
        self.timeout_minutes_for_nsfw = 15
        self.timeout_minutes_for_hate_speech = 60

        # Cooldowns
        self.cooldown_seconds = 3
        self.user_cooldown: Dict[int, float] = {}
        
        # Violation tracking
        self.user_violations: Dict[int, Dict[str, int]] = {}
        self.strikes_before_timeout = 3

        # OPTIMIZATION: No thread pool needed - using async HTTP
        
        # OPTIMIZATION: AI result cache (content hash -> result) - AGGRESSIVE caching
        self._ai_cache = {}  # {hash: (result, timestamp)}
        self._ai_cache_ttl = 7200  # 2 hour cache (more aggressive)
        self._ai_cache_max_size = 5000  # Larger cache to minimize API calls
        
        # AI setup - async HTTP session
        self.ai_semaphore = asyncio.Semaphore(5)  # Limit concurrent API calls
        self._http_session: Optional[aiohttp.ClientSession] = None
        self.ai_enabled = AI_AVAILABLE
        
        # Perspective API key (optional, get free at https://perspectiveapi.com/)
        # Load from environment variable
        self.perspective_api_key = os.getenv("PERSPECTIVE_API_KEY")
        if self.perspective_api_key:
            log.info("✓ Perspective API key loaded - using enhanced AI moderation")
        else:
            log.info("⚡ Using fast heuristic mode (no API key) - still very effective!")

        # AI thresholds
        self.ai_thresholds = {
            "threat": 0.55,
            "identity_hate": 0.35,
            "severe_toxic": 0.75,
            "sexual_explicit": 0.60,
        }
        self.targeted_ai_thresholds = {
            "insult": 0.80,
            "toxic": 0.85,
        }

        # ---------------- PRECOMPILED PATTERNS (OPTIMIZATION) ----------------
        self._zero_width_re = re.compile(r"[\u200B-\u200F\uFEFF\u2060]")
        self._mention_re = re.compile(r"<@!?\d+>")
        self._channel_mention_re = re.compile(r"<#\d+>")
        self._role_mention_re = re.compile(r"<@&\d+>")

        # Confusables & leet
        self._confusables_map = str.maketrans({
            "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "і": "i",
            "Α": "a", "Β": "b", "Ε": "e", "Η": "h", "Ι": "i", "Κ": "k", "Μ": "m", "Ν": "n",
            "Ο": "o", "Ρ": "p", "Τ": "t", "Χ": "x",
        })
        self._leet_map = str.maketrans({
            "@": "a", "4": "a", "8": "b", "3": "e", "1": "i", "!": "i",
            "0": "o", "$": "s", "5": "s", "7": "t", "+": "t",
        })
        self._pii_leet_map = str.maketrans({
            "⓪": "0", "①": "1", "②": "2", "③": "3", "④": "4",
            "⑤": "5", "⑥": "6", "⑦": "7", "⑧": "8", "⑨": "9",
        })

        # Hard rules (hate speech)
        self.always_block_roots = {
            "n" "i" "g" "g" "e" "r",
            "f" "a" "g" "g" "o" "t",
            "k" "i" "k" "e",
            "t" "r" "a" "n" "n" "y",
            "r" "e" "t" "a" "r" "d",
            "c" "o" "o" "n",
            "s" "p" "i" "c",
            "c" "h" "i" "n" "k",
            "g" "o" "o" "k",
        }

        # Compact regexes for violations
        self._always_block_compact_re = [
            re.compile(r"\b(?:kys|kill(?:yourself|urself)|unalive(?:yourself|urself)|go\s*die)\b", re.I),
            re.compile(r"\bslit(?:\s*your)?(?:\s*wrist)?s?\b", re.I),
            re.compile(r"\b(?:commit|an\s*hero)\b", re.I),
            re.compile(r"\b(?:i(?:am|'m)?\s*going\s*to|ill|i\s*will)\s*(?:kill|hurt|beat|stab|shoot|harm|attack)\b", re.I),
            re.compile(r"\b(?:im|i'm)?\s*gonna\s*(?:kill|hurt|beat|stab|shoot|harm|attack)\b", re.I),
            re.compile(r"\b(?:i\s*know\s*where\s*you\s*live|i\s*have\s*your\s*address|i\s*have\s*your\s*ip|i'?ll\s*dox|gonna\s*dox)\b", re.I),
            re.compile(r"\b(?:swat(?:ting)?|send(?:ing)?\s*(?:pizza|food|cops))\s*(?:to\s*)?(?:your\s*(?:house|address|home))\b", re.I),
            re.compile(r"\b(?:no\s*one\s*wants\s*you\s*here|nobody\s*likes\s*you|everyone\s*hates\s*you)\b", re.I),
            re.compile(r"\b(?:send\s*(?:nudes|pics)|show\s*(?:me\s*)?(?:your|ur)\s*(?:tits|ass|pussy|dick|cock))\b", re.I),
            re.compile(r"\b(?:your\s*real\s*(?:name|gender)|not\s*a\s*real\s*(?:man|woman|boy|girl))\b", re.I),
            re.compile(r"\b(?:holocaust\s*(?:never\s*happened|was\s*(?:fake|a\s*lie|hoax)))\b", re.I),
        ]

        # PII patterns
        self._ipv4_re = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\s*\.\s*){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")
        self._ipv6_re = re.compile(r"\b(?:[A-Fa-f0-9]{1,4}:){2,7}[A-Fa-f0-9]{1,4}\b")
        self._email_re = re.compile(r"\b[a-z0-9._%+-]{1,64}@[a-z0-9.-]{1,255}\.[a-z]{2,24}\b", re.I)
        
        addr_suffixes = r"st|street|ave|avenue|rd|road|blvd|boulevard|dr|drive|ln|lane|ct|court|pl|place|ter|terrace|way|hwy|highway"
        self._street_with_number_re = re.compile(rf"\b\d{{1,6}}\s+(?:[a-z0-9]+(?:\s+|$)){{1,5}}(?:{addr_suffixes})\b", re.I)
        self._uk_postcode_re = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", re.I)
        self._street_ordinal_re = re.compile(rf"\b\d{{1,3}}(?:st|nd|rd|th)\s+(?:{addr_suffixes})\b", re.I)
        self._pobox_re = re.compile(r"\b(?:p\.?\s*o\.?\s*)?box\s*\d+\b", re.I)
        self._pii_leadin_re = re.compile(r"\b(?:my|his|her|their|our)\s+(?:ip|address|addr|phone|number|email)\s*(?:is|=|:)\b", re.I)
        self._iban_re = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")
        self._card_candidate_re = re.compile(r"(?:\b\d[ -]*?){13,19}\b")
        self._phone_candidate_re = re.compile(r"\b(?:\+?\d[\d\s().-]{7,}\d)\b")

        # NSFW patterns
        self.nsfw_keywords = {
            "porn", "hentai", "r34", "xxx", "nsfw", "nude", "naked",
            "sex", "cum", "pussy", "dick", "cock", "tits", "boobs",
            "ass", "anal", "blowjob", "handjob", "masturbat", "orgasm"
        }
        self._nsfw_site_re = re.compile(r"\b(?:pornhub|xvideos|xnxx|onlyfans|rule34|e621|gelbooru|nhentai)\.\w+", re.I)
        
        # Self-promotion patterns
        self._discord_invite_re = re.compile(r"(?:discord(?:\.gg|\.com/invite|app\.com/invite)|dsc\.gg)/[a-zA-Z0-9]+", re.I)
        self._promo_patterns = [
            re.compile(r"\b(?:join\s*my|check\s*out\s*my|subscribe\s*to|follow\s*me\s*on)\s*(?:server|discord|channel|youtube|twitch|instagram|twitter|tiktok)\b", re.I),
            re.compile(r"\b(?:dm\s*me\s*(?:to\s*buy|for\s*(?:cheap|free|nitro|robux|v-?bucks)))\b", re.I),
            re.compile(r"\b(?:cheap|free|selling)\s*(?:nitro|robux|v-?bucks|accounts|cheats|hacks|boosts)\b", re.I),
        ]

        log.info("✓ LocalPolicyModeration loaded (ULTRA-OPTIMIZED for low-resource VPS)")

    def cog_unload(self):
        """OPTIMIZATION: Clean up HTTP session"""
        if self._http_session and not self._http_session.closed:
            asyncio.create_task(self._http_session.close())
    
    async def _get_http_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session"""
        if self._http_session is None or self._http_session.closed:
            self._http_session = aiohttp.ClientSession()
        return self._http_session
    
    # ---------------- OPTIMIZATION: Cache Management ----------------
    def _get_content_hash(self, text: str) -> str:
        """Create hash of content for cache key"""
        return hashlib.md5(text.encode('utf-8')).hexdigest()
    
    def _get_cached_ai_result(self, content_hash: str) -> Optional[Dict[str, float]]:
        """Get cached AI result if available and not expired"""
        if content_hash in self._ai_cache:
            result, timestamp = self._ai_cache[content_hash]
            if time.time() - timestamp < self._ai_cache_ttl:
                return result
            else:
                del self._ai_cache[content_hash]
        return None
    
    def _cache_ai_result(self, content_hash: str, result: Dict[str, float]):
        """Cache AI result with timestamp"""
        # OPTIMIZATION: Limit cache size
        if len(self._ai_cache) >= self._ai_cache_max_size:
            # Remove oldest entries (simple: remove first 100)
            to_remove = list(self._ai_cache.keys())[:100]
            for key in to_remove:
                del self._ai_cache[key]
        
        self._ai_cache[content_hash] = (result, time.time())
    
    # ---------------- cooldown ----------------
    def _user_on_cooldown(self, user_id: int) -> bool:
        until = self.user_cooldown.get(user_id)
        if not until:
            return False
        if time.time() >= until:
            self.user_cooldown.pop(user_id, None)
            return False
        return True

    def _set_user_cooldown(self, user_id: int) -> None:
        self.user_cooldown[user_id] = time.time() + self.cooldown_seconds

    # ---------------- OPTIMIZATION: Static methods for faster processing ----------------
    @staticmethod
    @lru_cache(maxsize=512)
    def _strip_diacritics(s: str) -> str:
        """CACHED: Strip diacritics from string"""
        return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))

    @staticmethod
    def _digits_only(s: str) -> str:
        return "".join(ch for ch in s if ch.isdigit())

    @staticmethod
    def _squeeze_repeats(token: str, max_rep: int = 2) -> str:
        out, prev, rep = [], "", 0
        for ch in token:
            if ch == prev:
                rep += 1
                if rep < max_rep:
                    out.append(ch)
            else:
                prev = ch
                rep = 0
                out.append(ch)
        return "".join(out)

    def _normalize_compact(self, raw: str) -> Tuple[List[str], str]:
        """OPTIMIZED: Normalize text for pattern matching"""
        s = raw or ""
        s = unicodedata.normalize("NFKC", s)
        s = self._zero_width_re.sub("", s)
        s = s.lower().translate(self._confusables_map).translate(self._leet_map)
        s = self._strip_diacritics(s)
        s = re.sub(r"[^a-z0-9]+", " ", s)
        s = re.sub(r"\s+", " ", s).strip()
        tokens = [self._squeeze_repeats(t) for t in (s.split() if s else [])]
        return tokens, "".join(tokens)

    def _prep_pii_text(self, raw: str) -> str:
        """OPTIMIZED: Prepare text for PII detection"""
        s = raw or ""
        s = unicodedata.normalize("NFKC", s)
        s = self._zero_width_re.sub("", s)
        s = s.lower().translate(self._confusables_map).translate(self._pii_leet_map)
        s = self._strip_diacritics(s)
        s = re.sub(r"\s*[\(\[\{]?\s*dot\s*[\)\]\}]?\s*", ".", s, flags=re.I)
        s = re.sub(r"\s*[\(\[\{]?\s*at\s*[\)\]\}]?\s*", "@", s, flags=re.I)
        s = re.sub(r"[^a-z0-9@\.\:\+\-\s\(\)]", " ", s)
        s = re.sub(r"\s+", " ", s).strip()
        return s

    # ---------------- PII checks ----------------
    @staticmethod
    def _luhn_ok(number: str) -> bool:
        """OPTIMIZED: Luhn algorithm for credit card validation"""
        digits = [int(c) for c in number if c.isdigit()]
        if len(digits) < 13 or len(digits) > 19:
            return False
        checksum = 0
        parity = len(digits) % 2
        for i, d in enumerate(digits):
            if i % 2 == parity:
                d *= 2
                if d > 9:
                    d -= 9
            checksum += d
        return checksum % 10 == 0

    def _phone_hit(self, pii_text: str) -> Optional[str]:
        for m in self._phone_candidate_re.finditer(pii_text):
            cand = m.group(0)
            digits = self._digits_only(cand)
            if self._ipv4_re.search(cand):
                continue
            if 9 <= len(digits) <= 15:
                return cand
        return None

    def _card_hit(self, pii_text: str) -> Optional[str]:
        for m in self._card_candidate_re.finditer(pii_text):
            digits = self._digits_only(m.group(0))
            if self._luhn_ok(digits):
                return m.group(0)
        return None

    def _pii_reason(self, raw_text: str) -> Optional[str]:
        """OPTIMIZED: Fast PII detection"""
        pii_text = self._prep_pii_text(raw_text)

        if self._pii_leadin_re.search(pii_text):
            return "pii:leadin"
        if self._uk_postcode_re.search(pii_text):
            return "pii:uk_postcode"
        if self._ipv4_re.search(pii_text):
            return "pii:ipv4"
        if self._ipv6_re.search(pii_text):
            return "pii:ipv6"
        if self._email_re.search(pii_text):
            return "pii:email"
        if self._pobox_re.search(pii_text):
            return "pii:address_pobox"
        if self._street_with_number_re.search(pii_text):
            return "pii:address_street"
        if self._street_ordinal_re.search(pii_text):
            return "pii:address_ordinal"

        phone = self._phone_hit(pii_text)
        if phone:
            return "pii:phone"
        if self._iban_re.search(pii_text.upper()):
            return "pii:iban"
        card = self._card_hit(pii_text)
        if card:
            return "pii:card"

        return None

    def _is_address_reason(self, reason: str) -> bool:
        return reason.startswith("pii:address_")
    
    def _is_threat_reason(self, reason: str) -> bool:
        return "threat" in reason or "going to" in reason or "gonna" in reason
    
    def _is_hate_speech_reason(self, reason: str) -> bool:
        return "identity_hate" in reason or "hard_block_root" in reason or "holocaust" in reason
    
    def _is_severe_harassment_reason(self, reason: str) -> bool:
        return "dox" in reason or "swat" in reason or "sexual" in reason
    
    def _is_nsfw_reason(self, reason: str) -> bool:
        return reason.startswith("nsfw:")
    
    def _get_violation_category(self, reason: str) -> str:
        """Categorize violation reason"""
        if self._is_hate_speech_reason(reason):
            return "hate_speech"
        elif self._is_threat_reason(reason) or "kys" in reason or "kill" in reason:
            return "threats"
        elif "pii:" in reason or self._is_address_reason(reason):
            return "doxxing"
        elif self._is_severe_harassment_reason(reason) or "insult" in reason or "toxic" in reason:
            return "harassment"
        elif self._is_nsfw_reason(reason):
            return "nsfw"
        elif reason.startswith("promo:"):
            return "promo"
        else:
            return "other"
    
    def _increment_violation(self, user_id: int, category: str) -> int:
        """Increment violation count"""
        if user_id not in self.user_violations:
            self.user_violations[user_id] = {}
        if category not in self.user_violations[user_id]:
            self.user_violations[user_id][category] = 0
        self.user_violations[user_id][category] += 1
        return self.user_violations[user_id][category]
    
    def _check_nsfw(self, raw_text: str) -> Optional[str]:
        """OPTIMIZED: NSFW detection"""
        text_lower = raw_text.lower()
        if self._nsfw_site_re.search(text_lower):
            return "nsfw:explicit_site"
        matches = sum(1 for kw in self.nsfw_keywords if kw in text_lower)
        if matches >= 2:
            return "nsfw:explicit_content"
        return None
    
    def _check_self_promotion(self, raw_text: str) -> Optional[str]:
        """OPTIMIZED: Self-promotion detection"""
        text = raw_text.lower()
        invite_matches = self._discord_invite_re.findall(text)
        if invite_matches:
            for pattern in self._promo_patterns:
                if pattern.search(text):
                    return "promo:discord_invite"
        for pattern in self._promo_patterns:
            if pattern.search(text):
                return "promo:advertising"
        return None

    # ---------------- OPTIMIZATION: Lightweight AI using free APIs ----------------
    async def _call_perspective_api(self, text_in: str) -> Dict[str, float]:
        """Call Perspective API (free tier: 1 QPS)"""
        if not self.perspective_api_key:
            return {}
        
        try:
            session = await self._get_http_session()
            url = f"https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze?key={self.perspective_api_key}"
            data = {
                "comment": {"text": text_in},
                "languages": ["en"],
                "requestedAttributes": {
                    "TOXICITY": {},
                    "SEVERE_TOXICITY": {},
                    "IDENTITY_ATTACK": {},
                    "INSULT": {},
                    "THREAT": {},
                    "SEXUALLY_EXPLICIT": {}
                }
            }
            async with session.post(url, json=data, timeout=aiohttp.ClientTimeout(total=3)) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    scores = {}
                    for attr, data in result.get("attributeScores", {}).items():
                        score = data.get("summaryScore", {}).get("value", 0)
                        # Map to our labels
                        if attr == "TOXICITY":
                            scores["toxic"] = score
                        elif attr == "SEVERE_TOXICITY":
                            scores["severe_toxic"] = score
                        elif attr == "IDENTITY_ATTACK":
                            scores["identity_hate"] = score
                        elif attr == "INSULT":
                            scores["insult"] = score
                        elif attr == "THREAT":
                            scores["threat"] = score
                        elif attr == "SEXUALLY_EXPLICIT":
                            scores["sexual_explicit"] = score
                    return scores
        except Exception as e:
            log.debug(f"Perspective API error: {e}")
        return {}
    
    async def _simple_heuristic_scores(self, text_in: str) -> Dict[str, float]:
        """Fallback: Fast heuristic-based scoring (no API needed)"""
        text_lower = text_in.lower()
        scores = {}
        
        # Threat keywords
        threat_words = ["kill", "die", "murder", "attack", "hurt", "harm", "beat", "shoot", "stab"]
        threat_score = sum(1 for w in threat_words if w in text_lower) / max(len(threat_words), 1)
        scores["threat"] = min(threat_score * 0.5, 0.9)
        
        # Identity hate keywords
        hate_words = [word.replace(" ", "") for word in self.always_block_roots]
        hate_score = sum(1 for w in hate_words if w in text_lower.replace(" ", "")) / max(len(hate_words), 1)
        scores["identity_hate"] = min(hate_score, 0.95)
        
        # Toxic keywords
        toxic_words = ["stupid", "idiot", "dumb", "moron", "trash", "garbage", "pathetic", "loser"]
        toxic_score = sum(1 for w in toxic_words if w in text_lower) / max(len(toxic_words), 1)
        scores["toxic"] = min(toxic_score * 0.4, 0.8)
        
        # Insult keywords
        insult_words = ["ugly", "fat", "gross", "disgusting", "worthless"]
        insult_score = sum(1 for w in insult_words if w in text_lower) / max(len(insult_words), 1)
        scores["insult"] = min(insult_score * 0.5, 0.85)
        
        # Sexual explicit
        sexual_score = sum(1 for kw in self.nsfw_keywords if kw in text_lower) / max(len(self.nsfw_keywords), 1)
        scores["sexual_explicit"] = min(sexual_score * 0.3, 0.75)
        
        # Severe toxic (multiple indicators)
        severe_indicators = sum([
            scores.get("threat", 0) > 0.3,
            scores.get("identity_hate", 0) > 0.3,
            scores.get("toxic", 0) > 0.5,
            len([w for w in ["fuck", "shit", "bitch", "ass"] if w in text_lower]) > 2
        ])
        scores["severe_toxic"] = min(severe_indicators * 0.25, 0.9)
        
        return scores

    async def _ai_scores(self, text_in: str) -> Dict[str, float]:
        """ULTRA-OPTIMIZED: AI inference with aggressive caching and lightweight processing"""
        if not self.ai_enabled:
            return {}
        
        # OPTIMIZATION: Check cache first (most important for performance)
        content_hash = self._get_content_hash(text_in)
        cached_result = self._get_cached_ai_result(content_hash)
        if cached_result is not None:
            return cached_result
        
        # Try Perspective API if configured, otherwise use fast heuristics
        if self.perspective_api_key:
            scores = await self._call_perspective_api(text_in)
        else:
            # FAST: No API calls, pure heuristic (works offline!)
            scores = await self._simple_heuristic_scores(text_in)
        
        # Cache result for future
        if scores:
            self._cache_ai_result(content_hash, scores)
        
        return scores

    def _ai_violation(self, scores: Dict[str, float], targeted: bool) -> Optional[str]:
        """OPTIMIZED: Check AI scores against thresholds"""
        if not scores:
            return None

        for label, thr in self.ai_thresholds.items():
            if scores.get(label, 0.0) >= thr:
                return f"ai:{label}:{scores[label]:.3f}>={thr:.3f}"

        if targeted:
            for label, thr in self.targeted_ai_thresholds.items():
                if scores.get(label, 0.0) >= thr:
                    return f"ai:{label}:{scores[label]:.3f}>={thr:.3f}"

        return None

    # ---------------- Decision ----------------
    async def should_moderate(self, message: discord.Message) -> Optional[str]:
        """OPTIMIZED: Fast violation detection"""
        raw = message.content or ""
        if not raw.strip():
            return None

        # 1) PII/Doxxing (fast, critical)
        pii = self._pii_reason(raw)
        if pii:
            return pii

        # 2) NSFW
        nsfw = self._check_nsfw(raw)
        if nsfw:
            return nsfw
        
        # 3) Self-promotion
        promo = self._check_self_promotion(raw)
        if promo:
            return promo

        # 4) Hard rules - check against BOTH original and normalized text
        raw_no_mentions = self._mention_re.sub(" ", raw)
        raw_no_mentions = self._channel_mention_re.sub(" ", raw_no_mentions)
        raw_no_mentions = self._role_mention_re.sub(" ", raw_no_mentions)

        tokens, compact = self._normalize_compact(raw_no_mentions)

        # Check patterns against ORIGINAL text first (preserves word boundaries)
        for r in self._always_block_compact_re:
            if r.search(raw_no_mentions.lower()):
                return f"rule:{r.pattern}"
        
        # Also check compact for obfuscated versions
        compact_with_spaces = " ".join(tokens)  # Keep spaces for word boundaries
        for r in self._always_block_compact_re:
            if r.search(compact_with_spaces):
                return f"rule:{r.pattern}"

        # 5) Slur roots
        for root in self.always_block_roots:
            if root in compact or any(t.startswith(root) for t in tokens):
                return "rule:hard_block_root"

        # 6) AI analysis (only if needed, with caching)
        targeted = bool(message.mentions or message.role_mentions)
        async with self.ai_semaphore:
            scores = await self._ai_scores(raw)
        ai_reason = self._ai_violation(scores, targeted=targeted)
        if ai_reason:
            return ai_reason

        return None

    # ---------------- Actions ----------------
    async def _timeout_member(self, member: discord.Member, minutes: int, reason: str) -> None:
        if minutes <= 0:
            return
        from datetime import timedelta
        try:
            until = discord.utils.utcnow() + timedelta(minutes=minutes)
            await member.timeout(until, reason=f"AutoMod: {reason}")
        except Exception as e:
            log.warning("Timeout failed: %s", e)

    async def _warn_channel_with_strikes(self, message: discord.Message, category: str, strike_count: int) -> None:
        if not self.warn_in_channel or self._user_on_cooldown(message.author.id):
            return
        
        self._set_user_cooldown(message.author.id)
        category_display = category.replace("_", " ").title()
        
        if strike_count < self.strikes_before_timeout:
            warning = f"{message.author.mention} {self.warn_text} **Strike {strike_count}/{self.strikes_before_timeout}** for {category_display}."
        else:
            warning = f"{message.author.mention} {self.warn_text} **Final Strike ({strike_count})** for {category_display} - you've been timed out."
        
        try:
            await message.channel.send(warning, delete_after=self.warn_delete_after_seconds)
        except Exception as e:
            log.warning("Warn send failed: %s", e)

    async def _log_violation(self, message: discord.Message, reason: str, strike_count: int = 1, category: str = "unknown") -> None:
        if not self.log_channel_id:
            return
        ch = self.bot.get_channel(self.log_channel_id)
        if not ch:
            return

        emb = discord.Embed(
            title="Message removed",
            description=(
                f"Reason: `{reason}`\n"
                f"Category: **{category.replace('_', ' ').title()}**\n"
                f"Strike Count: **{strike_count}/{self.strikes_before_timeout}**\n"
                f"User: {message.author} ({message.author.id})\n"
                f"Channel: {message.channel.mention}\n"
                f"Time: {discord.utils.format_dt(message.created_at, style='F')}\n\n"
                f"Content:\n{message.content}"
            ),
        )
        
        if strike_count >= self.strikes_before_timeout:
            emb.color = discord.Color.red()
        elif strike_count == 2:
            emb.color = discord.Color.orange()
        else:
            emb.color = discord.Color.yellow()
        
        try:
            await ch.send(embed=emb)
        except Exception as e:
            log.warning("Log send failed: %s", e)

    async def _handle_violation(self, message: discord.Message, reason: str) -> None:
        """OPTIMIZED: Handle violations with strikes"""
        # Delete message
        if self.delete_on_violation:
            try:
                await message.delete()
            except Exception as e:
                log.warning("Delete failed: %s", e)

        # Track violation
        category = self._get_violation_category(reason)
        strike_count = self._increment_violation(message.author.id, category)
        
        # Warn user
        await self._warn_channel_with_strikes(message, category, strike_count)

        # Apply timeout after 3rd strike
        if isinstance(message.author, discord.Member) and strike_count >= self.strikes_before_timeout:
            timeout_mins = 0
            
            if self._is_hate_speech_reason(reason):
                timeout_mins = self.timeout_minutes_for_hate_speech
            elif self._is_threat_reason(reason):
                timeout_mins = self.timeout_minutes_for_threats
            elif self._is_address_reason(reason) or "pii:" in reason:
                timeout_mins = self.timeout_minutes_for_addresses
            elif self._is_severe_harassment_reason(reason):
                timeout_mins = self.timeout_minutes_for_severe_harassment
            elif self._is_nsfw_reason(reason):
                timeout_mins = self.timeout_minutes_for_nsfw
            
            if timeout_mins > 0:
                await self._timeout_member(message.author, timeout_mins, f"{reason} (Strike {strike_count})")

        await self._log_violation(message, reason, strike_count, category)

    # ---------------- Events ----------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """CRITICAL: Fire-and-forget AI moderation to prevent blocking"""
        if not self.enabled or message.author.bot or not message.guild:
            return

        # Staff bypass
        if self.allow_manage_messages_bypass and isinstance(message.author, discord.Member):
            if message.author.guild_permissions.manage_messages:
                return

        # CRITICAL: Run moderation in background task (non-blocking)
        asyncio.create_task(self._moderate_message(message))
    
    async def _moderate_message(self, message: discord.Message):
        """Background task for AI moderation"""
        try:
            reason = await self.should_moderate(message)
            if reason:
                await self._handle_violation(message, reason)
        except Exception as e:
            log.exception("AI moderation error: %s", e)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        """CRITICAL: Fire-and-forget AI moderation to prevent blocking"""
        if not self.enabled or after.author.bot or not after.guild:
            return
        if (before.content or "") == (after.content or ""):
            return
        if self.allow_manage_messages_bypass and isinstance(after.author, discord.Member):
            if after.author.guild_permissions.manage_messages:
                return

        # CRITICAL: Run moderation in background task (non-blocking)
        asyncio.create_task(self._moderate_message(after))

    # ---------------- Commands ----------------
    @commands.command(name="modstatus")
    @commands.has_permissions(manage_guild=True)
    async def modstatus(self, ctx: commands.Context):
        """Check moderation system status"""
        tracked_users = len(self.user_violations)
        total_strikes = sum(sum(cats.values()) for cats in self.user_violations.values())
        cache_size = len(self._ai_cache)
        
        await ctx.reply(
            f"**Moderation Status:**\n"
            f"• Enabled: {self.enabled}\n"
            f"• Bypass Mods: {self.allow_manage_messages_bypass}\n"
            f"• AI Enabled: {self.ai_enabled}\n"
            f"• Strikes Before Timeout: {self.strikes_before_timeout}\n"
            f"• Log Channel: {self.log_channel_id}\n"
            f"• Tracked Users: {tracked_users}\n"
            f"• Total Strikes: {total_strikes}\n"
            f"• AI Cache Size: {cache_size}/{self._ai_cache_max_size}"
        )

    @commands.command(name="modbypass")
    @commands.has_permissions(manage_guild=True)
    async def modbypass(self, ctx: commands.Context, value: str):
        """Toggle mod bypass"""
        v = value.strip().lower()
        if v in ("on", "true", "1", "yes"):
            self.allow_manage_messages_bypass = True
        elif v in ("off", "false", "0", "no"):
            self.allow_manage_messages_bypass = False
        else:
            return await ctx.reply("Usage: `;modbypass on|off`")
        await ctx.reply(f"Bypass mods: {self.allow_manage_messages_bypass}")

    @commands.command(name="modlog")
    @commands.has_permissions(manage_guild=True)
    async def modlog(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """Set mod log channel"""
        if channel is None:
            self.log_channel_id = None
            return await ctx.reply("Mod-log disabled.")
        self.log_channel_id = channel.id
        await ctx.reply(f"Mod-log set to {channel.mention}")

    @commands.command(name="modtest")
    @commands.has_permissions(manage_guild=True)
    async def modtest(self, ctx: commands.Context, *, text: str):
        """Test moderation on text"""
        fake = type("FakeMsg", (), {})()
        fake.content = text
        fake.mentions = []
        fake.role_mentions = []
        reason = await self.should_moderate(fake)  # type: ignore
        await ctx.reply(f"Result: {reason or 'OK (no violation)'}")
    
    @commands.command(name="modwarnings", aliases=["warnings", "strikes"])
    @commands.has_permissions(manage_messages=True)
    async def modwarnings(self, ctx: commands.Context, user: discord.Member):
        """View user strikes"""
        violations = self.user_violations.get(user.id, {})
        if not violations:
            return await ctx.reply(f"{user.mention} has no strikes.")
        
        lines = [f"**Strikes for {user}:**"]
        for category, count in violations.items():
            category_display = category.replace("_", " ").title()
            lines.append(f"• {category_display}: {count}/{self.strikes_before_timeout}")
        
        await ctx.reply("\n".join(lines))
    
    @commands.command(name="modclearstrikes", aliases=["clearwarnings"])
    @commands.has_permissions(manage_guild=True)
    async def modclearstrikes(self, ctx: commands.Context, user: discord.Member, category: Optional[str] = None):
        """Clear user strikes"""
        if user.id not in self.user_violations:
            return await ctx.reply(f"{user.mention} has no strikes to clear.")
        
        if category is None or category.lower() == "all":
            self.user_violations.pop(user.id, None)
            return await ctx.reply(f"Cleared all strikes for {user.mention}.")
        
        category = category.lower().replace(" ", "_")
        valid_categories = ["hate_speech", "threats", "doxxing", "harassment", "nsfw", "promo", "other"]
        
        if category not in valid_categories:
            return await ctx.reply(f"Invalid category. Valid: {', '.join(valid_categories)}")
        
        if category in self.user_violations[user.id]:
            del self.user_violations[user.id][category]
            if not self.user_violations[user.id]:
                del self.user_violations[user.id]
            return await ctx.reply(f"Cleared {category.replace('_', ' ')} strikes for {user.mention}.")
        else:
            return await ctx.reply(f"{user.mention} has no {category.replace('_', ' ')} strikes.")


async def setup(bot: commands.Bot):
    await bot.add_cog(LocalPolicyModeration(bot))
