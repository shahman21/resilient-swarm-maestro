"""Gemini (music + commentary), ElevenLabs (voice callouts), Tiger Data (telemetry).

Every service is optional. Missing keys or network errors fall back quietly so
the demo never stops because an API is down.
"""

import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import httpx

# ---------------------------------------------------------------------------
# Gemini: every 8 beats, gesture dynamics -> next 4-note phrase + rule
# ---------------------------------------------------------------------------

RULES = ("pulse", "orbit", "figure8")
SEMITONE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

FALLBACK_MUSIC = {
    "pulse": {"key": "A", "scale": "minor", "chords": ["Am", "F", "C", "G"]},
    "orbit": {"key": "C", "scale": "major", "chords": ["C", "Am", "F", "G"]},
    "figure8": {"key": "D", "scale": "dorian", "chords": ["Dm", "G", "Em", "A"]},
}


def chord_to_notes(name: str, base: int = 60) -> list[int]:
    """'Am' -> [69, 72, 76, 81]: root, third, fifth, octave as MIDI numbers near middle C."""
    name = name or "C"
    root = base + SEMITONE.get(name[0].upper(), 0)
    rest = name[1:]
    if rest[:1] == "#":
        root, rest = root + 1, rest[1:]
    elif rest[:1] == "b":
        root, rest = root - 1, rest[1:]
    if rest.startswith("dim"):
        third, fifth = 3, 6
    elif rest.startswith("m") and not rest.startswith("maj"):
        third, fifth = 3, 7
    else:
        third, fifth = 4, 7
    if root >= base + 8:  # keep phrases in a comfortable buzzer range
        root -= 12
    return [root, root + third, root + fifth, root + 12]


def clean_notes(raw) -> list[int] | None:
    try:
        notes = [int(n) for n in raw][:4]
    except (TypeError, ValueError):
        return None
    if len(notes) != 4:
        return None
    return [max(48, min(84, n)) for n in notes]


class GeminiComposer:
    """Call request() on every 8-beat boundary. The answer is held in `pending` and the
    hub swaps it in on the *next* boundary, so phrases always change on step % 8 == 0."""

    def __init__(self):
        self.key = os.getenv("GEMINI_API_KEY", "")
        if self.key.startswith("your_"):
            self.key = ""
        self.model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self._busy = False
        self._phrase = 0
        m = FALLBACK_MUSIC["orbit"]
        self.current = {**m, "notes": chord_to_notes(m["chords"][0]), "rule": None,
                        "commentary": "Swarm orbiting in C major"}
        self.pending = None

    @property
    def enabled(self) -> bool:
        return bool(self.key)

    def take_pending(self):
        """Hub calls this on the 8-beat boundary. Returns the new phrase or None."""
        p, self.pending = self.pending, None
        if p:
            self.current = p
        return p

    def request(self, rule: str, bpm: int, hand_y: float, hand_velocity: float, hand_spread: float):
        self._phrase += 1
        if not self.enabled:
            self.pending = self._fallback(rule, bpm)
            return
        if self._busy:
            return  # previous call still out; keep the current phrase
        self._busy = True
        asyncio.create_task(self._ask(rule, bpm, hand_y, hand_velocity, hand_spread))

    def _fallback(self, rule, bpm):
        m = FALLBACK_MUSIC.get(rule, FALLBACK_MUSIC["orbit"])
        chord = m["chords"][self._phrase % 4]
        mood = "calm" if bpm < 100 else "driving" if bpm < 130 else "frantic"
        return {**m, "notes": chord_to_notes(chord), "rule": None,
                "commentary": f"Swarm {rule} on {chord} in {m['key']} {m['scale']}, {bpm} BPM, {mood}"}

    async def _ask(self, rule, bpm, hand_y, hand_velocity, hand_spread):
        prompt = (
            "You conduct a dancing robot swarm (1 real mBot2, 4 virtual) from a human hand.\n"
            f"Current rule: {rule}. Tempo: {bpm} BPM. Hand height 0-1: {hand_y:.2f}. "
            f"Vertical speed: {hand_velocity:+.2f}/s. Finger spread 0 (fist) to 1 (open): {hand_spread:.2f}.\n"
            "Choose the next 8-beat phrase:\n"
            "- notes: exactly 4 MIDI note numbers between 55 and 84, one per beat, played on a buzzer.\n"
            "- rule: one of pulse, orbit, figure8 (pulse = punchy, orbit = flowing, figure8 = playful).\n"
            "- key, scale, and a 4-chord loop with simple names like C, Am, F#m, Bb.\n"
            "- commentary: at most 12 words for a live dashboard.\n"
            'Reply as JSON: {"notes":[int,int,int,int],"rule":str,"key":str,"scale":str,'
            '"chords":[str,str,str,str],"commentary":str}'
        )
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.9},
        }
        try:
            async with httpx.AsyncClient(timeout=6) as client:
                r = await client.post(url, json=body, headers={"x-goog-api-key": self.key})
                r.raise_for_status()
                data = json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
            notes = clean_notes(data.get("notes"))
            chords = [str(c) for c in data.get("chords", [])][:4]
            if not notes:
                raise ValueError(f"bad notes {data.get('notes')!r}")
            self.pending = {
                "notes": notes,
                "rule": data.get("rule") if data.get("rule") in RULES else None,
                "key": str(data.get("key", self.current["key"])),
                "scale": str(data.get("scale", self.current["scale"])),
                "chords": chords if len(chords) == 4 else self.current["chords"],
                "commentary": str(data.get("commentary", ""))[:120],
            }
        except Exception as exc:
            print(f"[gemini] falling back: {exc}")
            self.pending = self._fallback(rule, bpm)
        finally:
            self._busy = False


