import os
import pytest
from core.database import SettingsDB

@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_settings.db"
    db = SettingsDB(str(db_file))
    yield db
    db.close()
    if db_file.exists():
        try:
            os.remove(db_file)
        except:
            pass

def test_global_settings(temp_db):
    # Test setting and getting global config values (which are JSON serialized)
    temp_db.set_global("hostname", "My Test PC")
    assert temp_db.get_global("hostname") == "My Test PC"
    
    # Test complex structures (lists/dicts)
    plugins = ["sys_info", "pc_system"]
    temp_db.set_global("active_plugins", plugins)
    assert temp_db.get_global("active_plugins") == plugins

    # Test default fallback
    assert temp_db.get_global("non_existent", "default_val") == "default_val"

def test_plugin_settings(temp_db):
    settings = {"interval": 5.0, "sensors": {"cpu": True}}
    temp_db.set_plugin_settings("my_plugin", settings)
    assert temp_db.get_plugin_settings("my_plugin") == settings
    
    assert temp_db.get_plugin_settings("non_existent_plugin") is None

def test_secrets(temp_db):
    secret_bytes = b"encrypted_aes_payload"
    temp_db.set_raw_secret("wifi_password", secret_bytes)
    assert temp_db.get_raw_secret("wifi_password") == secret_bytes
    
    assert temp_db.get_raw_secret("non_existent_secret") is None
