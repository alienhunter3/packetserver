import os
import os.path
from configparser import ConfigParser
from pathlib import Path
from packetserver.client.cli.constants import DEFAULT_APP_DIR, DEFAULT_CONFIG_FILE

def default_app_dir() -> str:
    return os.path.join(str(Path.home()), DEFAULT_APP_DIR)

def config_path(app_path=default_app_dir()) -> str:
    return os.path.join(app_path, DEFAULT_CONFIG_FILE)

def get_config(config_file_path=config_path()) -> ConfigParser:
    config = ConfigParser()
    if os.path.isfile(config_file_path):
        config.read(config_file_path)

    if not 'cli' in config.sections():
        config.add_section('cli')

    if 'directory' not in config['cli']:
        config['cli']['directory'] = default_app_dir()

    return config