# ---------------------------------------------------------------------------
# ElevenLabs: spoken mode-transition callouts (cached per phrase)
# ---------------------------------------------------------------------------

class VoiceAnnouncer:
    CACHE = Path(__file__).parent / ".voice_cache"
    MIN_GAP_S = 3.0

    def __init__(self):
        self.key = os.getenv("ELEVENLABS_API_KEY", "")
        if self.key.startswith("your_"):
            self.key = ""
        self.voice_id = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
        self.use_say = os.getenv("VOICE_FALLBACK_SAY", "1") == "1" and shutil.which("say")
        self.player = shutil.which("afplay") or shutil.which("ffplay") or shutil.which("mpg123")
        self._last = 0.0
        self.CACHE.mkdir(exist_ok=True)

    def say(self, text: str):
        now = time.time()
        if now - self._last < self.MIN_GAP_S:
            return
        self._last = now
        print(f"[voice] {text}")
        asyncio.create_task(self._speak(text))

    async def _speak(self, text: str):
        if self.key and self.player:
            path = self.CACHE / (hashlib.sha1(f"{self.voice_id}:{text}".encode()).hexdigest() + ".mp3")
            try:
                if not path.exists():
                    async with httpx.AsyncClient(timeout=10) as client:
                        r = await client.post(
                            f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}",
                            headers={"xi-api-key": self.key, "accept": "audio/mpeg"},
                            json={"text": text, "model_id": "eleven_flash_v2_5"},
                        )
                        r.raise_for_status()
                        path.write_bytes(r.content)
                await self._play([self.player, str(path)] if "ffplay" not in self.player
                                 else [self.player, "-nodisp", "-autoexit", "-loglevel", "quiet", str(path)])
                return
            except Exception as exc:
                print(f"[voice] ElevenLabs failed, falling back: {exc}")
        if self.use_say:
            await self._play(["say", text])

    @staticmethod
    async def _play(cmd):
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        await proc.wait()


# ---------------------------------------------------------------------------
# Tiger Data (Timescale / Postgres): batched telemetry inserts
# ---------------------------------------------------------------------------

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS swarm_telemetry (
    time            TIMESTAMPTZ NOT NULL DEFAULT now(),
    seq             INTEGER,
    step            INTEGER,
    bpm             INTEGER,
    rule            TEXT,
    packet_loss_pct INTEGER,
    blackout        BOOLEAN,
    delivered       BOOLEAN,
    phase_drift     INTEGER,
    hand_detected   BOOLEAN,
    hand_y          REAL,
    robot_mode      TEXT
);
"""


class TelemetryStore:
    FLUSH_S = 2.0

    def __init__(self):
        self.url = os.getenv("TIGER_DB_URL", "")
        if "user:pass@host" in self.url:
            self.url = ""
        self.pool = None
        self.queue: list[tuple] = []

    async def start(self):
        if not self.url:
            print("[tiger] TIGER_DB_URL not set, telemetry kept in memory only")
            return
        try:
            import asyncpg

            self.pool = await asyncpg.create_pool(self.url, min_size=1, max_size=2, timeout=10)
            async with self.pool.acquire() as con:
                await con.execute(CREATE_SQL)
                try:
                    await con.execute(
                        "SELECT create_hypertable('swarm_telemetry', 'time', if_not_exists => TRUE);"
                    )
                except Exception:
                    pass  # plain Postgres without Timescale is fine
            asyncio.create_task(self._flush_loop())
            print("[tiger] connected")
        except Exception as exc:
            print(f"[tiger] disabled: {exc}")
            self.pool = None

    def record(self, row: tuple):
        if self.pool:
            self.queue.append(row)

    async def _flush_loop(self):
        while True:
            await asyncio.sleep(self.FLUSH_S)
            if not self.queue or not self.pool:
                continue
            rows, self.queue = self.queue, []
            try:
                async with self.pool.acquire() as con:
                    await con.executemany(
                        "INSERT INTO swarm_telemetry (seq, step, bpm, rule, packet_loss_pct, blackout, "
                        "delivered, phase_drift, hand_detected, hand_y, robot_mode) "
                        "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)",
                        rows,
                    )
            except Exception as exc:
                print(f"[tiger] insert failed ({len(rows)} rows dropped): {exc}")
