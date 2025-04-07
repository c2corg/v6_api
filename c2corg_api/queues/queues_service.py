from kombu import Exchange, Queue, pools
from kombu.connection import Connection
from kombu.pools import producers
from queue import Empty
from kombu.exceptions import TimeoutError
import logging

log = logging.getLogger('c2corg_api_queues')


def get_queue_config(settings, queue):
    # set the number of connections to Redis
    pools.set_limit(int(settings['redis.queue_pool']))

    class QueueConfiguration(object):
        def __init__(self, settings):
            self.connection = Connection(
                settings['redis.url'],
                virtual_host=settings['redis.db_queue']
            )
            self.routing_key = queue
            self.exchange = Exchange(settings['redis.exchange'], type='direct')
            self.queue = Queue(
                queue,
                self.exchange,
                routing_key=self.routing_key
            )

    return QueueConfiguration(settings)


def publish(queue_config, message):
    def retry(channel):
        """ Try to re-create the Redis queue on connection errors.
        """
        try:
            # try to unbind the queue, ignore errors
            channel.queue_unbind(
                queue_config.queue.name,
                exchange=queue_config.exchange.name)
        except Exception:
            pass

        # the re-create the queue
        channel.queue_bind(
            queue_config.queue.name, exchange=queue_config.exchange.name)

    with producers[queue_config.connection].acquire(
            block=True, timeout=3) as producer:
        producer.publish(
            message,
            exchange=queue_config.exchange,
            declare=[queue_config.exchange, queue_config.queue],
            retry=True,
            retry_policy={'max_retries': 3, 'on_revive': retry},
            routing_key=queue_config.routing_key
        )


def consume_all_messages(queue_config, process_task):
    bodies = []
    messages = []

    def populate_messages(body, message):
        bodies.append(body)
        messages.append(message)

    with queue_config.connection as connection:
        with connection.Consumer(
                queues=queue_config.queue,
                callbacks=[populate_messages]
        ):
            try:
                while True:
                    connection.drain_events(timeout=1)
            except KeyboardInterrupt:
                pass
            except Empty:
                log.info('No message in the queue')
                pass
            except TimeoutError:
                log.info('Queue timeout')
                pass
            try:
                process_task(bodies)
                for message in messages:
                    message.ack()
            except Exception as exc:
                log.error('Queue task raised exception: %r', exc)
