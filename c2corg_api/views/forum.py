import colander

from c2corg_api.models.common import document_types

from c2corg_api.models import DBSession
from c2corg_api.models.association import Association, \
    association_keys_for_types
from c2corg_api.models.cache_version import update_cache_version_direct
from c2corg_api.models.document import Document, DocumentLocale
from c2corg_api.models.document_topic import DocumentTopic
from c2corg_api.models.user import User
from c2corg_api.security.discourse_client import get_discourse_client

from cornice.resource import resource
from cornice.validators import colander_body_validator

from c2corg_api.views import cors_policy, restricted_view

from pyramid.httpexceptions import HTTPInternalServerError

import logging
log = logging.getLogger(__name__)


@resource(path='/forum/private-messages/unread-count', cors_policy=cors_policy)
class PrivateMessageRest(object):
    def __init__(self, request):
        self.request = request

    @restricted_view(renderer='json')
    def get(self):
        settings = self.request.registry.settings
        userid = self.request.authenticated_userid

        client = get_discourse_client(settings)
        d_username = client.get_username(userid)
        messages = client.client.private_messages_unread(d_username)

        count = len(messages['topic_list']['topics'])
        link = '%s/users/%s/messages' % (
            client.discourse_public_url, d_username)

        return {link: link, count: count}


class SchemaTopicCreate(colander.MappingSchema):
    document_id = colander.SchemaNode(colander.Int())
    lang = colander.SchemaNode(colander.String())


schema_topic_create = SchemaTopicCreate()


def validate_topic_create(request, **kwargs):
    document_id = request.validated['document_id']
    lang = request.validated['lang']

    locale = DBSession.query(DocumentLocale) \
        .filter(DocumentLocale.document_id == document_id) \
        .filter(DocumentLocale.lang == lang) \
        .one_or_none()
    if locale is None:
        request.errors.add('body',
                           '{}/{}'.format(document_id, lang),
                           'Document not found')
        return
    request.validated['locale'] = locale

    document = DBSession.query(Document) \
        .filter(Document.document_id == document_id) \
        .one_or_none()
    if document is None:
        request.errors.add('body',
                           '{}/{}'.format(document_id, lang),
                           'Document not found')
        return
    request.validated['document'] = document

    if locale.topic_id is not None:
        request.errors.add('body',
                           '{}_{}'.format(document_id, lang),
                           'Topic already exists',
                           topic_id=locale.topic_id)


# Here path is required by cornice but related routes are not implemented
# as far as we only need collection_post to create topic in discourse
@resource(collection_path='/forum/topics', path='/forum/topics/{id}',
          cors_policy=cors_policy)
class ForumTopicRest(object):
    def __init__(self, request):
        self.request = request

    @restricted_view(
        schema=schema_topic_create,
        validators=[colander_body_validator, validate_topic_create])
    def collection_post(self):
        settings = self.request.registry.settings

        locale = self.request.validated['locale']
        document = self.request.validated['document']
        document_type = association_keys_for_types[document.type]

        document_path = "/{}/{}/{}".format(document_type,
                                           locale.document_id,
                                           locale.lang)

        content = '<a href="https://www.camptocamp.org{}">{}</a>'.format(
            document_path, locale.title or document_path)

        category = settings['discourse.category']
        # category could be id or name
        try:
            category = int(category)
        except Exception:
            pass

        client = get_discourse_client(settings)
        try:
            title = "{}_{}".format(locale.document_id, locale.lang)
            response = client.client.create_post(content,
                                                 title=title,
                                                 category=category)
        except Exception as e:
            log.error('Error with Discourse: {}'.format(str(e)), exc_info=True)
            raise HTTPInternalServerError('Error with Discourse')

        if "topic_id" in response:
            topic_id = response['topic_id']

            document_topic = DocumentTopic(topic_id=topic_id)
            locale.document_topic = document_topic
            update_cache_version_direct(locale.document_id)
            DBSession.flush()

            if locale.type == document_types.OUTING_TYPE:
                try:
                    self.invite_participants(client, locale, topic_id)
                except Exception:
                    log.error('Inviting participants of outing {} failed'
                              .format(locale.document_id),
                              exc_info=True)

        return response

    def invite_participants(self, client, locale, topic_id):
        participants = DBSession.query(User.forum_username). \
            join(Association, Association.parent_document_id == User.id). \
            filter(Association.child_document_id == locale.document_id). \
            group_by(User.forum_username)

        for (forum_username,) in participants:
            try:
                client.client.invite_user_to_topic_by_username(forum_username,
                                                               topic_id)
            except Exception:
                log.error('Inviting forum user {} in topic {} failed'
                          .format(forum_username, topic_id),
                          exc_info=True)
