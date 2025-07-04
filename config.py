# config.py
import os

# --- DEEPSEEK API CONFIGURATION ---
# The API key is imported from pwdeep.py as requested.
# Ensure pwdeep.py exists in the same directory and contains your key.
try:
    from pwdeep import DEEPSEEK_API_KEY, DEEPSEEK_API_URL
    print("INFO: Successfully imported DEEPSEEK_API_KEY and DEEPSEEK_API_URL from pwdeep.py")
except ImportError:
    print("CRITICAL ERROR: Could not import from pwdeep.py. Please ensure the file exists and contains DEEPSEEK_API_KEY.")
    # Provide fallbacks so the application doesn't crash on startup
    DEEPSEEK_API_KEY = "PLACEHOLDER_KEY_IMPORT_FAILED"
    DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"

# Official DeepSeek API endpoint for Speech-to-Text, accessible in China.
DEEPSEEK_STT_API_URL = "https://api.deepseek.com/audio/transcriptions"

# --- File Configuration ---
AUDIO_FILENAME = "student_intro.wav"
SETTINGS_FILENAME = "settings.json"
HAT_GIF_FILENAME = "hat.gif"  # For speaking
HAT_THINK_GIF_FILENAME = "hat_think.gif" # For thinking/idle

MUSIC_FILENAME = "sortinghat_music.mp3"
# --- Audio Configuration ---
SAMPLE_RATE = 44100
CHANNELS = 1

# --- Default Application Settings (will be created/updated in settings.json) ---
DEFAULT_SETTINGS_TEMPLATE = {
    # NEW UI SETTINGS SECTION
    "ui_settings": {
        "dialogue_font_size": 28
    },
    "academy_name": "BIBS Magical Sorting Hat",
    "house_system_name": "Scientist",
    "custom_houses": ["Tesla", "Darwin", "Pythagoras", "Einstein"],
    "max_students_in_class": 8,
    "hat_characteristics": {
        "emotions_to_display": ["kind", "curious", "a little bit funny", "smart", "caring", "a good listener"],
        "speech_style_keywords": ["simple words", "clear sentences", "friendly", "for Grade 6 students", "easy to understand"]
    },
    "interaction_rules": {
        "ask_leading_question": True,
        "preamble_length_before_sorting": "medium",
        "sorting_must_occur_in_this_response": True,
        "minimum_questions_before_sorting": 1,
        "maximum_questions_before_sorting": 1
    },
    "response_formatting": {
        "target_word_count": 70,
        "target_word_count_question": 25,
        "target_speech_duration_seconds": 0
    },
    "api_parameters": {
        "deepseek_temperature": 0.7,
        "max_tokens_override": 0
    },
    "tts_settings": {
        "available_voices": [],
        "selected_voice_index": 6,
        "tts_rate": 140
    },
    "stt_input_language_mode": 3
}