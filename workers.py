# workers.py
import sys
import os
import time
import wave
import json
import re

from PySide6.QtCore import QThread, Signal

# External library imports
import sounddevice as sd
from scipy.io.wavfile import write as write_wav
import numpy as np
import requests  # Used for DeepSeek API calls
import pyttsx3

# Local configuration imports
from config import (
    AUDIO_FILENAME, SAMPLE_RATE, CHANNELS, DEFAULT_SETTINGS_TEMPLATE,
    DEEPSEEK_API_KEY, DEEPSEEK_API_URL, DEEPSEEK_STT_API_URL # Import all required API info
)

# -----------------------------------------------------------------------------
# AudioRecorderWorker (No changes needed)
# This worker handles audio recording using the system's microphone.
# It does not make any network calls and works offline.
# -----------------------------------------------------------------------------
class AudioRecorderWorker(QThread):
    finished_signal = Signal(str)
    error_signal = Signal(str)
    status_signal = Signal(str)

    def __init__(self):
        super().__init__()
        self.recording = False
        self.frames = []
        print("DEBUG AudioRecorderWorker: Initialized.")

    def run(self):
        self.recording = True
        self.frames = []
        self.status_signal.emit("Recording... Speak into your microphone.")
        print("DEBUG AudioRecorderWorker: run() started, self.recording=True")
        try:
            try:
                sd.check_input_settings(samplerate=SAMPLE_RATE, channels=CHANNELS)
                print("DEBUG AudioRecorderWorker: Audio device check successful.")
            except Exception as device_check_error:
                err_msg = f"Audio device check failed: {device_check_error}."
                print(f"ERROR AudioRecorderWorker: {err_msg}")
                self.error_signal.emit(err_msg)
                self.status_signal.emit("Error: Audio device issue.")
                return

            with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, callback=self._callback,
                                 blocksize=int(SAMPLE_RATE * 0.1), dtype='float32'):
                print("DEBUG AudioRecorderWorker: InputStream started.")
                while self.recording:
                    self.msleep(50)

            print("DEBUG AudioRecorderWorker: self.recording is False, exited recording loop.")

            if not self.frames:
                self.status_signal.emit("No audio recorded.")
                self.finished_signal.emit("")
                print("DEBUG AudioRecorderWorker: No frames recorded.")
                return

            self.status_signal.emit("Processing recorded audio...")
            audio_data_float = np.concatenate(self.frames, axis=0)

            if np.issubdtype(audio_data_float.dtype, np.integer):
                max_val = np.iinfo(audio_data_float.dtype).max
                audio_data_float = audio_data_float.astype(np.float32) / max_val
            elif audio_data_float.dtype == np.float64:
                 audio_data_float = audio_data_float.astype(np.float32)

            audio_data_float = np.clip(audio_data_float, -1.0, 1.0)
            audio_data_int16 = (audio_data_float * 32767).astype(np.int16)

            write_wav(AUDIO_FILENAME, SAMPLE_RATE, audio_data_int16)
            self.finished_signal.emit(AUDIO_FILENAME)
            print(f"DEBUG AudioRecorderWorker: Finished, emitted audio file: {AUDIO_FILENAME}")

        except sd.PortAudioError as pae:
            detailed_error = f"PortAudio error: {pae}."
            print(f"ERROR AudioRecorderWorker: {detailed_error}")
            self.error_signal.emit(detailed_error)
            self.status_signal.emit(f"Error: {detailed_error.split('.')[0]}")
        except Exception as e:
            print(f"ERROR AudioRecorderWorker: Unexpected error: {e}")
            self.error_signal.emit(f"Audio recording error: {e}")
            self.status_signal.emit(f"Error during recording: {e}")
        finally:
            print("DEBUG AudioRecorderWorker: run() method finished.")

    def _callback(self, indata, frames, time_info, status):
        if status:
            print(f"DEBUG Audio callback status: {status}")
        if self.recording:
            self.frames.append(indata.copy())

    def stop_recording(self):
        print("DEBUG AudioRecorderWorker: stop_recording() called.")
        if self.recording:
            self.recording = False
            self.status_signal.emit("Stopping recording...")
            print("DEBUG AudioRecorderWorker: self.recording flag set to False.")
        else:
            print("DEBUG AudioRecorderWorker: stop_recording() called but already not recording.")


