# animation_handler.py
import os
from PySide6.QtCore import QObject, Signal, Slot, QTimer, QRect, QSize, Qt
from PySide6.QtGui import QMovie, QPixmap
from PySide6.QtWidgets import QLabel

class AnimationHandler(QObject):
    animation_error_signal = Signal(str)
    animation_status_signal = Signal(str)
    animation_cycle_complete_signal = Signal()

    def __init__(self, display_label: QLabel, speaking_gif_filename: str, thinking_gif_filename: str, parent=None):
        super().__init__(parent)
        self.display_label = display_label
        self.display_label.setScaledContents(False) 

        self.speaking_gif_filename_only = speaking_gif_filename
        self.thinking_gif_filename_only = thinking_gif_filename
        
        self.speaking_movie: QMovie | None = None 
        self.thinking_movie: QMovie | None = None 
        self.active_movie: QMovie | None = None
        
        self.speaking_gif_load_successful = False
        self.thinking_gif_load_successful = False

        # Scale factors for each GIF type
        self.thinking_gif_scale_factor = 0.5  # 2x smaller for hat_think.gif
        self.speaking_gif_scale_factor = 1.2  # 1.0 = no scaling for hat.gif (adjust if needed)

        self._load_movie_data()

    def _load_single_movie(self, gif_filename: str) -> tuple[QMovie | None, bool]:
        # ... (loading logic remains the same as your previous version with this file) ...
        print(f"ANIMATION_HANDLER: Loading GIF: {gif_filename}")
        if not os.path.exists(gif_filename):
            err_msg = f"GIF file '{gif_filename}' not found."
            print(f"WARNING: {err_msg}")
            self.animation_status_signal.emit(err_msg)
            return None, False

        movie = QMovie(gif_filename) 
        if not movie.isValid():
            err_msg = f"GIF file '{gif_filename}' is invalid. QMovie error: {movie.lastErrorString()}"
            print(f"WARNING: {err_msg}")
            self.animation_status_signal.emit(err_msg)
            return None, False 

        movie.setCacheMode(QMovie.CacheAll)
        print(f"INFO: GIF QMovie object created for: {gif_filename}")
        
        original_size_from_pixmap = QSize(0,0)
        if movie.jumpToFrame(0):
            pixmap = movie.currentPixmap()
            if not pixmap.isNull():
                original_size_from_pixmap = pixmap.size()
        
        original_frame_rect = movie.frameRect()
        original_size_from_rect = original_frame_rect.size()
        
        if (original_size_from_rect.width() == 0 or original_size_from_rect.height() == 0) and \
           (original_size_from_pixmap.width() == 0 or original_size_from_pixmap.height() == 0):
            print(f"ERROR: Cannot determine original size for {gif_filename}. Both frameRect and pixmap are 0x0.")
            return movie, False
        elif (original_size_from_rect.width() == 0 or original_size_from_rect.height() == 0):
            print(f"INFO: Using pixmap size for {gif_filename}: {original_size_from_pixmap.width()}x{original_size_from_pixmap.height()}")
        return movie, True

    def _load_movie_data(self):
        # ... (loading logic remains the same) ...
        print("ANIMATION_HANDLER: _load_movie_data called.")
        self.speaking_movie, self.speaking_gif_load_successful = self._load_single_movie(self.speaking_gif_filename_only)
        self.thinking_movie, self.thinking_gif_load_successful = self._load_single_movie(self.thinking_gif_filename_only)

        if self.speaking_movie:
            self.speaking_movie.updated.connect(self._on_movie_updated)
        if self.thinking_movie:
            self.thinking_movie.updated.connect(self._on_movie_updated)

        # ... (error reporting remains the same) ...
        if not self.speaking_gif_load_successful and not self.thinking_gif_load_successful:
            err_msg = "Failed to load both speaking and thinking GIFs. Animations disabled."
            print(f"ERROR: {err_msg}")
            self.animation_status_signal.emit(err_msg)
            self.animation_error_signal.emit(err_msg)
        elif not self.speaking_gif_load_successful:
            self.animation_status_signal.emit(f"Warning: Speaking GIF '{self.speaking_gif_filename_only}' failed to load.")
        elif not self.thinking_gif_load_successful:
             self.animation_status_signal.emit(f"Warning: Thinking GIF '{self.thinking_gif_filename_only}' failed to load.")


    @Slot(QRect)
    def _on_movie_updated(self, rect: QRect):
        if self.active_movie and self.active_movie.isValid():
            pixmap = self.active_movie.currentPixmap()
            if not pixmap.isNull():
                current_scale_factor = 1.0 # Default to no scaling

                # Determine which scale factor to use
                if self.active_movie == self.thinking_movie:
                    current_scale_factor = self.thinking_gif_scale_factor
                elif self.active_movie == self.speaking_movie:
                    current_scale_factor = self.speaking_gif_scale_factor
                
                original_w = pixmap.width()
                original_h = pixmap.height()
                
                if original_w == 0 or original_h == 0:
                    if self.active_movie.jumpToFrame(0):
                        base_pixmap = self.active_movie.currentPixmap()
                        if not base_pixmap.isNull():
                            original_w = base_pixmap.width()
                            original_h = base_pixmap.height()

                if original_w > 0 and original_h > 0:
                    scaled_w = int(original_w * current_scale_factor)
                    scaled_h = int(original_h * current_scale_factor)
                    
                    # Ensure scaled dimensions are at least 1x1 to avoid errors with QPixmap.scaled
                    scaled_w = max(1, scaled_w)
                    scaled_h = max(1, scaled_h)

                    scaled_pixmap = pixmap.scaled(scaled_w, scaled_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    self.display_label.setPixmap(scaled_pixmap)
                else:
                    self.display_label.setPixmap(pixmap) 
            # else:
            #    print("DEBUG: _on_movie_updated - currentPixmap isNull")
        # else:
        #    print("DEBUG: _on_movie_updated - No active_movie or it's invalid")

    def _set_active_movie(self, movie: QMovie | None):
        # ... (remains the same as previous version) ...
        if self.active_movie and self.active_movie != movie and self.active_movie.state() == QMovie.Running:
            self.active_movie.stop()
        
        self.active_movie = movie
        
        if not self.active_movie:
            self.display_label.clear()
            return

        if self.active_movie.jumpToFrame(0):
            self._on_movie_updated(self.active_movie.frameRect()) 
        else:
            self.display_label.clear() 


    def is_ready_to_display(self, movie_type: str = "speaking") -> bool:
        # ... (remains the same) ...
        if movie_type == "speaking":
            return self.speaking_gif_load_successful and self.speaking_movie is not None
        elif movie_type == "thinking":
            return self.thinking_gif_load_successful and self.thinking_movie is not None
        return False

    def setup_initial_display(self): 
        # ... (remains the same) ...
        print("ANIMATION_HANDLER: setup_initial_display (thinking GIF) called.")
        if self.is_ready_to_display("thinking"):
            self.set_thinking_animation(loop=True) 
        elif self.is_ready_to_display("speaking"): 
            print("WARNING: Thinking GIF not available, falling back to speaking GIF for initial display.")
            self.set_speaking_animation_frozen()
        else:
            err_msg = "Cannot setup initial display, no valid GIFs loaded."
            self._emit_error_and_complete(err_msg)
            
    def set_speaking_animation_active(self): 
        # ... (remains the same, property assignment for loopCount) ...
        if not self.is_ready_to_display("speaking") or not self.speaking_movie:
            self._emit_error_and_complete(f"Speaking GIF '{self.speaking_gif_filename_only}' not ready.")
            return

        print("ANIMATION_HANDLER: Setting SPEAKING animation active.")
        self.animation_status_signal.emit("Animation: Speaking...")
        self._set_active_movie(self.speaking_movie) 
        
        self.speaking_movie.setSpeed(100)
        try:
            self.speaking_movie.loopCount = 1 
        except AttributeError:
            print(f"ERROR: speaking_movie.loopCount property assignment failed. Trying setLoopCount.")
            self.speaking_movie.setLoopCount(1)

        if self.speaking_movie.state() != QMovie.Running:
            self.speaking_movie.start()

    def set_speaking_animation_frozen(self): 
        # ... (remains the same) ...
        if not self.is_ready_to_display("speaking") or not self.speaking_movie:
            self._emit_error_and_complete(f"Speaking GIF '{self.speaking_gif_filename_only}' not ready for freeze.")
            return
            
        print("ANIMATION_HANDLER: Setting SPEAKING animation to frozen (frame 0).")
        self.animation_status_signal.emit("Animation: Speaking GIF frozen.")
        self._set_active_movie(self.speaking_movie)

        if self.speaking_movie.state() == QMovie.Running:
            self.speaking_movie.stop()
        self._emit_completion()

    def set_thinking_animation(self, loop: bool = True):
        # ... (remains the same, property assignment for loopCount) ...
        if not self.is_ready_to_display("thinking") or not self.thinking_movie:
            if self.is_ready_to_display("speaking"):
                print("WARNING: Thinking GIF not available, falling back to frozen speaking GIF.")
                self.set_speaking_animation_frozen() 
            else:
                self._emit_error_and_complete(f"Neither Thinking nor Speaking GIF is ready.")
            return
            
        print(f"ANIMATION_HANDLER: Setting THINKING animation (Loop: {loop}).")
        self.animation_status_signal.emit("Animation: Thinking...")
        self._set_active_movie(self.thinking_movie)
        
        self.thinking_movie.setSpeed(100)
        loop_val = -1 if loop else 1
        try:
            self.thinking_movie.loopCount = loop_val
        except AttributeError as e:
            print(f"ERROR: thinking_movie.loopCount property assignment failed: {e}. Trying setLoopCount.")
            self.thinking_movie.setLoopCount(loop_val) 

        if loop: 
            if self.thinking_movie.state() != QMovie.Running:
                self.thinking_movie.start()
        else: 
             if self.thinking_movie.state() == QMovie.Running:
                 self.thinking_movie.stop()
        self._emit_completion()

    def tts_audio_has_finished(self):
        # ... (remains the same) ...
        print("ANIMATION_HANDLER: TTS audio finished. Stopping speaking GIF.")
        if self.is_ready_to_display("speaking") and self.speaking_movie:
            if self.speaking_movie.state() == QMovie.Running:
                self.speaking_movie.stop()

    def _emit_error_and_complete(self, err_msg):
        # ... (remains the same) ...
        print(f"ERROR: {err_msg}")
        self.animation_status_signal.emit(err_msg)
        self.animation_error_signal.emit(err_msg)
        self._emit_completion()

    def _emit_completion(self):
        # ... (remains the same) ...
        print("ANIMATION_HANDLER: Emitting animation_cycle_complete_signal.")
        if not self.signalsBlocked(): self.animation_cycle_complete_signal.emit()

    def stop_all_animation_activity(self):
        # ... (remains the same) ...
        print("ANIMATION_HANDLER: Stopping all animation activity.")
        if self.speaking_movie and self.speaking_movie.state() == QMovie.Running:
            self.speaking_movie.stop()
        if self.thinking_movie and self.thinking_movie.state() == QMovie.Running:
            self.thinking_movie.stop()
        self.active_movie = None 
        self.display_label.clear()