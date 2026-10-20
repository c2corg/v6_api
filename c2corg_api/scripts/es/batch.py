import abc


class Batch(object):
    """A base class for inserting entities in batches.
    """

    def __init__(self, session, batch_size):
        self.session = session
        self.batch_size = batch_size

    def flush_or_not(self):
        if self.should_flush():
            self.flush()

    @abc.abstractmethod
    def flush(self):
        pass

    @abc.abstractmethod
    def should_flush(self):
        pass

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val:
            return False
        else:
            self.flush()
