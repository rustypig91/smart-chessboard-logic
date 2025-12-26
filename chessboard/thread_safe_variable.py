from typing import Any, TypeVar, Generic, List
from threading import Lock

T = TypeVar('T')


class ThreadSafeVariable(Generic[T]):
    """ A variable that is safe to access from multiple threads. """

    def __init__(self, initial_value: T):
        self._value = initial_value
        self._lock = Lock()

    def get(self) -> T:
        with self._lock:
            if hasattr(self._value, 'copy'):
                return self._value.copy()  # type: ignore
            return self._value

    def set(self, new_value: T) -> None:
        with self._lock:
            self._value = new_value
