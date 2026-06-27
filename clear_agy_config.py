import json
import os

config_path = os.path.expanduser('~/.gemini/config/config.json')

if os.path.exists(config_path):
    with open(config_path, 'r') as f:
        data = json.load(f)
    
    # We don't know the exact key, but let's clear anything related to auth or token
    # or just move the file to config.json.bak
    print("Keys found:", list(data.keys()))
    
    # Just backup and create a new empty one or remove userSettings.auth
    os.rename(config_path, config_path + ".bak")
    print("Moved config.json to config.json.bak")
else:
    print("config.json not found")