# -----------------------------------------------------------------------------
# SpeechToTextWorker (MODIFIED)
# This worker now sends audio to the DeepSeek STT API instead of Google.
# It no longer uses the `speech_recognition` library.
# -----------------------------------------------------------------------------
class SpeechToTextWorker(QThread):
    finished_signal = Signal(str)
    error_signal = Signal(str)
    status_signal = Signal(str)

    def __init__(self, audio_filepath, stt_input_language_mode=1):
        super().__init__()
        self.audio_filepath = audio_filepath
        self.stt_input_language_mode = stt_input_language_mode
        print(f"DEBUG SpeechToTextWorker: Initialized with STT Mode: {self.stt_input_language_mode}")

    def _transcribe_with_deepseek(self, language_code):
        """Helper method to call the DeepSeek STT API."""
        self.status_signal.emit(f"Transcribing ({language_code.upper()})...")
        print(f"DEBUG STT: Calling DeepSeek STT API with lang='{language_code}'")

        headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}"}
        
        with open(self.audio_filepath, 'rb') as f:
            files = {'file': (os.path.basename(self.audio_filepath), f, 'audio/wav')}
            data = {
                'model': 'deepseek-whisper',
                'language': language_code
            }
            response = requests.post(DEEPSEEK_STT_API_URL, headers=headers, files=files, data=data, timeout=60)

        response.raise_for_status()  # Raises HTTPError for bad responses (4xx or 5xx)
        response_data = response.json()

        transcribed_text = response_data.get('text', '').strip()
        if not transcribed_text:
            raise ValueError(f"API returned empty transcription for lang='{language_code}'.")
        
        print(f"DEBUG STT: Success with lang='{language_code}'. Text: {transcribed_text}")
        return transcribed_text

    def run(self):
        self.status_signal.emit("Preparing to transcribe audio...")
        print(f"DEBUG STT Worker: Starting run(). Processing file: '{self.audio_filepath}', STT Mode: {self.stt_input_language_mode}")

        if not os.path.exists(self.audio_filepath) or os.path.getsize(self.audio_filepath) < 1024:
            err_msg = f"Audio file for STT not found or is empty: {self.audio_filepath}"
            print(f"ERROR STT Worker: {err_msg}")
            self.error_signal.emit(err_msg)
            self.status_signal.emit("STT Error: Audio file missing or empty.")
            return

        try:
            lang_map = {
                1: ["en"],          # English only
                2: ["zh"],          # Chinese only
                3: ["en", "zh"]     # Try English, then Chinese
            }
            langs_to_try = lang_map.get(self.stt_input_language_mode, ["en"])

            last_error = None
            for lang_code in langs_to_try:
                try:
                    text = self._transcribe_with_deepseek(lang_code)
                    self.status_signal.emit("Transcription successful.")
                    self.finished_signal.emit(text)
                    return  # Success, exit the worker
                except Exception as e:
                    print(f"INFO STT Worker: Attempt with lang='{lang_code}' failed: {e}")
                    last_error = e

            # If the loop finishes, all attempts failed.
            if last_error:
                raise last_error # Re-raise the last error to be caught below
            else:
                raise Exception("No languages were attempted for STT (internal error).")

        except requests.exceptions.RequestException as e:
            err_msg = f"STT Network Error: {e}"
            print(f"ERROR STT Worker: {err_msg}")
            self.error_signal.emit(err_msg)
            self.status_signal.emit("STT network connection error.")
        except Exception as e:
            err_msg = f"STT failed after all attempts: {e}"
            print(f"ERROR STT Worker: {err_msg}")
            self.error_signal.emit(err_msg)
            self.status_signal.emit("Could not understand audio.")
        finally:
            print("DEBUG STT Worker: run() method finished.")


