"""Prompts for missing API keys without echoing them, and writes them to .env."""
import getpass, os
from envfile import load_env, set_key, PATH

REQUIRED = {
    "ANTHROPIC_API_KEY": "Anthropic API key (console.anthropic.com)",
    "KITE_API_KEY": "Kite Connect API key (developers.kite.trade)",
    "KITE_API_SECRET": "Kite Connect API secret",
}

def main() -> None:
    if not os.path.exists(PATH):
        open(PATH, "w").close()
        os.chmod(PATH, 0o600)
    load_env()
    for key, label in REQUIRED.items():
        if os.environ.get(key):
            print(f"{key}: already set")
            continue
        value = getpass.getpass(f"{label} (input hidden, Enter to skip): ").strip()
        if value:
            set_key(key, value)
            print(f"{key}: saved")
        else:
            print(f"{key}: skipped; add it to .env later")

if __name__ == "__main__":
    main()
