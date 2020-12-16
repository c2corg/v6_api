from c2corg_api.models import DBSession
from c2corg_api.models.association import Association, AssociationLog
from c2corg_api.models.cache_version import \
    update_cache_version_direct, update_cache_version_full
from c2corg_api.models.document import Document, UpdateType
from c2corg_api.models.document_tag import DocumentTag, DocumentTagLog
from c2corg_api.models.feed import DocumentChange
from c2corg_api.models.image import IMAGE_TYPE
from c2corg_api.models.route import Route
from c2corg_api.models.user_profile import USERPROFILE_TYPE
from c2corg_api.models.waypoint import WAYPOINT_TYPE, Waypoint
from c2corg_api.search.notify_sync import notify_es_syncer
from c2corg_api.views import cors_policy, restricted_json_view
from c2corg_api.views.document import DocumentRest
from c2corg_api.views.image import delete_all_files_for_image
from c2corg_api.views.waypoint import update_linked_route_titles
from colander import MappingSchema, required, SchemaNode, Integer
from cornice.resource import resource
from cornice.validators import colander_body_validator
from sqlalchemy.sql.elements import not_
from sqlalchemy.sql.expression import and_, or_
from sqlalchemy.sql.functions import func


class MergeSchema(MappingSchema):
    source_document_id = SchemaNode(Integer(), missing=required)
    target_document_id = SchemaNode(Integer(), missing=required)


def validate_documents(request, **kwargs):
    """ Checks that

    - the documents exists.
    - the documents are of the same type.
    - the type is not USERPROFILE_TYPE.
    - the documents are not redirected yet.
    """
    if 'source_document_id' not in request.validated or \
            'target_document_id' not in request.validated:
        return

    source_document_id = request.validated['source_document_id']
    target_document_id = request.validated['target_document_id']

    if source_document_id == target_document_id:
        request.errors.add(
            'body', 'target_document_id', 'Cannot merge document with itself')
        return

    source_info = DBSession.query(Document.redirects_to, Document.type). \
        filter(Document.document_id == source_document_id). \
        first()

    target_info = DBSession.query(Document.redirects_to, Document.type). \
        filter(Document.document_id == target_document_id). \
        first()

    # do the documents exist?
    if not source_info or not target_info:
        if not source_info:
            request.errors.add(
                'body', 'source_document_id',
                'document {0} does not exist'.format(source_document_id))
        if not target_info:
            request.errors.add(
                'body', 'target_document_id',
                'document {0} does not exist'.format(target_document_id))
        return

    (source_redirects_to, source_type) = source_info
    (target_redirects_to, target_type) = target_info

    # are the documents not already merged?
    if source_redirects_to or target_redirects_to:
        if source_redirects_to:
            request.errors.add(
                'body', 'source_document_id',
                'document {0} is already redirected'.format(
                    source_document_id))
        if target_redirects_to:
            request.errors.add(
                'body', 'target_document_id',
                'document {0} is also redirected'.format(target_document_id))
        return

    # do they have the same type?
    if source_type != target_type:
        request.errors.add(
            'body', 'types', 'documents must have the same type')

    if source_type == USERPROFILE_TYPE:
        request.errors.add(
            'body', 'types', 'merging user accounts is not supported')


@resource(path='/documents/merge', cors_policy=cors_policy)
class MergeDocumentRest(object):

    def __init__(self, request):
        self.request = request

    @restricted_json_view(
        permission='moderator',
        schema=MergeSchema(),
        validators=[colander_body_validator, validate_documents])
    def post(self):
        """ Merges a document into another document.

        - Associations and tags of the source document are transferred to
          the target document.
        - The association log entries are rewritten to the target document.
        - The time of the log entries is updated, so that the ES syncer will
          pick up the new associations of the target document.
        - The attribute `redirects_to` of the source document is set.
        - A new version is created for the source document. This makes sure
          that the ES syncer removes the document from ES index.
        - Update the cache version of the source document.
        - Update the cache version of the target document and its associations.
        - Removes the feed entries of the source document.


        Request:
            `POST` `/documents/merge`

        Request body:
            {
                'source_document_id': @document_id@,
                'target_document_id': @document_id@
            }

        """
        source_document_id = self.request.validated['source_document_id']
        target_document_id = self.request.validated['target_document_id']
        source_doc = DBSession.query(Document).get(source_document_id)

        # transfer associations from source to target
        transfer_associations(source_document_id, target_document_id)

        # transfer tags from source to target
        transfer_tags(source_document_id, target_document_id)

        # if waypoint, update main waypoint of routes
        if source_doc.type == WAYPOINT_TYPE:
            _transfer_main_waypoint(source_document_id, target_document_id)

        # set redirection and create a new version
        source_doc.redirects_to = target_document_id
        DocumentRest.update_version(
            source_doc, self.request.authenticated_userid,
            'merged with {}'.format(target_document_id),
            [UpdateType.FIGURES], [])

        # update the cache version for the source and target document
        update_cache_version_direct(source_document_id)
        update_cache_version_full(target_document_id, source_doc.type)

        _remove_feed_entry(source_document_id)

        if source_doc.type == IMAGE_TYPE:
            delete_all_files_for_image(source_document_id, self.request)

        notify_es_syncer(self.request.registry.queue_config)

        return {}