# -----------------------------------------------------------------------------
# DeepSeekWorker (No changes needed)
# This worker handles the chat completions API call to DeepSeek.
# Its existing implementation is correct and works in China.
# -----------------------------------------------------------------------------
class DeepSeekWorker(QThread):
    finished_signal = Signal(str)
    error_signal = Signal(str)
    status_signal = Signal(str)

    def __init__(self, user_text, conversation_step, questions_for_this_round, hat_tone="friendly", settings=None):
        super().__init__()
        self.user_text = user_text
        self.conversation_step = conversation_step
        self.questions_for_this_round = questions_for_this_round
        self.hat_tone = hat_tone
        self.settings = settings if isinstance(settings, dict) else DEFAULT_SETTINGS_TEMPLATE.copy()
        print(f"DEBUG DeepSeekWorker: Initialized. Step: {conversation_step}, Total Q's: {self.questions_for_this_round}, Tone: {hat_tone}")

    def get_setting(self, keys_str, default_val=None):
        current_val = self.settings
        try:
            for key in keys_str.split('.'):
                current_val = current_val[key]
            return current_val
        except (KeyError, TypeError):
            current_val_default_template = DEFAULT_SETTINGS_TEMPLATE
            try:
                for key in keys_str.split('.'):
                    current_val_default_template = current_val_default_template[key]
                return current_val_default_template
            except (KeyError, TypeError):
                return default_val

    def get_system_prompt(self):
        academy_name = self.get_setting("academy_name", "The Grand Academy")
        house_system_name = self.get_setting("house_system_name", "Great Houses")
        custom_houses_list = self.get_setting("custom_houses", ["Gryffindor", "Hufflepuff", "Ravenclaw", "Slytherin"])

        if isinstance(custom_houses_list, list) and len(custom_houses_list) > 0:
            if len(custom_houses_list) > 1:
                houses_string = ", ".join(custom_houses_list[:-1]) + ", or " + custom_houses_list[-1]
            else:
                houses_string = custom_houses_list[0]
        else:
            houses_string = "a default house (if none are configured)"
            print("WARNING: custom_houses in settings is not a valid list or is empty.")

        prompt_parts = [
            f"You are an AI Sorting Hat for the {academy_name}. You are very old and very smart.",
            "Your job is to talk to a Grade 6 student who is learning English. Use VERY simple words and short sentences. Be friendly and easy to understand.",
            "Speak DIRECTLY to the student as the Sorting Hat. Do NOT say things like 'Here is my response:'. Just start talking.",
            f"For this talk, your main personality is: {self.hat_tone}."
        ]

        if self.conversation_step < self.questions_for_this_round:
            question_number = self.conversation_step + 1
            if self.conversation_step == 0:
                prompt_parts.append(f"This is your first time talking. Ask the student your Question {question_number} to learn about them. For example: 'Hello! What is your name?' or 'Tell me, what do you like to do for fun?'. Keep your question short and simple. Do NOT sort the student yet.")
            else:
                prompt_parts.append(f"The student answered your last question. Now, ask your Question {question_number}. It should be a new, simple question to learn more about them. For example: 'What makes you feel brave?' or 'What is your favorite subject in school?'. Do NOT sort the student yet.")

        elif self.conversation_step == self.questions_for_this_round:
            max_students = self.get_setting("max_students_in_class", 20)
            num_houses = len(custom_houses_list) if custom_houses_list and isinstance(custom_houses_list, list) and len(custom_houses_list) > 0 else 4
            group_balance_info = ""
            if num_houses > 0:
                try:
                    max_students = int(max_students)
                    base_size = max_students // num_houses
                    remainder = max_students % num_houses
                    group_sizes = {}
                    for i in range(num_houses):
                        size = base_size + 1 if i < remainder else base_size
                        if size in group_sizes:
                            group_sizes[size] += 1
                        else:
                            group_sizes[size] = 1
                    size_descriptions = []
                    for size, count in sorted(group_sizes.items(), reverse=True):
                        group_str = "group" if count == 1 else "groups"
                        student_str = "student" if size == 1 else "students"
                        size_descriptions.append(f"{count} {group_str} with {size} {student_str}")
                    group_balance_info = (f"The maximum class size is {max_students}. To keep the houses balanced, "
                                          f"they should be organized as evenly as possible: {', and '.join(size_descriptions)}. "
                                          "Keep this principle of balance in mind when you are sorting.")
                except (ValueError, TypeError):
                    group_balance_info = "Your goal is to keep the houses balanced."
                    print(f"WARNING: max_students_in_class ('{max_students}') is not a valid number. Using default balance prompt.")

            prompt_parts.append(f"You have asked all your questions. This is your final answer. Based on what the student said, you MUST choose one of these {house_system_name} for them: {houses_string}. {group_balance_info} Tell them the house and give a short, simple reason why you chose it. You MUST sort them now.")

        else:
             prompt_parts.append(f"Something is wrong. Just sort the student into one of the {house_system_name}: {houses_string}. Give a simple reason.")

        word_target_q = self.get_setting("response_formatting.target_word_count_question", 25)
        word_target_sort = self.get_setting("response_formatting.target_word_count", 70)

        is_question_turn = (self.conversation_step < self.questions_for_this_round)
        if is_question_turn:
             prompt_parts.append(f"Your question should be about {word_target_q} words long.")
        else:
             prompt_parts.append(f"Your full answer should be about {word_target_sort} words long.")

        prompt_parts.append(f"Only use the house names I gave you: {houses_string}. Do not use stars (*) or long dashes (—) in your answer.")
        return " ".join(prompt_parts)

    def construct_user_message(self):
        if self.conversation_step == 0 and self.user_text is None:
            return "Please give me your first question for the student."
        elif self.user_text:
            return f"The student says: \"{self.user_text}\"."
        else:
            if self.conversation_step > 0:
                 return "The student's answer was not heard. Please ask another question to keep the conversation going."
            else:
                 return "The student is ready for your first question."

    def run(self):
        if not DEEPSEEK_API_KEY or DEEPSEEK_API_KEY == "PLACEHOLDER_KEY_IMPORT_FAILED":
            self.error_signal.emit("DEEPSEEK_API_KEY not set or failed to import from pwdeep.py.")
            self.status_signal.emit("API Error: Key not configured.")
            return
        if not DEEPSEEK_API_URL:
            self.error_signal.emit("DEEPSEEK_API_URL not configured.")
            self.status_signal.emit("API Error: URL not configured.")
            return

        self.status_signal.emit(f"The {self.get_setting('academy_name', 'SortingHat')} is thinking...")
        system_prompt = self.get_system_prompt()
        user_message_content = self.construct_user_message()

        print(f"DEBUG DeepSeekWorker: Step: {self.conversation_step}, Total Q's: {self.questions_for_this_round}, User Text: '{self.user_text}'")
        print(f"DEBUG DeepSeekWorker: System Prompt:\n{system_prompt}\n---")
        print(f"DEBUG DeepSeekWorker: User Message to API: {user_message_content}")

        headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
        api_temp = float(self.get_setting("api_parameters.deepseek_temperature", 0.7))
        max_tokens_override = int(self.get_setting("api_parameters.max_tokens_override", 0))
        is_question_turn = (self.conversation_step < self.questions_for_this_round)
        max_tokens = 80 if is_question_turn else 200
        if max_tokens_override > 0: max_tokens = max_tokens_override

        print(f"DEBUG DeepSeek API: max_tokens: {max_tokens}, temperature: {api_temp}")
        payload = {
            "model": "deepseek-chat",
            "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_message_content}],
            "max_tokens": max_tokens,
            "temperature": api_temp,
        }
        try:
            response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            response_data = response.json()

            if "choices" in response_data and len(response_data["choices"]) > 0:
                message_content = response_data["choices"][0].get("message", {}).get("content")
                if message_content:
                    print(f"DEBUG DeepSeekWorker: API Response Content: {message_content[:200]}...")
                    self.finished_signal.emit(message_content.strip())
                else:
                    self.error_signal.emit("DeepSeek API: Empty message content in response.")
                    print(f"ERROR DeepSeekWorker: Empty message content. Full response: {response_data}")
            else:
                err_detail = response_data.get('error', response_data)
                self.error_signal.emit(f"DeepSeek API Error: Malformed response or error structure: {err_detail}")
                print(f"ERROR DeepSeekWorker: Malformed response. Full response: {response_data}")
        except requests.exceptions.Timeout:
            self.error_signal.emit("DeepSeek API request timed out.")
            self.status_signal.emit("API Error: Timeout.")
        except requests.exceptions.HTTPError as http_err:
            err_body = http_err.response.text if http_err.response else "No response body"
            self.error_signal.emit(f"DeepSeek API HTTP Error: {http_err}. Body: {err_body}")
            self.status_signal.emit(f"API Error: HTTP {http_err.response.status_code if http_err.response else 'N/A'}")
        except requests.exceptions.RequestException as req_err:
            self.error_signal.emit(f"DeepSeek API Request Failed: {req_err}")
            self.status_signal.emit("API Error: Request failed.")
        except Exception as e:
            self.error_signal.emit(f"Error processing DeepSeek response: {e}")
            self.status_signal.emit(f"API Error: Processing error.")
        finally:
            print("DEBUG DeepSeekWorker: run() method finished.")


