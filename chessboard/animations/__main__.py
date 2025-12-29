
import chess

import tkinter as tk
from chessboard.animations.rainbow import AnimationRainbow
from chessboard.animations.pulse import AnimationPulse
import chessboard.events as events


class TKInterBoard:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("8x8 Chessboard")

        square_size = 80
        self.canvas = tk.Canvas(self.root, width=8*square_size, height=8*square_size)
        self.canvas.pack()

        self.rects = {}
        for row in range(8):
            for col in range(8):
                x1 = col * square_size
                y1 = row * square_size
                x2 = x1 + square_size
                y2 = y1 + square_size
                rect = self.canvas.create_rectangle(x1, y1, x2, y2, fill="white", outline="black")
                self.rects[chess.square(col, 7 - row)] = rect  # Map chess square to rectangle

        events.event_manager.subscribe(events.SetSquareColorEvent, self._handle_set_square_color_event)

    def _handle_set_square_color_event(self, event: events.SetSquareColorEvent):
        for square, color in event.color_map.items():
            hex_color = "#%02x%02x%02x" % color
            self.canvas.itemconfig(self.rects[square], fill=hex_color)

    def run(self):
        self.root.mainloop()


board = TKInterBoard()
# animation = AnimationRainbow(
#     fps=15.0,
#     speed=0.05,
#     loop=True,
# )

animation = AnimationPulse(
    pulsating_squares=[chess.E4, chess.D4, chess.E5, chess.D5],
    frequency_hz=1.0,
    pulsating_color=(0, 255, 0),
    fps=15.0,
    pulses=10,
    priority=500,
)

board.root.after(100, animation.start)
board.run()