def transfer_associations(source_document_id, target_document_id):
    # get the document ids the target is already associated with
    target_child_ids_result = DBSession. \
        query(Association.child_document_id). \
        filter(Association.parent_document_id == target_document_id). \
        all()
    target_child_ids = [
        child_id for (child_id,) in target_child_ids_result]
    target_parent_ids_result = DBSession. \
        query(Association.parent_document_id). \
        filter(Association.child_document_id == target_document_id). \
        all()
    target_parent_ids = [
        parent_id for (parent_id,) in target_parent_ids_result]

    # move the current associations (only if the target document does not
    # already have an association with the same document)
    DBSession.execute(
        Association.__table__.update().
        where(_and_in(
            Association.parent_document_id == source_document_id,
            Association.child_document_id, target_child_ids
        )).
        values(parent_document_id=target_document_id)
    )
    DBSession.execute(
        Association.__table__.update().
        where(_and_in(
            Association.child_document_id == source_document_id,
            Association.parent_document_id, target_parent_ids
        )).
        values(child_document_id=target_document_id)
    )

    # remove remaining associations
    DBSession.execute(
        Association.__table__.delete().
        where(or_(
            Association.child_document_id == source_document_id,
            Association.parent_document_id == source_document_id)
        )
    )

    # transfer the association log entries
    DBSession.execute(
        AssociationLog.__table__.update().
        where(_and_in(
            AssociationLog.parent_document_id == source_document_id,
            AssociationLog.child_document_id, target_child_ids
        )).
        values(
            parent_document_id=target_document_id,
            written_at=func.now()
        )
    )
    DBSession.execute(
        AssociationLog.__table__.update().
        where(_and_in(
            AssociationLog.child_document_id == source_document_id,
            AssociationLog.parent_document_id, target_parent_ids
        )).
        values(
            child_document_id=target_document_id,
            written_at=func.now()
        )
    )

    DBSession.execute(
        AssociationLog.__table__.delete().
        where(or_(
            AssociationLog.child_document_id == source_document_id,
            AssociationLog.parent_document_id == source_document_id)
        )
    )


def transfer_tags(source_document_id, target_document_id):
    # get the ids of users that have already tagged the target document
    target_user_ids_result = DBSession. \
        query(DocumentTag.user_id). \
        filter(DocumentTag.document_id == target_document_id). \
        all()
    target_user_ids = [user_id for (user_id,) in target_user_ids_result]

    # move the current tags (only if the target document does not
    # already have been tagged by the same user)
    DBSession.execute(
        DocumentTag.__table__.update().
        where(_and_in(
            DocumentTag.document_id == source_document_id,
            DocumentTag.user_id, target_user_ids
        )).
        values(document_id=target_document_id)
    )

    # remove remaining tags
    DBSession.execute(
        DocumentTag.__table__.delete().
        where(DocumentTag.document_id == source_document_id)
    )

    # transfer the tag log entries
    DBSession.execute(
        DocumentTagLog.__table__.update().
        where(_and_in(
            DocumentTagLog.document_id == source_document_id,
            DocumentTagLog.user_id, target_user_ids
        )).
        values(
            document_id=target_document_id,
            written_at=func.now()
        )
    )

    DBSession.execute(
        DocumentTagLog.__table__.delete().
        where(DocumentTagLog.document_id == source_document_id)
    )


def _and_in(condition1, field2, in_ids):
    if not in_ids:
        return condition1
    else:
        return and_(condition1, not_(field2.in_(in_ids)))


def _transfer_main_waypoint(source_document_id, target_document_id):
    target_waypoint = DBSession.query(Waypoint).get(target_document_id)

    DBSession.execute(
        Route.__table__.update().
        where(Route.main_waypoint_id == source_document_id).
        values(main_waypoint_id=target_document_id)
    )
    update_linked_route_titles(target_waypoint, [UpdateType.LANG], None)


def _remove_feed_entry(source_document_id):
    DBSession.query(DocumentChange). \
        filter(DocumentChange.document_id == source_document_id).delete()
