import chess
from chessboard.animations.change_side import AnimationChangeSide
from chessboard.animations.water_droplet import AnimationWaterDroplet
from chessboard.animations.rainbow import AnimationRainbow
from chessboard.animations.pulse import AnimationPulse
import chessboard.events as events
from chessboard.game.game_state import game_state
from chessboard.settings import settings, ColorSetting

settings.register('led.color.check', ColorSetting(255, 100, 0), 'Color for when the king is in check')
settings.register('led.color.water_droplet', ColorSetting(102, 204, 255), 'Color for water droplet animation')


_change_side_animation = AnimationChangeSide(
    new_side=chess.WHITE,
    fps=15.0,
    duration=0.5,
)


def _handle_chess_move_event(event: events.ChessMoveEvent) -> None:
    global _change_side_animation
    _change_side_animation.set_side(not event.side)


def _handle_piece_state_change(event: events.SquarePieceStateChangeEvent) -> None:
    # Trigger a ripple around newly dropped friendly pieces (None -> turn)
    if len(event.squares) != 1:
        return

    if event.colors[event.squares[0]] is not None:
        anim = AnimationWaterDroplet(
            fps=15.0,
            color=settings['led.color.water_droplet'],
            center_square=event.squares[0])
        anim.start()


_checkers_animation = AnimationPulse(
    pulsating_squares=[],
    frequency_hz=0.5,
    pulsating_color=settings['led.color.check'],
    fps=10.0,
)


def _handle_game_state_change(event: events.GameStateChangedEvent) -> None:
    checkers = game_state.board.checkers()
    king_square = game_state.board.king(game_state.board.turn)
    if checkers and king_square is not None:
        _checkers_animation.squares = list(checkers) + [king_square]
        if not _checkers_animation.is_running:
            _checkers_animation.start()

    if event.winner is not None:
        # Victory rainbow animation
        anim = AnimationRainbow(
            fps=15.0,
            speed=0.05,
            duration=10.0,
        )
        anim.start()


events.event_manager.subscribe(events.ChessMoveEvent, _handle_chess_move_event)
events.event_manager.subscribe(events.SquarePieceStateChangeEvent, _handle_piece_state_change)
events.event_manager.subscribe(events.GameStateChangedEvent, _handle_game_state_change)
_change_side_animation.start()