# -----------------------------------------------------------------------------
# TextToSpeechWorker (No changes needed)
# This worker uses pyttsx3, which relies on offline system voices.
# It does not make any network calls and works in China.
# -----------------------------------------------------------------------------
class TextToSpeechWorker(QThread):
    finished_signal = Signal()
    error_signal = Signal(str)
    status_signal = Signal(str)

    def __init__(self, text_to_speak, tts_settings):
        super().__init__()
        self.raw_text_to_speak = text_to_speak
        self.tts_settings = tts_settings if isinstance(tts_settings, dict) else \
                            DEFAULT_SETTINGS_TEMPLATE["tts_settings"].copy()
        self.engine = None
        self._should_stop = False
        self._engine_initialized_successfully = False
        print("DEBUG TTS Worker: Initialized.")

    def _filter_text_for_tts(self, text):
        if not isinstance(text, str): text = str(text)
        print(f"TTS_FILTER: Original In: '{text}'")
        filtered_text = text.replace("—", ", ")
        filtered_text = filtered_text.replace("*", "")
        filtered_text = re.sub(r'[^\w\s\'\.,?!:"“”‘’()-]', '', filtered_text)
        filtered_text = re.sub(r'\s+', ' ', filtered_text).strip()
        print(f"TTS_FILTER: Filtered Out: '{filtered_text}'")
        return filtered_text

    def _initialize_engine(self):
        if self.engine is not None: return True

        try:
            self.engine = pyttsx3.init()
            if not self.engine:
                self.error_signal.emit("Failed to initialize Text-to-Speech engine (pyttsx3.init() returned None).")
                self.status_signal.emit("TTS Error: Engine init failed.")
                return False

            self._engine_initialized_successfully = True

            engine_voices = self.engine.getProperty('voices')
            selected_voice_index = int(self.tts_settings.get("selected_voice_index", 0))
            target_tts_rate = int(self.tts_settings.get("tts_rate", DEFAULT_SETTINGS_TEMPLATE["tts_settings"]["tts_rate"]))

            voice_id_to_use = None
            available_voices_from_settings = self.tts_settings.get("available_voices", [])

            if available_voices_from_settings and \
               0 <= selected_voice_index < len(available_voices_from_settings):
                voice_id_to_use = available_voices_from_settings[selected_voice_index].get("id")

            if voice_id_to_use:
                found_by_id = any(v.id == voice_id_to_use for v in engine_voices)
                if found_by_id:
                    self.engine.setProperty('voice', voice_id_to_use)
                    print(f"INFO: TTS: Using voice (ID from settings): {available_voices_from_settings[selected_voice_index].get('name', voice_id_to_use)}")
                else:
                    print(f"WARNING: TTS: Voice ID '{voice_id_to_use}' from settings not found. Falling back.")
                    voice_id_to_use = None

            if not voice_id_to_use and engine_voices:
                actual_index = selected_voice_index if 0 <= selected_voice_index < len(engine_voices) else 0
                if not (0 <= selected_voice_index < len(engine_voices)):
                     print(f"WARNING: TTS: Voice index {selected_voice_index} invalid for current {len(engine_voices)} voices. Using index {actual_index}.")
                chosen_voice = engine_voices[actual_index]
                self.engine.setProperty('voice', chosen_voice.id)
                print(f"INFO: TTS: Using voice (engine index {actual_index}): {chosen_voice.name}")
            elif not engine_voices:
                self.status_signal.emit("Warning: No TTS voices found by engine. Using system default.")
                print("WARNING: TTS: No voices found by pyttsx3. Using system default.")

            print(f"INFO: TTS: Setting rate to: {target_tts_rate} wpm")
            self.engine.setProperty('rate', target_tts_rate)
            self.engine.setProperty('volume', 0.9)
            return True

        except Exception as e:
            err_msg = f"TTS engine initialization error: {e}"
            print(f"ERROR TTS Worker: {err_msg}")
            self.error_signal.emit(err_msg)
            self.status_signal.emit(f"TTS Error: {e}")
            self.engine = None
            self._engine_initialized_successfully = False
            return False

    def run(self):
        self.status_signal.emit("The Sorting Hat is preparing to speak...")
        self.text_to_speak = self._filter_text_for_tts(self.raw_text_to_speak)

        if not self.text_to_speak:
            self.error_signal.emit("Text to speak is empty after filtering.")
            self.status_signal.emit("TTS Error: No speakable text.")
            self.finished_signal.emit()
            return

        print(f"DEBUG TTS Worker: run() started. Text: '{self.text_to_speak[:100]}...'")

        if not self._initialize_engine():
            self.finished_signal.emit()
            return

        try:
            if self._should_stop:
                 print("DEBUG TTS Worker: Stop signal received before engine.say(), skipping speech.")
            else:
                self.engine.say(self.text_to_speak)
                print("DEBUG TTS Worker: Before engine.runAndWait().")
                self.engine.runAndWait()
                print("DEBUG TTS Worker: After engine.runAndWait().")

            if not self._should_stop:
                self.status_signal.emit("The Sorting Hat has spoken.")
            else:
                self.status_signal.emit("Speech was interrupted.")

        except RuntimeError as e:
            err_msg = f"Text-to-Speech (TTS) RuntimeError: {e}"
            print(f"ERROR TTS Worker: {err_msg}")
            self.error_signal.emit(err_msg)
            self.status_signal.emit(f"TTS Error: {e}")
        except Exception as e:
            err_msg = f"Unexpected Text-to-Speech (TTS) error: {e}"
            print(f"ERROR TTS Worker: {err_msg}")
            self.error_signal.emit(err_msg)
            self.status_signal.emit(f"TTS Error: {e}")
        finally:
            print("DEBUG TTS Worker: run() method finished. Emitting finished_signal.")
            self.finished_signal.emit()

    def stop_tts_signal(self):
        print("DEBUG TTS Worker: stop_tts_signal() called.")
        self._should_stop = True
        if hasattr(self, 'engine') and self.engine is not None and self._engine_initialized_successfully:
            try:
                print("DEBUG TTS Worker: Attempting engine.stop() due to stop_tts_signal.")
                self.engine.stop()
            except Exception as e:
                print(f"DEBUG TTS Worker: Exception during engine.stop() in stop_tts_signal: {e}")
        else:
            print("DEBUG TTS Worker: Engine not available or not initialized for stop_tts_signal.")