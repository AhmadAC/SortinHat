# config.py
import os
from pwdeep import * # DEEPSEEK_API_KEY is here

# --- API Endpoints ---
# NOTE: The chat endpoint is different from the audio transcription endpoint.
DEEPSEEK_CHAT_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_STT_API_URL = "https://api.deepseek.com/v1/audio/transcriptions"


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
    "academy_name": "BIBS Magical Sorting Hat", 
    "house_system_name": "Scientist", 
    "custom_houses": ["Tesla", "Darwin", "Pythagoras", "Einstein"],
    "max_students_in_class": 8,
    "hat_characteristics": {
        # Simplified for Grade 6 ELL students
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
        "target_word_count_question": 25, # Adjusted for simpler questions
        "target_speech_duration_seconds": 0
    },
    "api_parameters": {
        "deepseek_temperature": 0.7, 
        "max_tokens_override": 0
    },
    "tts_settings": {
        "available_voices": [], 
        "selected_voice_index": 6,
        "tts_rate": 140 # Slower speed (was 200). 140-150 is a normal pace.
    },
    "stt_input_language_mode": 3 # 1: English, 2: Chinese (Mandarin), 3: English then Chinese
}
