# sorting_hat_app.py
import sys
import os
import time 
import random

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QWidget, QTextEdit, QComboBox, QMessageBox, QSizePolicy,
    QSpacerItem, QSlider, QToolButton 
)
from PySide6.QtCore import Qt, Slot, QTimer, QSize 
from PySide6.QtGui import QIcon 

from config import HAT_GIF_FILENAME, HAT_THINK_GIF_FILENAME, DEEPSEEK_API_KEY, MUSIC_FILENAME
from settings_manager import SettingsManager
from workers import AudioRecorderWorker, SpeechToTextWorker, DeepSeekWorker, TextToSpeechWorker
from animation_handler import AnimationHandler
from media_players import BackgroundMusicPlayer 


# Define a constant for the state after sorting is done
FINAL_SORTING_STEP_COMPLETE = 99 # Arbitrary number greater than max questions

class SortingHatApp(QMainWindow):
    def __init__(self):
        super().__init__()
        
        self._is_shutting_down = False 

        self.settings_manager = SettingsManager()
        self.settings = self.settings_manager.get_all_settings() 

        academy_name = self.settings_manager.get_setting("academy_name", "AI Sorting Hat")
        self.setWindowTitle(f"The {academy_name} Sorting Hat")

        if not DEEPSEEK_API_KEY or DEEPSEEK_API_KEY == "YOUR_DEEPSEEK_API_KEY":
            QMessageBox.critical(self, "API Key Error",
                                 "DEEPSEEK_API_KEY not found or not set. "
                                 "Please configure it and restart the application.")

        self._init_ui_elements() 

        self.animation_handler = AnimationHandler(
            self.animation_display_label, 
            HAT_GIF_FILENAME,         
            HAT_THINK_GIF_FILENAME,   
            parent=self
        )
        self.animation_handler.animation_error_signal.connect(self._handle_ui_error)
        self.animation_handler.animation_status_signal.connect(self._update_status_bar)
        self.animation_handler.animation_cycle_complete_signal.connect(self.on_animation_cycle_completed)

        self.recorder_worker: AudioRecorderWorker | None = None
        self.stt_worker: SpeechToTextWorker | None = None
        self.deepseek_worker: DeepSeekWorker | None = None
        self.tts_worker: TextToSpeechWorker | None = None
        
        self.current_oracle_state = "idle" 
        self.interaction_step = 0 
        
        self.questions_to_ask_this_session = 0
        print(f"INFO: SortingHatApp initialized.")

        initial_bg_volume_slider_value = 15
        normalized_initial_slider_value = initial_bg_volume_slider_value / 100.0
        power_exponent = 2.5 
        initial_actual_volume = 0.0
        if normalized_initial_slider_value > 0:
            initial_actual_volume = normalized_initial_slider_value ** power_exponent
        
        self.music_player = BackgroundMusicPlayer(MUSIC_FILENAME, initial_volume=initial_actual_volume, parent=self)
        self.music_player.error_occurred.connect(self._on_music_player_error)
        self.music_player.mute_changed.connect(self._update_mute_button_icon) 

        self.volume_slider.setValue(initial_bg_volume_slider_value) 
        self._update_mute_button_icon(self.music_player.is_muted())

        self._reset_interaction_flow_and_ui(initial_message="Waiting for a lucky student...") 
        self.setFocusPolicy(Qt.StrongFocus)
        self.setFocus() 

    def _init_ui_elements(self):
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        main_layout = QVBoxLayout(self.central_widget)
        main_layout.setContentsMargins(10, 2, 10, 10) 

        top_bar_layout = QHBoxLayout()
        self.activate_hat_button = QPushButton("Activate Sorting Hat (3)")
        self.activate_hat_button.clicked.connect(self.activate_oracle_interaction)
        self.record_button = QPushButton("Start Recording (1)")
        self.record_button.clicked.connect(self.start_recording_router)
        self.stop_button = QPushButton("Stop Recording (2)")
        self.stop_button.clicked.connect(self.stop_audio_recording)
        
        top_bar_layout.addWidget(self.activate_hat_button)
        top_bar_layout.addWidget(self.record_button)
        top_bar_layout.addWidget(self.stop_button)
        top_bar_layout.addStretch(1) 

        music_controls_layout = QHBoxLayout()
        music_controls_layout.setSpacing(5) 
        self.mute_button = QToolButton()
        self.mute_button.setToolTip("Mute/Unmute Background Music")
        self.mute_button.setIconSize(QSize(24, 24)) 
        self.mute_button.clicked.connect(self._toggle_music_mute)

        # --- FIX 1: Removed icon logic, forcing text-based button ---
        print("INFO: Mute button is using text labels (icons removed).")
        self.mute_button.setText("Mute")
        self.mute_button.setFixedSize(60, 28)
        # --- End of FIX 1 ---

        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setToolTip("Adjust Background Music Volume")
        self.volume_slider.setRange(0, 100); self.volume_slider.setFixedWidth(100) 
        self.volume_slider.valueChanged.connect(self._change_music_volume)
        music_controls_layout.addWidget(self.mute_button)
        music_controls_layout.addWidget(QLabel("Vol:")) 
        music_controls_layout.addWidget(self.volume_slider)
        top_bar_layout.addLayout(music_controls_layout)
        main_layout.addLayout(top_bar_layout) 
        
        BG_COLOR = "#202123"; INPUT_BG_COLOR = "#40414f"; TEXT_COLOR = "#ececf1"
        self.setStyleSheet(f"""
            QMainWindow {{ background-color: {BG_COLOR}; }} QWidget {{ background-color: {BG_COLOR}; color: {TEXT_COLOR}; font-family: "Segoe UI", Arial, sans-serif; font-size: 9.5pt; }} QLabel {{ color: {TEXT_COLOR}; padding: 2px; }} QLabel#titleLabel {{ font-size: 16pt; font-weight: bold; color: {TEXT_COLOR}; margin-bottom: 2px; qproperty-alignment: 'AlignCenter'; }} QLabel#statusLabel {{ color: #a9aaae; font-style: italic; margin-bottom: 5px; qproperty-alignment: 'AlignCenter'; }} QLabel#animationLabel {{ background-color: black; border: 1px solid #40414f; qproperty-alignment: 'AlignCenter'; }} QPushButton, QToolButton {{ background-color: #343541; color: {TEXT_COLOR}; border: 1px solid #565869; padding: 8px 15px; border-radius: 5px; font-weight: 500; }} QToolButton {{ padding: 4px; }} QPushButton:hover, QToolButton:hover {{ background-color: #4a4b57; }} QPushButton:disabled, QToolButton:disabled {{ background-color: #2a2b32; color: #6a6b70; border: 1px solid #40414f; }} QTextEdit {{ background-color: {INPUT_BG_COLOR}; border: 1px solid #565869; color: {TEXT_COLOR}; border-radius: 5px; padding: 6px; }} QComboBox {{ background-color: {INPUT_BG_COLOR}; border: 1px solid #565869; padding: 7px 9px; border-radius: 5px; min-width: 140px; }} QComboBox::drop-down {{ border: none; background-color: transparent; }} QComboBox::down-arrow {{ image: url(none); }} QComboBox QAbstractItemView {{ background-color: {INPUT_BG_COLOR}; border: 1px solid #565869; color: {TEXT_COLOR}; selection-background-color: #4a4b57; }} QMessageBox {{ background-color: {INPUT_BG_COLOR}; font-size: 9pt; }} QMessageBox QLabel {{ color: {TEXT_COLOR}; }} QMessageBox QPushButton {{ background-color: #343541; min-width: 70px; padding: 6px 12px;}} QSlider::groove:horizontal {{ border: 1px solid #565869; height: 8px; background: {INPUT_BG_COLOR}; margin: 2px 0; border-radius: 4px; }} QSlider::handle:horizontal {{ background: #8e8e90; border: 1px solid #565869; width: 14px; margin: -4px 0; border-radius: 7px; }} QSlider::handle:horizontal:hover {{ background: #a9aaae; }}
        """)
        self.title_label = QLabel(self.settings_manager.get_setting("academy_name", "AI Sorting Hat")); self.title_label.setObjectName("titleLabel"); main_layout.addWidget(self.title_label)
        self.status_label = QLabel("Status: Initializing..."); self.status_label.setObjectName("statusLabel"); main_layout.addWidget(self.status_label)
        self.animation_display_label = QLabel(); self.animation_display_label.setObjectName("animationLabel"); self.animation_display_label.setMinimumHeight(250); self.animation_display_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding); self.animation_display_label.setAlignment(Qt.AlignCenter); main_layout.addWidget(self.animation_display_label)
        config_row_layout = QHBoxLayout(); self.primary_characteristic_label = QLabel("Primary Characteristic:"); self.primary_characteristic_combo = QComboBox()
        emotions_list = self.settings_manager.get_setting("hat_characteristics.emotions_to_display", []); emotions_list = emotions_list if emotions_list and isinstance(emotions_list, list) else ["friendly", "wise", "perceptive"]
        for emotion in emotions_list: self.primary_characteristic_combo.addItem(str(emotion).capitalize(), str(emotion))
        if self.primary_characteristic_combo.count() > 0: self.primary_characteristic_combo.setCurrentIndex(0) 
        config_row_layout.addWidget(self.primary_characteristic_label); config_row_layout.addWidget(self.primary_characteristic_combo); config_row_layout.addStretch(); main_layout.addLayout(config_row_layout); main_layout.addSpacing(5)
        text_areas_layout = QHBoxLayout(); oracle_response_layout = QVBoxLayout(); self.oracle_response_label = QLabel(f"{self.settings_manager.get_setting('academy_name', 'Sorting Oracle')}:"); self.oracle_response_text = QTextEdit(); self.oracle_response_text.setReadOnly(True); oracle_response_layout.addWidget(self.oracle_response_label); oracle_response_layout.addWidget(self.oracle_response_text)
        your_text_layout = QVBoxLayout(); self.your_text_label = QLabel("You:"); self.your_text_output = QTextEdit(); self.your_text_output.setReadOnly(True); your_text_layout.addWidget(self.your_text_label); your_text_layout.addWidget(self.your_text_output)
        text_areas_layout.addLayout(oracle_response_layout, 2); text_areas_layout.addLayout(your_text_layout, 1); main_layout.addLayout(text_areas_layout)

    @Slot(str)
    def _update_status_bar(self, message: str):
        if self._is_shutting_down: return 
        if hasattr(self, 'status_label') and self.status_label:
            self.status_label.setText(f"Status: {message}")

    def _stop_all_active_workers(self):
        print("DEBUG: Stopping all active workers due to interrupt/reset.")
        self._safe_stop_worker(self.recorder_worker, "AudioRecorder (interrupt)", timeout_ms=1000)
        self.recorder_worker = None
        self._safe_stop_worker(self.stt_worker, "SpeechToText (interrupt)", timeout_ms=1000)
        self.stt_worker = None
        self._safe_stop_worker(self.deepseek_worker, "DeepSeek (interrupt)", timeout_ms=1500)
        self.deepseek_worker = None
        self._safe_stop_worker(self.tts_worker, "TextToSpeech (interrupt)", timeout_ms=1500)
        self.tts_worker = None
        QApplication.instance().processEvents()

    def _reset_interaction_flow_and_ui(self, initial_message="Waiting for a lucky student..."):
        if self._is_shutting_down: return
        print(f"DEBUG: _reset_interaction_flow_and_ui called with message: '{initial_message}'")
        
        self._stop_all_active_workers() 

        self.questions_to_ask_this_session = random.randint(3, 5)
        print(f"DEBUG: New session started. The hat will ask {self.questions_to_ask_this_session} questions before sorting.")

        self.interaction_step = 0
        self.current_oracle_state = "idle" 
        
        self.activate_hat_button.setEnabled(True)
        self.record_button.setEnabled(True)
        self.stop_button.setEnabled(False) 

        if hasattr(self, 'oracle_response_text'): self.oracle_response_text.clear()
        if hasattr(self, 'your_text_output'): self.your_text_output.clear()

        self._update_status_bar(initial_message)
        if hasattr(self, '_just_sorted_flag'): del self._just_sorted_flag 
        
        if self.animation_handler:
            print("DEBUG: _reset_interaction_flow_and_ui calling set_thinking_animation.")
            self.animation_handler.set_thinking_animation(loop=True) 
        else: 
            self.on_animation_cycle_completed() 

    def complete_initial_setup(self):
        if self._is_shutting_down: return
        print("SORTING_HAT_APP: complete_initial_setup called.")
        if self.animation_handler:
            print("DEBUG: complete_initial_setup calling setup_initial_display.")
            self.animation_handler.setup_initial_display() 
        else:
            self._reset_interaction_flow_and_ui() 

    @Slot() 
    def on_animation_cycle_completed(self):
        if self._is_shutting_down: return
        print(f"SORTING_HAT_APP: SLOT on_animation_cycle_completed. Oracle: {self.current_oracle_state}, App Interaction Step: {self.interaction_step}")
        
        if self.interaction_step == 0 and self.current_oracle_state == "idle":
            if hasattr(self, '_just_sorted_flag') and self._just_sorted_flag:
                self._update_status_bar("Sorting complete. Waiting for the next student...")
            else:
                self._update_status_bar("Waiting for a lucky student...")
            self.activate_hat_button.setEnabled(True) 
            self.record_button.setEnabled(True)
            self.stop_button.setEnabled(False)
        elif self.interaction_step > 0 and self.interaction_step < FINAL_SORTING_STEP_COMPLETE:
             self._update_status_bar(f"Oracle awaits your answer to question {self.interaction_step}...")

        self.setFocus() 
        print(f"UI_LOG: Anim cycle done. App Interaction Step: {self.interaction_step}. ActBtn: {self.activate_hat_button.isEnabled()}, RecBtn: {self.record_button.isEnabled()}, StopBtn: {self.stop_button.isEnabled()}")

    def _prepare_for_oracle_thinking(self, status_message="Oracle is contemplating..."):
        if self._is_shutting_down: return
        self._update_status_bar(status_message)
        self.stop_button.setEnabled(False) 
        
        if self.animation_handler:
            print("DEBUG: _prepare_for_oracle_thinking calling set_thinking_animation.")
            self.animation_handler.set_thinking_animation(loop=True) 
        self.current_oracle_state = "thinking"

    def activate_oracle_interaction(self):
        if self._is_shutting_down: return
        print("DEBUG: activate_oracle_interaction clicked (Hat initiates).")
        
        self._reset_interaction_flow_and_ui("Activating Oracle...") 
        self.interaction_step = 0 

        self._update_status_bar("Oracle is preparing its first question...")
        self.current_oracle_state = "thinking" 
        
        selected_primary_char = self.primary_characteristic_combo.currentData() or "friendly"

        self.deepseek_worker = DeepSeekWorker(user_text=None, 
                                              conversation_step=self.interaction_step, 
                                              questions_for_this_round=self.questions_to_ask_this_session,
                                              hat_tone=selected_primary_char, 
                                              settings=self.settings)
        self.deepseek_worker.status_signal.connect(self._update_status_bar)
        self.deepseek_worker.finished_signal.connect(self.on_deepseek_response_received)
        self.deepseek_worker.error_signal.connect(self._on_deepseek_error)
        self.deepseek_worker.start()

    def start_recording_router(self):
        if self._is_shutting_down: return
        print(f"DEBUG: start_recording_router clicked. Current App Interaction Step: {self.interaction_step}")

        if self.interaction_step == 0 and self.current_oracle_state == "idle":
            self._reset_interaction_flow_and_ui("Preparing for your input...")
        else:
            self._stop_all_active_workers() 
            self.your_text_output.clear()
            self._update_status_bar(f"Listening for your answer (currently at step {self.interaction_step})...")
        
        self._start_audio_recording_common()


    def _start_audio_recording_common(self):
        if self._is_shutting_down: return
        self.activate_hat_button.setEnabled(True) 
        self.record_button.setEnabled(False)    
        self.stop_button.setEnabled(True)       

        if self.animation_handler and self.current_oracle_state == "thinking":
            pass

        self._update_status_bar(f"Listening (for Q{self.interaction_step + 1} or initial input)... Press 'Stop Recording' (2) when done.")
        if self.recorder_worker and self.recorder_worker.isRunning(): 
             print("CRITICAL WARNING: Old recorder worker still running in _start_audio_recording_common!"); return

        self.recorder_worker = AudioRecorderWorker()
        self.recorder_worker.status_signal.connect(self._update_status_bar)
        self.recorder_worker.finished_signal.connect(self.on_recording_session_finished)
        self.recorder_worker.error_signal.connect(self._on_recording_error) 
        self.recorder_worker.start()

    def stop_audio_recording(self): 
        if self._is_shutting_down: return
        if not self.stop_button.isEnabled(): print("DEBUG: stop_audio_recording called but stop_button not enabled."); return
        
        print("DEBUG: stop_audio_recording - User requested stop.")
        if self.recorder_worker and self.recorder_worker.isRunning(): 
            self.recorder_worker.stop_recording() 
        
        self.stop_button.setEnabled(False) 
        self.record_button.setEnabled(True) 
        self.activate_hat_button.setEnabled(True)
        self._update_status_bar("Recording stopped, processing audio...")

    def on_recording_session_finished(self, audio_filepath): 
        if self._is_shutting_down: return 
        print(f"DEBUG: on_recording_session_finished. audio_filepath: {audio_filepath}, App Interaction Step: {self.interaction_step}")
        
        self.activate_hat_button.setEnabled(True)
        self.record_button.setEnabled(True)
        self.stop_button.setEnabled(False)

        self._prepare_for_oracle_thinking("Processing your words...")

        if not audio_filepath or not os.path.exists(audio_filepath) or os.path.getsize(audio_filepath) < 1024:
            self._handle_ui_error("No audio captured or recording was too short.") 
            return
        
        self._update_status_bar("Transcribing audio to text...")
        
        stt_lang_mode = self.settings_manager.get_setting("stt_input_language_mode", 1) 
        try:
            stt_lang_mode = int(stt_lang_mode) 
            if stt_lang_mode not in [1, 2, 3]:
                print(f"WARNING: Invalid stt_input_language_mode '{stt_lang_mode}' in settings. Defaulting to 1 (English).")
                stt_lang_mode = 1
        except (ValueError, TypeError):
            print(f"WARNING: stt_input_language_mode '{stt_lang_mode}' is not a valid integer/type. Defaulting to 1 (English).")
            stt_lang_mode = 1

        self.stt_worker = SpeechToTextWorker(audio_filepath, stt_input_language_mode=stt_lang_mode)
        self.stt_worker.status_signal.connect(self._update_status_bar)
        self.stt_worker.finished_signal.connect(self.on_stt_conversion_finished)
        self.stt_worker.error_signal.connect(self._on_stt_error)
        self.stt_worker.start()

    def on_stt_conversion_finished(self, transcribed_text): 
        if self._is_shutting_down: return 
        print(f"DEBUG: on_stt_conversion_finished. App Interaction Step before DeepSeek: {self.interaction_step}")
        
        if not transcribed_text.strip():
            self._handle_ui_error("Could not understand what you said.")
            self._update_status_bar(f"Please try answering question {self.interaction_step +1} again.") 
            if self.animation_handler: self.animation_handler.set_thinking_animation(loop=True)
            return 

        self.your_text_output.setPlainText(transcribed_text)
        self._update_status_bar("Transcription complete. Consulting the Oracle...")
        
        if not DEEPSEEK_API_KEY or DEEPSEEK_API_KEY == "YOUR_DEEPSEEK_API_KEY":
            self._handle_ui_error("DeepSeek API Key is not configured.")
            return

        selected_primary_char = self.primary_characteristic_combo.currentData() or "friendly"
        current_deepseek_step = self.interaction_step
        
        print(f"DEBUG: Calling DeepSeekWorker with its conversation_step: {current_deepseek_step}")
        self.deepseek_worker = DeepSeekWorker(user_text=transcribed_text, 
                                              conversation_step=current_deepseek_step, 
                                              questions_for_this_round=self.questions_to_ask_this_session,
                                              hat_tone=selected_primary_char, 
                                              settings=self.settings)
        self.deepseek_worker.status_signal.connect(self._update_status_bar)
        self.deepseek_worker.finished_signal.connect(self.on_deepseek_response_received)
        self.deepseek_worker.error_signal.connect(self._on_deepseek_error)
        self.deepseek_worker.start()

    def on_deepseek_response_received(self, oracle_response_text): 
        if self._is_shutting_down: return 
        print(f"DEBUG: on_deepseek_response_received. App Step: {self.interaction_step}, Total Q's this session: {self.questions_to_ask_this_session}")
        self.oracle_response_text.setPlainText(oracle_response_text)
        self.current_oracle_state = "speaking" 

        if self.interaction_step < self.questions_to_ask_this_session:
            self.interaction_step += 1 
            self._update_status_bar(f"Oracle asks question {self.interaction_step}. Preparing to speak...")
            print(f"DEBUG: Hat asked Q{self.interaction_step}. App Interaction Step advanced to: {self.interaction_step}")
        else:
            self.interaction_step = FINAL_SORTING_STEP_COMPLETE 
            self._update_status_bar("Oracle has made its decision. Preparing to speak...")
            print(f"DEBUG: Hat has sorted. App Interaction Step set to: {self.interaction_step}")
        
        if self.animation_handler: 
            self.animation_handler.set_speaking_animation_active()
        
        self.tts_worker = TextToSpeechWorker(oracle_response_text, self.settings_manager.get_setting("tts_settings", {}))
        self.tts_worker.status_signal.connect(self._update_status_bar)
        self.tts_worker.finished_signal.connect(self.on_tts_playback_finished)
        self.tts_worker.error_signal.connect(self._on_tts_error)
        self.tts_worker.start()

    def on_tts_playback_finished(self): 
        if self._is_shutting_down: return
        print(f"DEBUG: on_tts_playback_finished. App Interaction Step: {self.interaction_step}")
        self._update_status_bar("Oracle has spoken.")
        self.current_oracle_state = "thinking" 

        if self.animation_handler:
            self.animation_handler.tts_audio_has_finished() 
        
        if self.interaction_step == FINAL_SORTING_STEP_COMPLETE: 
            print("DEBUG: TTS finished after final response/sorting. Triggering full reset.")
            self._just_sorted_flag = True 
            self._reset_interaction_flow_and_ui("Sorting complete. Waiting for the next student...")
        else:
            print(f"DEBUG: TTS finished after Hat asked Q{self.interaction_step}. Waiting for user answer.")
            self._update_status_bar(f"Please answer the Oracle's question (Q{self.interaction_step}).")
            if self.animation_handler:
                 self.animation_handler.set_thinking_animation(loop=True)
            else:
                self.on_animation_cycle_completed() 
            self.record_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            self.activate_hat_button.setEnabled(True)


    def keyPressEvent(self, event): 
        if self._is_shutting_down: super().keyPressEvent(event); return
        key_text = event.text() 
        
        if key_text == '1' and self.record_button.isEnabled(): 
            print("DEBUG: '1' key -> Start Recording Router (Interrupts if needed)")
            self.start_recording_router()
        elif key_text == '2' and self.stop_button.isEnabled(): 
            print("DEBUG: '2' key action: Stop Recording")
            self.stop_audio_recording()
        elif key_text == '3' and self.activate_hat_button.isEnabled():
            print("DEBUG: '3' key action: Activate Oracle (Interrupts if needed)")
            self.activate_oracle_interaction()
        else: super().keyPressEvent(event)

    @Slot(str)
    def _handle_ui_error(self, message): 
        if self._is_shutting_down: return
        QMessageBox.warning(self, "Application Error", message)
        self._reset_interaction_flow_and_ui(f"Error: {message.split('.')[0]}. Resetting.")

    # --- Music Control Slots ---
    @Slot(str)
    def _on_music_player_error(self, error_message): 
        print(f"ERROR: Background Music: {error_message}"); self._update_status_bar(f"Music Error: {error_message.split('.')[0]}")
        self.mute_button.setEnabled(False); self.volume_slider.setEnabled(False)
    @Slot()
    def _toggle_music_mute(self): 
        if self._is_shutting_down: return
        if self.music_player: self.music_player.toggle_mute()
        
    @Slot(bool)
    def _update_mute_button_icon(self, muted: bool): 
        if self._is_shutting_down: return
        # --- FIX 2: Removed icon logic, forcing text-based update ---
        self.mute_button.setText("Unmute" if muted else "Mute")
        self.mute_button.setIcon(QIcon()) # Clear any potential stale icon
        # --- End of FIX 2 ---
        
    @Slot(int)
    def _change_music_volume(self, value: int): 
        if self._is_shutting_down: return
        if self.music_player:
            normalized_slider_value = value / 100.0  
            power_exponent = 2.5 
            actual_volume_to_set = 0.0
            if normalized_slider_value > 0: 
                actual_volume_to_set = normalized_slider_value ** power_exponent
            actual_volume_to_set = max(0.0, min(1.0, actual_volume_to_set))
            self.music_player.set_volume(actual_volume_to_set)

    # --- Worker Error Slots ---
    def _on_recording_error(self, error_message): self._handle_ui_error(f"Recording Problem: {error_message}")
    def _on_stt_error(self, error_message): self._handle_ui_error(f"Speech-to-Text Problem: {error_message}")
    def _on_deepseek_error(self, error_message): self._handle_ui_error(f"DeepSeek API Problem: {error_message}")
    def _on_tts_error(self, error_message): self._handle_ui_error(f"Text-to-Speech Problem: {error_message}")
        
    def _safe_stop_worker(self, worker, worker_name, timeout_ms=1500): 
        if worker and worker.isRunning():
            print(f"INFO: Attempting to stop worker: {worker_name}")
            if isinstance(worker, AudioRecorderWorker): worker.stop_recording()
            elif isinstance(worker, TextToSpeechWorker): worker.stop_tts_signal()
            
            try: worker.finished_signal.disconnect()
            except (TypeError, RuntimeError): pass 
            try: worker.error_signal.disconnect()
            except (TypeError, RuntimeError): pass
            try: worker.status_signal.disconnect()
            except (TypeError, RuntimeError): pass

            worker.quit() 
            if not worker.wait(timeout_ms): 
                print(f"WARNING: Worker {worker_name} did not finish in {timeout_ms}ms. Terminating.")
                worker.terminate()
                if not worker.wait(500): print(f"ERROR: Worker {worker_name} did not terminate after explicit call.")
            else: print(f"INFO: Worker {worker_name} finished gracefully.")
        elif worker: print(f"INFO: Worker {worker_name} already finished or not running (checked by _safe_stop_worker).")

    def closeEvent(self, event):
        if self._is_shutting_down: super().closeEvent(event); return
        print("INFO: Initiating application shutdown...")
        self._is_shutting_down = True; self._update_status_bar("Shutting down application...")
        if hasattr(self, 'music_player') and self.music_player: print("INFO: Stopping background music player."); self.music_player.stop()
        
        if self.animation_handler:
            self.animation_handler.stop_all_animation_activity()
            signals_to_disconnect = [
                (self.animation_handler.animation_status_signal, self._update_status_bar),
                (self.animation_handler.animation_cycle_complete_signal, self.on_animation_cycle_completed),
                (self.animation_handler.animation_error_signal, self._handle_ui_error)
            ]
            for sig, slot_func in signals_to_disconnect:
                try: sig.disconnect(slot_func)
                except (TypeError, RuntimeError): pass
        
        self._safe_stop_worker(self.tts_worker, "TextToSpeech", timeout_ms=3500); self.tts_worker = None 
        self._safe_stop_worker(self.recorder_worker, "AudioRecorder", timeout_ms=3500); self.recorder_worker = None
        self._safe_stop_worker(self.stt_worker, "SpeechToText", timeout_ms=3500); self.stt_worker = None
        self._safe_stop_worker(self.deepseek_worker, "DeepSeek", timeout_ms=3500); self.deepseek_worker = None
        
        print("INFO: All active workers processed for shutdown."); QApplication.instance().processEvents(); super().closeEvent(event)

if __name__ == "__main__":
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        if os.getcwd() != script_dir:
            os.chdir(script_dir)
        print(f"INFO: CWD: {os.getcwd()}")
    except Exception as e:
        print(f"ERROR: CWD change: {e}")
    app = QApplication(sys.argv)
    main_window = SortingHatApp()
    main_window.showMaximized()
    QTimer.singleShot(250, main_window.complete_initial_setup)
    sys.exit(app.exec())