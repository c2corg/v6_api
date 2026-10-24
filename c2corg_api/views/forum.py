import logging

import colander
from cornice.resource import resource
from cornice.validators import colander_body_validator
from pyramid.httpexceptions import HTTPInternalServerError

from c2corg_api.models import DBSession
from c2corg_api.models.association import Association, association_keys_for_types
from c2corg_api.models.cache_version import update_cache_version_direct
from c2corg_api.models.common import document_types
from c2corg_api.models.document import Document, DocumentLocale
from c2corg_api.models.document_topic import DocumentTopic
from c2corg_api.models.user import User
from c2corg_api.security.acl import ACLDefault
from c2corg_api.security.discourse_client import get_discourse_client
from c2corg_api.views import cors_policy, restricted_view

log = logging.getLogger(__name__)


class SchemaTopicCreate(colander.MappingSchema):
    document_id = colander.SchemaNode(colander.Int())
    lang = colander.SchemaNode(colander.String())


schema_topic_create = SchemaTopicCreate()


def validate_topic_create(request, **kwargs):
    document_id = request.validated['document_id']
    lang = request.validated['lang']

    locale = (
        DBSession.query(DocumentLocale)
        .filter(DocumentLocale.document_id == document_id)
        .filter(DocumentLocale.lang == lang)
        .one_or_none()
    )
    if locale is None:
        request.errors.add('body', f'{document_id}/{lang}', 'Document not found')
        return
    request.validated['locale'] = locale

    document = (
        DBSession.query(Document)
        .filter(Document.document_id == document_id)
        .one_or_none()
    )
    if document is None:
        request.errors.add('body', f'{document_id}/{lang}', 'Document not found')
        return
    request.validated['document'] = document

    if locale.topic_id is not None:
        request.errors.add(
            'body',
            f'{document_id}_{lang}',
            'Topic already exists',
            topic_id=locale.topic_id,
        )


# Here path is required by cornice but related routes are not implemented
# as far as we only need collection_post to create topic in discourse
@resource(
    collection_path='/forum/topics', path='/forum/topics/{id}', cors_policy=cors_policy
)
class ForumTopicRest(ACLDefault):
    @restricted_view(
        schema=schema_topic_create,
        validators=[colander_body_validator, validate_topic_create],
    )
    def collection_post(self):
        settings = self.request.registry.settings

        locale = self.request.validated['locale']
        document = self.request.validated['document']
        document_type = association_keys_for_types[document.type]

        document_path = f'/{document_type}/{locale.document_id}/{locale.lang}'

        content = (
            f'<a href="https://www.camptocamp.org{document_path}">'
            f'{locale.title or document_path}</a>'
        )

        category = settings['discourse.category']
        # category could be id or name
        try:
            category = int(category)
        except ValueError:
            pass  # a name: use it as it is

        client = get_discourse_client(settings)
        try:
            title = f'{locale.document_id}_{locale.lang}'
            response = client.client.create_post(
                content, title=title, category_id=category
            )
        except Exception as e:
            log.error(f'Error with Discourse: {e!s}', exc_info=True)
            raise HTTPInternalServerError('Error with Discourse') from e

        if 'topic_id' in response:
            topic_id = response['topic_id']

            document_topic = DocumentTopic(topic_id=topic_id)
            locale.document_topic = document_topic
            update_cache_version_direct(locale.document_id)
            DBSession.flush()

            if locale.type == document_types.OUTING_TYPE:
                try:
                    self.invite_participants(client, locale, topic_id)
                except Exception:
                    log.error(
                        f'Inviting participants of outing {locale.document_id} failed',
                        exc_info=True,
                    )

        return response

    def invite_participants(self, client, locale, topic_id):
        participants = (
            DBSession.query(User.forum_username)
            .join(Association, Association.parent_document_id == User.id)
            .filter(Association.child_document_id == locale.document_id)
            .group_by(User.forum_username)
        )

        for (forum_username,) in participants:
            try:
                client.invite_user_to_topic(forum_username, topic_id)
            except Exception:
                log.error(
                    f'Inviting forum user {forum_username} in topic {topic_id} failed',
                    exc_info=True,
                )
