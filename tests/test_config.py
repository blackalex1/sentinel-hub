import os
import pytest
from core.config import ConfigManager, MasterConfig

@pytest.fixture
def temp_config_manager(tmp_path):
    db_file = tmp_path / "test_config.db"
    manager = ConfigManager(str(db_file))
    yield manager
    manager.db.close()
    if db_file.exists():
        try:
            os.remove(db_file)
        except:
            pass

def test_config_initialization(temp_config_manager):
    cfg = temp_config_manager.get()
    assert isinstance(cfg, MasterConfig)
    assert cfg.hostname == "MonitHome PC"  # Default value
    assert len(cfg.server_uuid) > 0  # Should be auto-generated

def test_save_and_load_config(temp_config_manager):
    cfg = temp_config_manager.get()
    cfg.hostname = "Custom Hostname"
    cfg.theme_color = "0xFF00FF00"
    temp_config_manager.save()
    
    # Re-initialize to verify persistence
    db_path = temp_config_manager.db_path
    temp_config_manager.db.close()
    
    new_manager = ConfigManager(db_path)
    new_cfg = new_manager.get()
    assert new_cfg.hostname == "Custom Hostname"
    assert new_cfg.theme_color == "0xFF00FF00"
    new_manager.db.close()

def test_secrets_encryption(temp_config_manager):
    original_secret = "my_super_secret_token_123"
    temp_config_manager.set_secret("API_KEY", original_secret)
    
    # Read it back (should be transparently decrypted)
    retrieved = temp_config_manager.get_secret("API_KEY")
    assert retrieved == original_secret

    # Verify that it is actually encrypted in the DB raw column
    raw_secret = temp_config_manager.db.get_raw_secret("API_KEY")
    assert raw_secret is not None
    assert original_secret.encode() not in raw_secret  # Secret should not be in plaintext
