# import chess
# from chessboard.settings import settings
# import threading


# class AnimationFrame:
#     def __init__(self, duration: float, colors: dict[chess.Square, tuple[int, int, int]]) -> None:
#         self.duration = duration
#         self.colors = colors


# class Animation:
#     def __init__(self):
#         self._stop = threading.Event()
#         self._thread = threading.Thread(target=self._animate_thread)
#         self._animation_done_callback = None

#     def next_frame(self) -> AnimationFrame | None:
#         """
#         Returns the next frame of the animation as a list of tuples containing
#         (time the frame should be displayed in seconds, square, color). If the animation is complete, returns None.
#         """
#         raise NotImplementedError()

#     def start(self, animation_done_callback=None):
#         self._animation_done_callback = animation_done_callback
#         self._stop.clear()
#         self._thread.start()

#     def stop(self):
#         self._stop.set()
#         self._thread.join()

#     def _animate_thread(self):
#         while not self._stop.is_set():
#             frame = self.next_frame()
#             if frame is None:
#                 self._animation = None
#                 break

#             with STRIP_LOCK:
#                 for square, color in frame.colors.items():
#                     board_leds.set_color([square], color, commit=False)

#                 board_leds.commit()

#             threading.Event().wait(frame.duration)

#         if self._animation_done_callback:
#             self._animation_done_callback()


# class ChessBoardFrame(AnimationFrame):
#     def __init__(self, board_state: chess.Board, duration) -> None:
#         white_squares = [sq for sq in chess.SQUARES if (chess.square_rank(sq) + chess.square_file(sq)) % 2 == 1]
#         black_squares = [sq for sq in chess.SQUARES if (chess.square_rank(sq) + chess.square_file(sq)) % 2 == 0]

#         colors = {}
#         for sq in chess.SQUARES if (chess.square_rank(sq) + chess.square_file(sq)) % 2 == 1:
#             colors[sq] = settings['leds.colors.white_max']
#         for sq in black_squares:
#             colors[sq] = settings['leds.colors.black']

#         super().__init__(duration=duration, colors=colors)


# class AnimationChangeSide(Animation):
#     def __init__(self, new_side: chess.Color, duration: float = 1.0, ) -> None:
#         super().__init__()
#         self._new_side = new_side
#         self._duration = duration
#         self.frames = [[0] * 64, [255] * 64, [100] * 64]*50  # Example frames

#         self.idx = 0

#     def next_frame(self) -> AnimationFrame | None:
#         if self.idx >= len(self.frames):
#             return None

#         frame_data = self.frames[self.idx]
#         colors = {}
#         for square in chess.SQUARES:
#             intensity = frame_data[square]
#             if self._new_side == chess.WHITE:
#                 color = (intensity, intensity, intensity)  # White side
#             else:
#                 color = (intensity // 2, intensity // 2, intensity // 2)  # Dimmer for black side
#             colors[square] = color

#         self.idx += 1
#         return AnimationFrame(duration=self._duration / len(self.frames), colors=colors)


# if __name__ == "__main__":
#     import tkinter as tk
#     # Example usage
#     root = tk.Tk()
#     root.title("8x8 Chessboard")

#     square_size = 40
#     canvas = tk.Canvas(root, width=8*square_size, height=8*square_size)
#     canvas.pack()

#     rects = {}
#     for row in range(8):
#         for col in range(8):
#             x1 = col * square_size
#             y1 = row * square_size
#             x2 = x1 + square_size
#             y2 = y1 + square_size
#             rect = canvas.create_rectangle(x1, y1, x2, y2, fill="white", outline="black")
#             rects[chess.square(col, 7 - row)] = rect  # Map chess square to rectangle

#     anim = AnimationChangeSide(chess.WHITE, duration=1.0)

#     def rgb_to_hex(rgb):
#         return "#%02x%02x%02x" % rgb

#     def play_animation():
#         frame = anim.next_frame()
#         if frame is None:
#             return
#         for square, color in frame.colors.items():
#             canvas.itemconfig(rects[square], fill=rgb_to_hex(color))
#         root.after(int(frame.duration * 1000), play_animation)

#     play_animation()
#     root.mainloop()
