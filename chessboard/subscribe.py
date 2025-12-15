import queue


class Event:
    pass


class Subscriber:
    """
    >>> pub = Publisher()
    >>> sub = Subscriber()
    >>> pub.subscribe(sub)
    >>> pub.notify_all("hello")
    >>> next(sub.get_updates())
    'hello'
    >>> pub.notify_all("world")
    >>> next(sub.get_updates())
    'world'
    >>> pub.unsubscribe(sub)
    >>> sub.publisher is None
    True
    """

    def __init__(self, function: Event | None = None):
        self.queue: queue.Queue = queue.Queue()
        self.publisher: Publisher | None = None
        self.function = function
        self.active: bool = True

    def notify(self, data):
        self.queue.put(data)

    def get_updates(self):
        while self.active:
            data = self.queue.get()
            yield data

    def __del__(self):
        if self.publisher:
            self.active = False
            self.publisher.unsubscribe(self)


class Publisher:
    """
    >>> pub = Publisher()
    >>> sub1 = Subscriber()
    >>> sub2 = Subscriber()
    >>> pub.subscribe(sub1)
    >>> pub.subscribe(sub2)
    >>> pub.notify_all("move1")
    >>> next(sub1.get_updates())
    'move1'
    >>> next(sub2.get_updates())
    'move1'
    """

    def __init__(self):
        self.subscribers = []

    def subscribe(self, subscriber: Subscriber):
        self.subscribers.append(subscriber)
        subscriber.publisher = self

    def unsubscribe(self, subscriber: Subscriber):
        subscriber.publisher = None
        self.subscribers.remove(subscriber)

    def notify_all(self, data: Event):
        for subscriber in self.subscribers:
            if subscriber.function:
                subscriber.function(data)
            else:
                subscriber.notify(data)


if __name__ == "__main__":
    import doctest

    doctest.testmod(verbose=True)
