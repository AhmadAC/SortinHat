# settings_manager.py
import json
import os
import pyttsx3 # For discovering TTS voices
from config import SETTINGS_FILENAME, DEFAULT_SETTINGS_TEMPLATE

class SettingsManager:
    def __init__(self, settings_file=SETTINGS_FILENAME, defaults_template=None):
        self.settings_file = settings_file
        self.defaults_template = defaults_template if defaults_template else DEFAULT_SETTINGS_TEMPLATE.copy()
        self.settings = self._load_or_create()

    def _populate_tts_voices(self, settings_data_to_update):
        """Populates the tts_settings.available_voices in the provided dictionary."""
        try:
            engine = pyttsx3.init()
            voices = engine.getProperty('voices')
            del engine

            current_voices_list = []
            if voices:
                for i, voice in enumerate(voices):
                    current_voices_list.append(
                        {"index": i, "id": voice.id, "name": voice.name, 
                         "lang": voice.languages, "gender": voice.gender}
                    )
            
            # Ensure tts_settings sub-dictionary exists
            if "tts_settings" not in settings_data_to_update:
                settings_data_to_update["tts_settings"] = self.defaults_template["tts_settings"].copy()

            settings_data_to_update["tts_settings"]["available_voices"] = current_voices_list
            if current_voices_list:
                # If selected_voice_index is invalid or not set, default to 0
                if not (0 <= settings_data_to_update["tts_settings"].get("selected_voice_index", -1) < len(current_voices_list)):
                    settings_data_to_update["tts_settings"]["selected_voice_index"] = 0
            else:
                settings_data_to_update["tts_settings"]["selected_voice_index"] = -1 # No voices available
            print("INFO: TTS voices discovery complete for settings.")
            return True # Indicates voices were (re)populated
        except Exception as e:
            print(f"ERROR: Could not populate TTS voices: {e}. TTS settings might be incomplete.")
            # Ensure tts_settings structure still exists
            if "tts_settings" not in settings_data_to_update:
                settings_data_to_update["tts_settings"] = self.defaults_template["tts_settings"].copy()
            if "available_voices" not in settings_data_to_update["tts_settings"]: # Should exist from copy
                settings_data_to_update["tts_settings"]["available_voices"] = []
            if "selected_voice_index" not in settings_data_to_update["tts_settings"]:
                 settings_data_to_update["tts_settings"]["selected_voice_index"] = -1
            return False

    def _load_or_create(self):
        current_defaults = self.defaults_template.copy()
        if not os.path.exists(self.settings_file):
            print(f"INFO: '{self.settings_file}' not found. Creating default settings file.")
            self._populate_tts_voices(current_defaults) # Populate voices in the new default set
            try:
                with open(self.settings_file, 'w') as f:
                    json.dump(current_defaults, f, indent=4)
                print(f"INFO: Default settings file '{self.settings_file}' created.")
                return current_defaults
            except IOError as e_io:
                print(f"ERROR: Could not write default settings file '{self.settings_file}': {e_io}")
                return current_defaults # Return in-memory defaults
        else:
            print(f"INFO: Loading settings from '{self.settings_file}'.")
            try:
                with open(self.settings_file, 'r') as f:
                    loaded_settings = json.load(f)
                
                is_updated = False
                # If tts_settings or available_voices is missing/empty, try to repopulate
                if not loaded_settings.get("tts_settings", {}).get("available_voices"):
                    print("INFO: TTS voices not found or empty in loaded settings, attempting to (re)populate.")
                    if self._populate_tts_voices(loaded_settings):
                        is_updated = True
                
                # Merge loaded settings with defaults to ensure all keys exist
                for key, default_value in self.defaults_template.items():
                    if key not in loaded_settings:
                        loaded_settings[key] = default_value
                        is_updated = True
                    elif isinstance(default_value, dict): # Merge sub-dictionaries (one level deep)
                        for sub_key, default_sub_value in default_value.items():
                            if sub_key not in loaded_settings.get(key, {}): # Check if sub_key exists in loaded_settings[key]
                                if key not in loaded_settings: loaded_settings[key] = {} # Ensure parent dict exists
                                loaded_settings[key][sub_key] = default_sub_value
                                is_updated = True
                
                if is_updated:
                    print(f"INFO: Settings were updated (missing keys/TTS voices). Saving changes to '{self.settings_file}'.")
                    try:
                        with open(self.settings_file, 'w') as f:
                            json.dump(loaded_settings, f, indent=4)
                    except IOError as e_io:
                        print(f"ERROR: Could not save updated settings file '{self.settings_file}': {e_io}")
                return loaded_settings
            except Exception as e:
                print(f"ERROR: Could not load or parse '{self.settings_file}': {e}. Using default template and attempting to save it.")
                self._populate_tts_voices(current_defaults) # Populate new defaults
                try:
                    with open(self.settings_file, 'w') as f:
                        json.dump(current_defaults, f, indent=4)
                    print(f"INFO: Replaced corrupted/unparsable settings file with new defaults.")
                except IOError as e_io:
                     print(f"ERROR: Could not write new default settings file after parse error: {e_io}")
                return current_defaults

    def get_setting(self, key_path, default_return=None):
        keys = key_path.split('.')
        value = self.settings
        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default_return

    def get_all_settings(self):
        return self.settings.copy()