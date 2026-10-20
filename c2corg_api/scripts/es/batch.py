import abc


class Batch(object):
    """A base class for inserting entities in batches."""

    def __init__(self, session, batch_size):
        """Create a batch flushing every ``batch_size`` entities."""
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
        """Start the batch."""

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Flush the remaining entities, unless an exception was raised."""
        if exc_val:
            return False
        else:
            self.flush()
