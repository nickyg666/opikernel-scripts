#!/usr/bin/env python3
"""
peak_model_switch.py — switch Hermes models around provider peak windows.

Scheduled by cron at :45 (pre-peak → cheaper model) and :15 (post-peak →
DeepSeek flash). The price probe is pluggable; if no live pricing source is
available it falls back to a time-based heuristic and logs everything.

Usage:
  peak_model_switch.py prepeak     # :45 run — switch to cheap model
  peak_model_switch.py postpeak    # :15 run — switch back to deepseek flash

Config (JSON, defaults inline):
  {
    "cheap_model":  "deepseek-v4-lite",
    "cheap_provider": "deepseek",
    "flash_model":  "deepseek-v4-flash",
    "flash_provider": "deepseek",
    "price_api": ""   # optional URL returning {"flash": <usd/Mtok>, "cheap": <usd/Mtok>}
  }
"""
import json, os, sys, shutil, subprocess, datetime, pathlib

CONFIG_PATH = pathlib.Path(os.environ.get("HERMES_CONFIG", "/home/host/.hermes/config.yaml"))
STATE_PATH  = pathlib.Path("/home/host/.hermes/peak_model_state.json")
LOG_PATH    = pathlib.Path("/home/host/opikernel/logs/peak_model.log")
SETTINGS    = {
    "cheap_model":   os.environ.get("PEAK_CHEAP_MODEL", "deepseek-v4-lite"),
    "cheap_provider": os.environ.get("PEAK_CHEAP_PROVIDER", "deepseek"),
    "flash_model":   os.environ.get("PEAK_FLASH_MODEL", "deepseek-v4-flash"),
    "flash_provider": os.environ.get("PEAK_FLASH_PROVIDER", "deepseek"),
    "price_api":     os.environ.get("PEAK_PRICE_API", ""),
}

def log(msg):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.datetime.now().isoformat()} {msg}"
    with open(LOG_PATH, "a") as f:
        f.write(line + "\n")
    print(line)

def probe_prices():
    """Return (flash_price, cheap_price) USD/Mtok or (None,None) if unknown."""
    api = SETTINGS["price_api"]
    if not api:
        return None, None
    try:
        import urllib.request
        with urllib.request.urlopen(api, timeout=8) as r:
            d = json.load(r)
        return d.get("flash"), d.get("cheap")
    except Exception as e:
        log(f"price probe failed: {e}")
        return None, None

def set_model(model, provider):
    if not CONFIG_PATH.exists():
        log(f"ERROR config not found: {CONFIG_PATH}")
        return False
    shutil.copy2(CONFIG_PATH, str(CONFIG_PATH) + ".bak-peak")
    try:
        import yaml
        with open(CONFIG_PATH) as f:
            cfg = yaml.safe_load(f)
        if "model" not in cfg:
            cfg["model"] = {}
        cfg["model"]["default"] = model
        cfg["model"]["provider"] = provider
        with open(CONFIG_PATH, "w") as f:
            yaml.safe_dump(cfg, f, sort_keys=False)
        # verify
        with open(CONFIG_PATH) as f:
            chk = yaml.safe_load(f)
        ok = chk.get("model", {}).get("default") == model and chk.get("model", {}).get("provider") == provider
        log(f"set model.default={model} provider={provider} verified={ok}")
        return ok
    except Exception as e:
        log(f"ERROR writing config: {e}")
        return False

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    now = datetime.datetime.now()
    flash_p, cheap_p = probe_prices()
    price_note = f"prices flash={flash_p} cheap={cheap_p}" if flash_p else "prices unknown (time-based heuristic)"

    if mode == "prepeak":  # :45 — cheaper model before peak
        # If we have real prices and cheap is actually cheaper, switch; else heuristic.
        if flash_p is not None and cheap_p is not None and cheap_p >= flash_p:
            log(f"prepeak: SKIP switch ({price_note}) — cheap model not cheaper, staying on {SETTINGS['flash_model']}")
            return 0
        ok = set_model(SETTINGS["cheap_model"], SETTINGS["cheap_provider"])
        log(f"prepeak: switched to cheap {SETTINGS['cheap_model']} ({price_note}) ok={ok}")
        return 0 if ok else 1
    elif mode == "postpeak":  # :15 — back to DeepSeek flash
        ok = set_model(SETTINGS["flash_model"], SETTINGS["flash_provider"])
        log(f"postpeak: switched back to flash {SETTINGS['flash_model']} ({price_note}) ok={ok}")
        return 0 if ok else 1
    else:
        log(f"usage: {sys.argv[0]} prepeak|postpeak")
        return 2

if __name__ == "__main__":
    sys.exit(main())
