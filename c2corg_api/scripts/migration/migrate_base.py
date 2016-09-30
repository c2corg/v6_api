from datetime import datetime, timedelta
import abc
import phpserialize


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

    def convert_type(self, type_index, mapping, skip_values=[0]):
        if type_index is None:
            return None
        if skip_values is not None and type_index in skip_values:
            return None

        old_type = str(type_index)
        if old_type in mapping:
            return mapping[old_type]
        else:
            raise AssertionError(
                'invalid type: {0}'.format(type_index))

    def convert_types(self, old_types, mapping, skip_values=[0]):
        if old_types is None:
            return None
        new_types = list(set(
            [self.convert_type(old_type, mapping, skip_values)
                for old_type in old_types]))
        return [t for t in new_types if t is not None]


def parse_php_object(serialized):
    data = bytes(serialized, encoding='utf-8')
    return phpserialize.loads(
        data, object_hook=phpserialize.phpobject, decode_strings=True)
