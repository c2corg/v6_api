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


class SimpleBatch(Batch):
    """A simple batch implementation which deals with a single model type.

    Example usage:

        batch = SimpleBatch(session, 1000, Document)
        with batch:
            ...
            batch.add(document)
    """

    def __init__(self, session, batch_size, model):
        super(SimpleBatch, self).__init__(session, batch_size)
        self.model = model
        self.entities = []

    def add(self, entity):
        self.entities.append(entity)
        self.flush_or_not()

    def should_flush(self):
        return len(self.entities) > self.batch_size

    def flush(self):
        if self.entities:
            self.session.bulk_insert_mappings(self.model, self.entities)
            self.session.flush()
            self.entities = []
