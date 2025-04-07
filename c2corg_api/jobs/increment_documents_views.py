import logging
from c2corg_api import get_queue_config
from sqlalchemy import engine_from_config, text
from c2corg_api.queues.queues_service import consume_all_messages
from sqlalchemy.orm import (
    scoped_session,
    sessionmaker,
)
from collections import Counter
import math
import time

log = logging.getLogger(__name__)

# The max number of documents to update per transaction
MAX_REQ = 4000

# The number of seconds to wait between each transaction
SLEEP_TIME = 2

# Bulk update base statement
BASE_STMT = """
    UPDATE guidebook.documents
    SET view_count = documents.view_count + updates.view_count
    FROM (VALUES
        {stmt_values}
        ) AS updates(document_id, view_count)
    WHERE documents.document_id = updates.document_id;
"""


def increment_documents_views(settings, test_session=None):
    queue = settings['redis.queue_documents_views_sync']
    queue_config = get_queue_config(settings, queue)

    def process_task(doc_ids):
        engine = engine_from_config(settings, 'sqlalchemy.')
        db_session = scoped_session(sessionmaker(bind=engine))
        session = db_session() if not test_session else test_session

        if len(doc_ids) != 0:
            doc_views = list(Counter(doc_ids).items())
            max_iteration = math.ceil(len(doc_views) / MAX_REQ)
            for i in range(max_iteration):
                docs = []
                for id, count in doc_views[i * MAX_REQ:(i + 1) * MAX_REQ]:
                    docs.append({
                     'document_id': id,
                     'view_count': count
                    })
                stmt_values = ", ".join(
                 f"({doc['document_id']}, {doc['view_count']})"
                 for doc in docs
                )
                stmt = text(BASE_STMT.format(stmt_values=stmt_values))
                session.execute(stmt)
                session.commit()
                docs.clear()
                if max_iteration > 1 and i != max_iteration - 1:
                    # Sleep to prevent blocking other transactions
                    time.sleep(SLEEP_TIME)

    consume_all_messages(queue_config, process_task)
