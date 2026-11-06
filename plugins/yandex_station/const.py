import base64
from pathlib import Path

PLUGIN_DIR = Path(__file__).parent
CONFIG_FILE = PLUGIN_DIR / "config.json"

# Thanks to https://github.com/MarshalX/yandex-music-api/
CLIENT_ID = "23cabbbdc6cd418abb4b39c32c41195d"
CLIENT_SECRET = base64.b64decode("NTNiYzc1MjM4ZjBjNGQwOGExMThlNTFmZTkyMDMzMDA=").decode("ascii")
