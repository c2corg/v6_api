from datetime import datetime, timedelta
import abc


class MigrateBase(object):

    def __init__(self, connection_source, session_target, batch_size):
        self.connection_source = connection_source
        self.session_target = session_target
        self.batch_size = batch_size
        self.last_progress_update = None
        self.start_time = None

    @abc.abstractmethod
    def migrate(self):
        pass

    def start(self, type):
        print(('Importing {0}'.format(type)))
        self.start_time = datetime.now()

    def stop(self):
        duration = datetime.now() - self.start_time
        print('Done (duration: {0})'.format(duration))

    def progress(self, count, total_count):
        if self.last_progress_update is None or \
                self.last_progress_update + timedelta(seconds=1) < \
                datetime.now():
            print('{0} of {1}'.format(count, total_count))
            self.last_progress_update = datetime.now()
