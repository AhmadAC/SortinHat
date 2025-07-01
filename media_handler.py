# media_handler.py
import os
import time # For small delays if needed, use cautiously
import inspect # For debugging play calls
from PySide6.QtCore import QObject, Signal, QUrl, Slot, Qt
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget

class MediaPlayerHandler(QObject):
    video_error_signal = Signal(str)
    video_status_signal = Signal(str)
    video_cycle_complete_signal = Signal() # Emitted when video is frozen and UI can be reset

    def __init__(self, video_widget: QVideoWidget, video_filename: str, parent=None):
        super().__init__(parent)
        self.video_widget = video_widget
        self.video_filename_only = video_filename
        self.video_path = None

        self.media_player = QMediaPlayer()
        self.media_player.setVideoOutput(self.video_widget)
        self._audio_output_for_video = QAudioOutput() # Required even if muted
        self.media_player.setAudioOutput(self._audio_output_for_video)
        self._audio_output_for_video.setMuted(True)

        self.is_video_reversing = False
        self.reverse_after_play_completes = False # Flag for post-TTS reverse
        self.is_initializing_first_frame = True  # Flag for initial freeze sequence
        self.video_load_successful = False
        self._expect_tts_related_play = False # Flag to know if a play is for TTS

        self._setup_video_path()
        self._connect_signals()
        
        if self.video_load_successful:
            self.set_to_frozen_state() # Start initial freeze
        else:
            # If video load failed, _setup_video_path should have emitted video_cycle_complete_signal
            # This is a safeguard if it's called before signals are connected somehow (though unlikely with current structure)
            if not self.signalsBlocked():
                 self.video_cycle_complete_signal.emit()

    def _debug_play(self, context_message=""):
        caller_frame = inspect.currentframe().f_back
        caller_function = caller_frame.f_code.co_name
        caller_lineno = caller_frame.f_lineno
        
        print(f"MEDIA_PLAYER_DEBUG: play() INVOKED by {caller_function} at line {caller_lineno} [{context_message}]. "
              f"State: {self.media_player.playbackState()}, MediaStatus: {self.media_player.mediaStatus()}, "
              f"InitFrame: {self.is_initializing_first_frame}, ReversePending: {self.reverse_after_play_completes}, "
              f"Reversing: {self.is_video_reversing}, ExpectTTS: {self._expect_tts_related_play}, "
              f"Position: {self.media_player.position()}, Loops: {self.media_player.loops()}, Duration: {self.media_player.duration()}")
        self.media_player.play()

    def _setup_video_path(self):
        if os.path.exists(self.video_filename_only):
            self.video_path = os.path.abspath(self.video_filename_only)
            self.media_player.setSource(QUrl.fromLocalFile(self.video_path))
            self.video_load_successful = True
            self.video_status_signal.emit(f"Video '{self.video_filename_only}' loaded.")
            print(f"INFO: Video file found: {self.video_path}")
        else:
            self.video_load_successful = False
            err_msg = f"Video file '{self.video_filename_only}' not found. Video playback disabled."
            self.video_status_signal.emit(err_msg) # For app status bar
            self.video_error_signal.emit(err_msg)  # For potential error dialog
            print(f"WARNING: {err_msg}")
            # If video load fails, UI should still become ready
            if not self.signalsBlocked(): # Ensure signal connection exists
                self.video_cycle_complete_signal.emit()


    def _connect_signals(self):
        self.media_player.errorOccurred.connect(self.on_media_error)
        self.media_player.positionChanged.connect(self.on_media_position_changed)
        self.media_player.mediaStatusChanged.connect(self.on_media_status_changed)
        self.media_player.playbackStateChanged.connect(self.on_playback_state_changed)

    def is_ready(self): # If video file was loaded successfully
        return self.video_load_successful

    def set_to_frozen_state(self):
        if not self.video_load_successful:
            if not self.signalsBlocked(): self.video_cycle_complete_signal.emit()
            return

        print(f"VIDEO_HANDLER: Setting to FROZEN state (frame 0, paused). Loops: {self.media_player.loops()}")
        self.video_status_signal.emit("Video: Setting to frozen state...")
        self.media_player.setLoops(1) # No looping for normal play
        self.media_player.setPlaybackRate(1.0) # Ensure normal rate
        self._expect_tts_related_play = False # Not expecting TTS play during freeze sequence

        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.stop() 
        
        self.media_player.setPosition(0)
        
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.StoppedState or \
           (self.media_player.playbackState() == QMediaPlayer.PlaybackState.PausedState and self.media_player.position() != 0):
            print("VIDEO_HANDLER: Player stopped or paused not at 0. Initiating play()->pause() for freeze.")
            self.is_initializing_first_frame = True 
            self._debug_play("set_to_frozen_state - for initial frame render")
        elif self.media_player.playbackState() == QMediaPlayer.PlaybackState.PausedState and self.media_player.position() == 0:
            print("VIDEO_HANDLER: Already paused at frame 0.")
            self.is_initializing_first_frame = False 
            self.is_video_reversing = False
            self.reverse_after_play_completes = False
            if not self.signalsBlocked(): self.video_cycle_complete_signal.emit()
        else: 
            print(f"VIDEO_HANDLER: Unexpected state for freezing: {self.media_player.playbackState()}, Pos: {self.media_player.position()}. Attempting play/pause.")
            self.is_initializing_first_frame = True
            self._debug_play("set_to_frozen_state - unexpected state, attempting freeze")

    @Slot(QMediaPlayer.PlaybackState)
    def on_playback_state_changed(self, state: QMediaPlayer.PlaybackState):
        print(f"VIDEO_HANDLER (StateChange): Now {state}. InitFrame: {self.is_initializing_first_frame}, "
              f"Reversing: {self.is_video_reversing}, ReversePending: {self.reverse_after_play_completes}, ExpectTTS: {self._expect_tts_related_play}, "
              f"Pos: {self.media_player.position()}, Dur: {self.media_player.duration()}, Loops: {self.media_player.loops()}")

        if self.is_initializing_first_frame and state == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause() 
            print("VIDEO_HANDLER: Initialized and paused at first frame via on_playback_state_changed.")
            self.is_initializing_first_frame = False
            self.is_video_reversing = False
            self.reverse_after_play_completes = False
            self._expect_tts_related_play = False # Ensure reset
            if not self.signalsBlocked(): self.video_cycle_complete_signal.emit() 

        elif self.is_video_reversing and state == QMediaPlayer.PlaybackState.PausedState:
            print("VIDEO_HANDLER: Paused during reverse sequence.")
            # ... (rest of existing logic)
            self.is_video_reversing = False
            if self.reverse_after_play_completes: self.reverse_after_play_completes = False
            self.set_to_frozen_state() 

        elif state == QMediaPlayer.PlaybackState.StoppedState:
            if self.is_video_reversing: 
                print("VIDEO_HANDLER: Stopped during reverse. Freezing.")
                self.is_video_reversing = False
                if self.reverse_after_play_completes: self.reverse_after_play_completes = False
                self.set_to_frozen_state()
            elif self.is_initializing_first_frame and self.media_player.mediaStatus() >= QMediaPlayer.MediaStatus.LoadedMedia:
                print("VIDEO_HANDLER: Went to StoppedState during init. Re-attempting play() for freeze.")
                self._debug_play("on_playback_state_changed - Went to StoppedState during init")
            # else:
                # print(f"VIDEO_HANDLER: StoppedState reached. Not init, not reversing. Pos: {self.media_player.position()}")
                # If it stopped on its own after an unwanted play, set_to_frozen_state might be needed if not at 0.
                # if self.media_player.position() != 0 and not self._expect_tts_related_play: # Avoid race if TTS just finished
                #    print("VIDEO_HANDLER: Stopped not at 0 and not expected (e.g. post-TTS). Attempting freeze.")
                #    self.set_to_frozen_state()


        # Defensive check for unexpected play
        elif not self.is_initializing_first_frame and \
             not self.is_video_reversing and \
             not self.reverse_after_play_completes and \
             not self._expect_tts_related_play and \
             state == QMediaPlayer.PlaybackState.PlayingState:
            print(f"VIDEO_HANDLER_DEFENSE: Unexpected transition to PlayingState when not expected. Forcing pause. Pos: {self.media_player.position()}")
            self.media_player.pause()
            if self.media_player.position() < 100: # If near the start, it's likely an unwanted loop
                # This pause should trigger PausedState again. If it then re-triggers PlayingState, there's a deeper issue.
                # Consider if set_to_frozen_state is needed here, but be wary of loops.
                # For now, just pausing. The problem might be that loops isn't truly 1.
                print("VIDEO_HANDLER_DEFENSE: Paused an unexpected play near start of video.")


    def play_for_tts(self):
        if not self.video_load_successful: return
        print(f"VIDEO_HANDLER: Playing for TTS (forward once). Loops: {self.media_player.loops()}")
        self.video_status_signal.emit("Video: Playing forward...")
        self.is_initializing_first_frame = False
        self.reverse_after_play_completes = False 
        self.is_video_reversing = False
        self._expect_tts_related_play = True # This play is expected for TTS
        self.media_player.setLoops(1)
        self.media_player.setPlaybackRate(1.0)
        self.media_player.setPosition(0)
        self._debug_play("play_for_tts")

    def tts_audio_has_finished(self):
        if not self.video_load_successful:
            if not self.signalsBlocked(): self.video_cycle_complete_signal.emit()
            return
        
        print("VIDEO_HANDLER: TTS audio finished. Preparing for video reverse or freeze.")
        self._expect_tts_related_play = False # TTS-related play is now ending/transitioning
        self.reverse_after_play_completes = True 

        # ... (rest of existing logic)
        current_status = self.media_player.mediaStatus()
        current_state = self.media_player.playbackState()
        duration = self.media_player.duration()
        position = self.media_player.position()

        # Margin for end check, using a small percentage of duration or fixed ms
        end_margin = min(100, int(duration * 0.05)) if duration > 0 else 100

        if current_status == QMediaPlayer.MediaStatus.EndOfMedia or \
           (current_state != QMediaPlayer.PlaybackState.PlayingState and duration > 0 and position >= duration - end_margin):
            print("VIDEO_HANDLER: TTS done, video already at/near end. Triggering reverse logic.")
            self.on_media_status_changed(QMediaPlayer.MediaStatus.EndOfMedia) 
        elif current_state == QMediaPlayer.PlaybackState.PlayingState:
            print("VIDEO_HANDLER: TTS done, video still playing. Reverse will trigger on natural EndOfMedia.")
        else: 
            print("VIDEO_HANDLER: TTS done, video not at end and not playing. Freezing directly.")
            self.reverse_after_play_completes = False 
            self.set_to_frozen_state()


    @Slot(int) 
    def on_media_position_changed(self, position: int):
        # print(f"DEBUG Media Pos: {position}, Rate: {self.media_player.playbackRate()}") # Verbose
        if self.is_video_reversing and self.media_player.playbackRate() < 0:
            if position <= 50: 
                print(f"VIDEO_HANDLER: Reached beginning (pos: {position}) while reversing. Pausing.")
                self.media_player.pause() 

    @Slot(QMediaPlayer.MediaStatus)
    def on_media_status_changed(self, status: QMediaPlayer.MediaStatus):
        print(f"VIDEO_HANDLER (MediaStatusChange): Now {status}. InitFrame: {self.is_initializing_first_frame}, "
              f"ReversePending: {self.reverse_after_play_completes}, Reversing: {self.is_video_reversing}, ExpectTTS: {self._expect_tts_related_play}, "
              f"Pos: {self.media_player.position()}, Dur: {self.media_player.duration()}, Loops: {self.media_player.loops()}")

        if status == QMediaPlayer.MediaStatus.LoadedMedia and self.is_initializing_first_frame:
            if self.media_player.playbackState() == QMediaPlayer.PlaybackState.StoppedState:
                print("VIDEO_HANDLER: Media loaded, attempting to freeze via play/pause.")
                self.media_player.setPosition(0)
                self._debug_play("on_media_status_changed - Media loaded, freeze via play/pause")

        elif status == QMediaPlayer.MediaStatus.EndOfMedia:
            print("VIDEO_HANDLER: EndOfMedia reached.")
            if self.reverse_after_play_completes and not self.is_video_reversing:
                print("VIDEO_HANDLER: EndOfMedia after TTS forward play. Attempting reverse.")
                self.media_player.pause() 
                time.sleep(0.05) 
                
                self.media_player.setPlaybackRate(-1.0)
                if abs(self.media_player.playbackRate() - (-1.0)) < 0.1:
                    print("VIDEO_HANDLER: Playback rate set to -1.0. Playing in reverse.")
                    self.is_video_reversing = True
                    self._debug_play("on_media_status_changed - EndOfMedia after TTS, playing in reverse") 
                else:
                    print("VIDEO_HANDLER: Playback rate -1.0 not supported. Skipping reverse.")
                    self.video_status_signal.emit("Video: Reverse not supported, freezing.")
                    self.is_video_reversing = False
                    self.reverse_after_play_completes = False
                    self.set_to_frozen_state()
            elif self.is_video_reversing:
                print("VIDEO_HANDLER: EndOfMedia reached while reversing (likely hit start). Pausing.")
                self.media_player.pause() 
            else: # EndOfMedia not related to TTS reverse or during reversing. Could be an unexpected play-through.
                print("VIDEO_HANDLER: EndOfMedia reached, not in expected reverse context.")
                # If it was playing due to an unwanted loop, it should now be stopped or paused here by the player.
                # Ensure it's frozen if it's not already.
                if self.media_player.playbackState() != QMediaPlayer.PlaybackState.PausedState or self.media_player.position() != 0:
                    print("VIDEO_HANDLER: EndOfMedia, but not paused at 0. Refreezing.")
                    self.set_to_frozen_state()


        elif (status == QMediaPlayer.MediaStatus.BufferingMedia or status == QMediaPlayer.MediaStatus.BufferedMedia) and \
             self.is_initializing_first_frame and \
             self.media_player.playbackState() == QMediaPlayer.PlaybackState.StoppedState:
            print(f"VIDEO_HANDLER: Media (un)buffered to {status} during init. Trying to play for freeze.")
            self.media_player.setPosition(0)
            self._debug_play("on_media_status_changed - Media (un)buffered during init, play for freeze")


    @Slot(QMediaPlayer.Error, str)
    def on_media_error(self, error_code: QMediaPlayer.Error, error_string: str):
        if error_code != QMediaPlayer.Error.NoError and error_code != QMediaPlayer.Error.ResourceError:
            msg = f"Media Player Error: {error_string} (Code: {error_code})"
            print(f"ERROR: {msg}")
            self.video_error_signal.emit(msg)
        
        self._expect_tts_related_play = False # Reset on error
        if self.is_initializing_first_frame:
            self.is_initializing_first_frame = False 
            if not self.signalsBlocked(): self.video_cycle_complete_signal.emit() 
        
        if self.reverse_after_play_completes or self.is_video_reversing: 
            self.reverse_after_play_completes = False
            self.is_video_reversing = False
            self.set_to_frozen_state() 

    def stop_all_media_activity(self):
        print("VIDEO_HANDLER: Stopping all media player activity.")
        self.is_initializing_first_frame = False
        self.is_video_reversing = False
        self.reverse_after_play_completes = False
        self._expect_tts_related_play = False
        if self.media_player:
            self.media_player.stop()