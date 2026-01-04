import chess
from chessboard.animations.change_side import AnimationChangeSide
from chessboard.animations.water_droplet import AnimationWaterDroplet
from chessboard.animations.rainbow import AnimationRainbow
from chessboard.animations.pulse import AnimationPulse
import chessboard.events as events
from chessboard.game.game_state import game_state
from chessboard.settings import settings, ColorSetting

settings.register('animation.check.color', ColorSetting(255, 100, 255), 'Color for when the king is in check')

settings.register('animation.legal_move.enabled', True, 'Enable animations for legal moves detected')
settings.register('animation.legal_move.color', ColorSetting(102, 204, 255), 'Color for water droplet animation')
settings.register('animation.hint.color', ColorSetting(0, 255, 0), 'Color for hint pulse animation')

_change_side_animation = AnimationChangeSide(
    new_side=chess.WHITE,
    fps=15.0,
    duration=0.5,
)
_change_side_animation.start()

_checkers_animation = AnimationPulse(
    pulsating_squares=[],
    frequency_hz=0.5,
    pulsating_color=settings['animation.check.color'],
    fps=10.0,
)

_hint_animation = AnimationPulse(
    pulsating_squares=[],
    frequency_hz=0.5,
    pulsating_color=settings['animation.hint.color'],
    fps=10.0,
)


def _handle_chess_move_event(event: events.ChessMoveEvent) -> None:
    global _change_side_animation
    _change_side_animation.set_side(not event.side)


def _handle_legal_move_detected(event: events.LegalMoveDetectedEvent) -> None:
    if not settings['animation.legal_move.enabled']:
        return
    # Trigger a ripple around newly dropped friendly pieces (None -> turn)
    anim = AnimationWaterDroplet(
        fps=15.0,
        color=settings['animation.legal_move.color'],
        center_square=event.move.to_square)
    anim.start()


_rainbow_animation_shown = False


def _handle_game_state_change(event: events.GameStateChangedEvent) -> None:
    checkers = game_state.board.checkers()
    king_square = game_state.board.king(game_state.board.turn)

    _hint_animation.stop()

    if checkers and king_square is not None:
        _checkers_animation.squares = list(checkers) + [king_square]
        if not _checkers_animation.is_running:
            _checkers_animation.start()
    else:
        _checkers_animation.stop()

    if event.winner is not None:
        global _rainbow_animation_shown
        # Make sure animation is only shown once per game end
        if not _rainbow_animation_shown:
            _rainbow_animation_shown = True
            anim = AnimationRainbow(
                fps=15.0,
                speed=0.05,
                duration=10.0,
            )
            anim.start()
    else:
        _rainbow_animation_shown = False


def _handle_hint_event(event: events.HintEvent) -> None:
    _hint_animation.squares = [event.move.from_square, event.move.to_square]
    if not _hint_animation.is_running:
        _hint_animation.start()


def _handle_sqaure_piece_state_change(event: events.SquarePieceStateChangeEvent) -> None:
    # Stop hint animation if either square involved changes piece state
    if _hint_animation.is_running:
        for square in event.squares:
            if square in _hint_animation.squares:
                _hint_animation.stop()


events.event_manager.subscribe(events.ChessMoveEvent, _handle_chess_move_event)
events.event_manager.subscribe(events.LegalMoveDetectedEvent, _handle_legal_move_detected)
events.event_manager.subscribe(events.GameStateChangedEvent, _handle_game_state_change)
events.event_manager.subscribe(events.HintEvent, _handle_hint_event)
events.event_manager.subscribe(events.SquarePieceStateChangeEvent, _handle_sqaure_piece_state_change)
