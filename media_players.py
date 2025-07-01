# media_players.py
import os
from PySide6.QtCore import QObject, QUrl, Slot, Signal, Qt
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

class BackgroundMusicPlayer(QObject):
    error_occurred = Signal(str)
    mute_changed = Signal(bool) # Emits the new mute state

    def __init__(self, music_file_path: str, initial_volume: float = 0, parent=None): # Default volume lower
        super().__init__(parent)
        self.music_file_path = os.path.abspath(music_file_path) # Ensure absolute path
        
        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self) 
        self.player.setAudioOutput(self.audio_output)

        self._is_loaded = False
        self._is_playing = False
        self._initial_volume = max(0.0, min(1.0, initial_volume)) # Clamp initial volume between 0 and 1

        self.player.errorOccurred.connect(self._handle_error)
        self.player.mediaStatusChanged.connect(self._on_media_status_changed)
        self.audio_output.mutedChanged.connect(self.mute_changed) # Forward the signal

        if os.path.exists(self.music_file_path):
            self.load_music(self.music_file_path)
        else:
            err_msg = f"Background music file not found: {self.music_file_path}"
            print(f"ERROR: {err_msg}")
            self.error_occurred.emit(err_msg)


    def load_music(self, music_file_path: str):
        self.music_file_path = os.path.abspath(music_file_path)
        if not self.music_file_path or not os.path.exists(self.music_file_path):
            self.error_occurred.emit(f"Music file not found or path empty: {self.music_file_path}")
            return
            
        source_url = QUrl.fromLocalFile(self.music_file_path)
        if not source_url.isValid():
            err_msg = f"Invalid music file path or URL: {self.music_file_path}"
            print(f"ERROR: {err_msg}")
            self.error_occurred.emit(err_msg)
            return

        self.player.setSource(source_url)
        print(f"INFO: Background music source set to: {self.music_file_path}")

    @Slot(QMediaPlayer.MediaStatus)
    def _on_media_status_changed(self, status):
        print(f"INFO: BackgroundMusicPlayer MediaStatusChanged: {status}")
        if status == QMediaPlayer.MediaStatus.LoadedMedia and not self._is_loaded:
            self._is_loaded = True
            self.audio_output.setVolume(self._initial_volume) 
            self.player.setLoops(QMediaPlayer.Infinite) 
            self.play()
            print(f"INFO: Background music '{os.path.basename(self.music_file_path)}' loaded and playing.")
        elif status == QMediaPlayer.MediaStatus.EndOfMedia:
            # Should not happen with Infinite loops, but good to have
            print("INFO: Background music reached end, restarting due to loop.")
            self.player.setPosition(0)
            self.play()
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            err_msg = f"Invalid media for background music: {self.player.source().toString()}"
            print(f"ERROR: {err_msg}")
            self.error_occurred.emit(err_msg)
        elif status == QMediaPlayer.MediaStatus.NoMedia:
             print("INFO: BackgroundMusicPlayer: No media loaded or cleared.")


    @Slot(QMediaPlayer.Error, str) # Corrected slot signature
    def _handle_error(self, error_code: QMediaPlayer.Error, error_string: str):
        if error_code != QMediaPlayer.Error.NoError:
            err_msg = f"BackgroundMusicPlayer Error: {error_string} (Code: {error_code})"
            print(f"ERROR: {err_msg}")
            self.error_occurred.emit(err_msg)

    def play(self):
        if self._is_loaded:
            self.player.play()
            self._is_playing = True
            print("INFO: Background music playing.")
        else:
            print("WARNING: BackgroundMusicPlayer - Play called but media not loaded.")

    def pause(self):
        if self._is_playing:
            self.player.pause()
            self._is_playing = False
            print("INFO: Background music paused.")

    def stop(self):
        self.player.stop()
        self._is_playing = False
        self._is_loaded = False # Consider if stopping means unloading
        print("INFO: Background music stopped.")

    def set_volume(self, volume: float): # Volume from 0.0 to 1.0
        clamped_volume = max(0.0, min(1.0, volume))
        if self.audio_output:
            self.audio_output.setVolume(clamped_volume)
            print(f"INFO: Background music volume set to {clamped_volume:.2f}")

    def get_volume(self) -> float:
        if self.audio_output:
            return self.audio_output.volume()
        return 0.0

    def toggle_mute(self):
        if self.audio_output:
            new_mute_state = not self.audio_output.isMuted()
            self.audio_output.setMuted(new_mute_state)
            # self.mute_changed.emit(new_mute_state) # audio_output.mutedChanged handles this
            print(f"INFO: Background music mute toggled to: {new_mute_state}")
            return new_mute_state
        return False # Or current mute state if audio_output is None

    def is_muted(self) -> bool:
        if self.audio_output:
            return self.audio_output.isMuted()
        return False