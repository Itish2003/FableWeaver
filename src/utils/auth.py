import os
import time
import itertools
from dotenv import load_dotenv
from src.config import get_settings

load_dotenv()

# Silence "Both GOOGLE_API_KEY and GEMINI_API_KEY are set" warning
if "GEMINI_API_KEY" in os.environ:
    del os.environ["GEMINI_API_KEY"]

class KeyRotator:
    def __init__(self):
        keys_str = os.getenv("GOOGLE_API_KEYS", "")
        if not keys_str:
            single_key = os.getenv("GOOGLE_API_KEY")
            if single_key:
                self.keys = [single_key]
            else:
                raise ValueError("No GOOGLE_API_KEYS or GOOGLE_API_KEY found in environment.")
        else:
            self.keys = [k.strip() for k in keys_str.split(",") if k.strip()]
        
        self._cooldowns = {k: 0 for k in self.keys}
        self._current_index = 0

    def get_next_key(self) -> str:
        # Try to find a key not in cooldown
        for _ in range(len(self.keys)):
            key = self.keys[self._current_index]
            self._current_index = (self._current_index + 1) % len(self.keys)
            
            if time.time() > self._cooldowns[key]:
                print(f"[KeyRotator] Selected key: {key[:8]}...")
                return key
        
        # All keys in cooldown, find the one with the smallest remaining wait
        best_key = min(self._cooldowns, key=self._cooldowns.get)
        wait_time = max(0.1, self._cooldowns[best_key] - time.time())
        print(f"[KeyRotator] All keys exhausted. Waiting {wait_time:.1f}s for earliest key...")
        time.sleep(wait_time)
        return best_key

    def mark_exhausted(self, key: str, duration: int = None):
        if duration is None:
            duration = get_settings().key_cooldown_seconds
        print(f"[KeyRotator] Marking key {key[:8]}... as exhausted for {duration}s.")
        self._cooldowns[key] = time.time() + duration

def get_next_key() -> str:
    return rotator.get_next_key()

# Singleton instance
rotator = KeyRotator()

def get_api_key() -> str:
    return rotator.get_next_key()

def mark_key_exhausted(key: str):
    rotator.mark_exhausted(key)
