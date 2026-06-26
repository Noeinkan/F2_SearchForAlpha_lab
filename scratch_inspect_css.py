"""Start the dashboard briefly and dump the rendered HTML of the trade-setup section."""
import threading
import time
from urllib.request import urlopen

from lib.dash.dash_config import get_theme
from lib.dash.integrated_dashboard import create_dash_app

theme = get_theme('bloomberg')
app = create_dash_app(theme=theme)


def run():
    app.run(debug=False, port=8765, host='127.0.0.1', use_reloader=False)


t = threading.Thread(target=run, daemon=True)
t.start()

# Wait for the server to come up
deadline = time.time() + 30
url = 'http://127.0.0.1:8765/'
last_err = None
while time.time() < deadline:
    try:
        resp = urlopen(url, timeout=2)
        html = resp.read().decode('utf-8', errors='replace')
        # Check our targeted inputs are present
        for tid in ['min-holding-period', 'trailing-stop-pct', 'take-profit-pct', 'position-size-pct']:
            if f'id="{tid}"' in html:
                print(f'OK: {tid} found in rendered HTML')
            else:
                print(f'MISS: {tid} not in rendered HTML')
        # Check the CSS asset is served
        css_url = 'http://127.0.0.1:8765/assets/dashboard.css'
        try:
            css_resp = urlopen(css_url, timeout=2)
            css = css_resp.read().decode('utf-8', errors='replace')
            if '#min-holding-period' in css:
                print('OK: CSS contains #min-holding-period selector')
            else:
                print('MISS: CSS missing #min-holding-period selector')
            print(f'CSS served size: {len(css)} bytes')
        except Exception as e:
            print(f'CSS fetch failed: {e}')
        # Stop server
        import os
        os._exit(0)
    except Exception as e:
        last_err = e
        time.sleep(0.5)

print(f'Server never came up: {last_err}')