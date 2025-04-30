#!/usr/bin/env python3
"""
radio.py

A online-radio player for Raspberry Pi and other single-board computers.
Cycles through an M3U playlist via a GPIO button or IR remote, controls volume,
and persists the last-played station across restarts.

Supports default remote playlist URL, HTTP/absolute/relative local playlist paths, with
fallback to remote if local file is unreadable or malformed.
Includes optional station-number TTS via `espeak` if available and configurable voice.
Automatically creates and updates a hidden config file `.radio_config.json` in the script directory.
"""

import json
import logging
import signal
import shutil
import sys
import time
from pathlib import Path
from subprocess import Popen, call

import evdev
import requests               # for fetching remote playlists
from gpiozero import Button

# ──────────────────────────────────────────────────────────────────────────────
# CONFIGURATION SECTION
# ──────────────────────────────────────────────────────────────────────────────

# Directory of this script
SCRIPT_DIR = Path(__file__).parent.resolve()
# Hidden config file in same directory
CONFIG_PATH = SCRIPT_DIR / ".radio_config.json"

# Defaults for config
DEFAULT_CONFIG = {
    "playlist_path": "",           # empty -> use default remote URL
    "ir_device_name": "gpio_ir_recv",
    "button_pin": 27,
    "volume": 80,
    "tts_voice": "en+f1",
    "last_index": 0,
    "log_level": "INFO"
}
# Default GitHub raw URL for playlist if not set or local fails
DEFAULT_PLAYLIST_URL = (
 "https://raw.githubusercontent.com/theaetet/radioclick/refs/heads/main/all_radio.m3u"
)

# Ensure config exists and is up-to-date
def ensure_config(path: Path):
    if not path.exists():
        path.write_text(json.dumps(DEFAULT_CONFIG, indent=2))
    else:
        try:
            cfg = json.loads(path.read_text())
        except Exception:
            cfg = {}
        updated = False
        for k, v in DEFAULT_CONFIG.items():
            if k not in cfg:
                cfg[k] = v
                updated = True
        if updated:
            path.write_text(json.dumps(cfg, indent=2))
    return json.loads(path.read_text())

# Load or create config
cfg = ensure_config(CONFIG_PATH)

# ──────────────────────────────────────────────────────────────────────────────
# RADIO PLAYER CLASS DEFINITION
# ──────────────────────────────────────────────────────────────────────────────

class RadioPlayer:
    def __init__(self, cfg: dict):
        # Determine playlist source (config or default)
        raw = cfg.get("playlist_path", "").strip()
        self.playlist_source = raw if raw else DEFAULT_PLAYLIST_URL

        # Load station list and initial index
        self.stations = self._load_playlist(self.playlist_source)
        self.current = cfg.get("last_index", 0) % len(self.stations)

        # GPIO button with debounce
        self.button = Button(cfg["button_pin"], bounce_time=0.1)
        self.button.when_pressed = self.next_and_play

        # IR device initialization
        self.ir = self._find_ir_device(cfg["ir_device_name"])

        # Volume setup
        self.volume = cfg.get("volume", 50)
        self._apply_volume()

        # TTS availability
        self.tts_cmd = shutil.which("espeak")
        self.tts_voice = cfg.get("tts_voice", DEFAULT_CONFIG["tts_voice"])
        if self.tts_cmd:
            logging.info(f"TTS enabled via {self.tts_cmd} with voice '{self.tts_voice}'")
        else:
            logging.info("TTS disabled: 'espeak' not found")

        # VLC process handle
        self.process = None

        # Logging setup
        logging.basicConfig(
            level=cfg.get("log_level", "INFO"),
            format="%(asctime)s [%(levelname)s] %(message)s"
        )
        logging.info("RadioPlayer initialized.")

    def _load_playlist(self, source: str):
        if source.startswith(("http://", "https://")):
            logging.info(f"Fetching remote playlist: {source}")
            resp = requests.get(source, timeout=10)
            resp.raise_for_status()
            text = resp.text
        else:
            p = Path(source)
            if not p.is_absolute():
                p = SCRIPT_DIR / p
            logging.info(f"Attempting to load local playlist: {p}")
            try:
                content = p.read_text(encoding="iso-8859-1")
            except Exception as e:
                logging.warning(f"Cannot read local playlist ({e}); falling back to remote.")
                return self._load_playlist(DEFAULT_PLAYLIST_URL)
            lines = content.splitlines()
            header = next((ln for ln in lines if ln.strip()), "")
            if not header.startswith("#EXTM3U"):
                logging.warning("Local playlist missing #EXTM3U header; using remote default.")
                return self._load_playlist(DEFAULT_PLAYLIST_URL)
            text = content
        stations = [ln.strip() for ln in text.splitlines() if ln.strip().startswith("http")]
        if not stations:
            logging.error("No stations found in playlist.")
            sys.exit(1)
        return stations

    def _find_ir_device(self, name: str):
        for dev_path in evdev.list_devices():
            dev = evdev.InputDevice(dev_path)
            if dev.name == name:
                logging.info(f"Using IR device: {dev.name} ({dev.path})")
                return dev
        logging.error(f"IR device '{name}' not found.")
        sys.exit(1)

    def _apply_volume(self):
        self.volume = max(0, min(100, self.volume))
        Popen(["amixer", "sset", "Master", f"{self.volume}%"])
        logging.info(f"Volume set to {self.volume}%")

    def adjust_volume(self, delta: int):
        self.volume += delta
        self._apply_volume()

    def speak_station(self):
        if not self.tts_cmd:
            return
        text = f"Station {self.current + 1}"
        voice_option = f"-v{self.tts_voice}"
        call([self.tts_cmd, voice_option, text])

    def play(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            time.sleep(0.2)
        url = self.stations[self.current]
        logging.info(f"Playing station {self.current}: {url}")
        self.process = Popen(["cvlc", "--quiet", url])
        self.speak_station()
        self._save_last_index()

    def next_and_play(self):
        self.current = (self.current + 1) % len(self.stations)
        self.play()

    def prev_and_play(self):
        self.current = (self.current - 1) % len(self.stations)
        self.play()

    def _save_last_index(self):
        try:
            cfg = json.loads(CONFIG_PATH.read_text())
            cfg["last_index"] = self.current
            CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
            logging.debug(f"Saved last_index = {self.current}")
        except Exception as e:
            logging.error(f"Failed to save last_index: {e}")

    def run(self):
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)
        self.play()
        logging.info("Entering main loop.")
        for event in self.ir.read_loop():
            if event.type == evdev.ecodes.EV_KEY and event.value == 1:
                code = event.code
                if code == evdev.ecodes.KEY_NEXT:
                    self.next_and_play()
                elif code == evdev.ecodes.KEY_PREVIOUS:
                    self.prev_and_play()
                elif code == evdev.ecodes.KEY_VOLUMEUP:
                    self.adjust_volume(+5)
                elif code == evdev.ecodes.KEY_VOLUMEDOWN:
                    self.adjust_volume(-5)

    def stop(self, *args):
        logging.info("Shutting down RadioPlayer.")
        if self.process and self.process.poll() is None:
            self.process.terminate()
        sys.exit(0)

if __name__ == "__main__":
    player = RadioPlayer(cfg)
    player.run()
