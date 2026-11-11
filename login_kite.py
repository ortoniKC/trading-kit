"""Daily Kite login. You log in yourself in the browser (password and 2FA stay with you)."""
import os, datetime as dt
import store
from envfile import set_key

def main() -> None:
    from kiteconnect import KiteConnect
    kite = KiteConnect(api_key=os.environ["KITE_API_KEY"])
    print("\n1. Open this link in your browser and log in to Zerodha yourself:\n")
    print(kite.login_url())
    print("\n2. After login your browser lands on a URL containing request_token=...")
    raw = input("\n3. Paste the request_token (or the full URL) here: ").strip()
    token = raw.split("request_token=")[1].split("&")[0] if "request_token=" in raw else raw
    data = kite.generate_session(token, api_secret=os.environ["KITE_API_SECRET"])
    today = dt.datetime.now(store.IST).date().isoformat()
    set_key("KITE_ACCESS_TOKEN", data["access_token"])
    set_key("KITE_TOKEN_DATE", today)
    print(f"\nLogin saved for {today}. Kite tokens expire daily, so repeat this each trading day.")

if __name__ == "__main__":
    main()
