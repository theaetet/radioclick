# RadioClick

*Internet Radio for Raspberry Pi*\
Flip through stations with one button or IR, auto-announces and resumes where you left off.

---

## Quick Start

1. **Configure Wi‑Fi** on your Pi (via `raspi-config` or `wpa_supplicant`).
2. **Clone and run**
   ```bash
   git clone https://github.com/theaetet/radioclick.git
   cd radioclick
   chmod +x radio.py
   ./radio.py
   ```
3. **Enable autostart**
   ```bash
   sudo ln -s $PWD/radio.py /usr/local/bin/radioclick
   (echo "@reboot /usr/local/bin/radioclick") | crontab -
   ```
4. **Power on** — your Pi plays internet radio automatically.

---

## Configuration

> **Note:** By default, the radio station playlist is loaded from our GitHub server. To use a custom playlist, set `playlist_path` in the config.

Hidden config `.radio_config.json` is created automatically. Defaults:

```json
{
  "playlist_path": "",
  "ir_device_name": "gpio_ir_recv",
  "button_pin": 27,
  "volume": 80,
  "tts_voice": "en+f1",
  "last_index": 0,
  "log_level": "INFO"
}
```

- Leave **playlist\_path** blank to use the built‑in GitHub playlist.
- To customize, edit `.radio_config.json` and reboot.

---

## Controls

- **GPIO button**: single = next station; double = skip +10.
- **IR remote**:
  - `KEY_NEXT` / `KEY_PREVIOUS`
  - `KEY_VOLUMEUP` / `KEY_VOLUMEDOWN`

---
