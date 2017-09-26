import logging

from c2corg_api.models import Base, schema, users_schema, enums, DBSession
from c2corg_api.models.area import Area, AREA_TYPE
from c2corg_api.models.area_association import AreaAssociation
from c2corg_api.models.article import ARTICLE_TYPE
from c2corg_api.models.association import Association
from c2corg_api.models.book import BOOK_TYPE
from c2corg_api.models.document import Document, DocumentLocale, UpdateType
from c2corg_api.models.enums import feed_change_type
from c2corg_api.models.image import Image, IMAGE_TYPE
from c2corg_api.models.outing import OUTING_TYPE
from c2corg_api.models.route import ROUTE_TYPE
from c2corg_api.models.user import User
from c2corg_api.models.user_profile import USERPROFILE_TYPE
from c2corg_api.models.utils import ArrayOfEnum
from c2corg_api.models.xreport import XREPORT_TYPE
from c2corg_api.views.validation import association_keys
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql.array import ARRAY
from sqlalchemy.orm import relationship, column_property
from sqlalchemy.sql.elements import literal_column
from sqlalchemy.sql.expression import select, text, cast
from sqlalchemy.sql.functions import func
from sqlalchemy.sql.schema import Column, ForeignKey, PrimaryKeyConstraint, \
    CheckConstraint, Index
from sqlalchemy.sql.sqltypes import Integer, String, DateTime, Boolean

log = logging.getLogger(__name__)


class FilterArea(Base):
    """Feed filter on areas for a user.

    E.g. with an entry (user_id=1, area_id=2) the user 1 will only
    see changes in area 2 in their feed (except changes from followed users).
    """
    __tablename__ = 'feed_filter_area'

    area_id = Column(
        Integer, ForeignKey(schema + '.areas.document_id'),
        nullable=False)
    area = relationship(
        Area, primaryjoin=area_id == Area.document_id)

    user_id = Column(
        Integer, ForeignKey(users_schema + '.user.id'),
        nullable=False, index=True)
    user = relationship(
        User, primaryjoin=user_id == User.id
    )

    __table_args__ = (
        PrimaryKeyConstraint(area_id, user_id),
        Base.__table_args__
    )


User.has_area_filter = column_property(
    select([func.count(FilterArea.area_id) > 0]).
    where(FilterArea.user_id == User.id).
    correlate_except(FilterArea),
    deferred=True
)
User.feed_filter_areas = relationship('Area', secondary=FilterArea.__table__)


class FollowedUser(Base):
    """Tracks which user follows which user.

    E.g. if user 1 follows user 2, user 1 will see changes of user 2 in their
    feed.
    """
    __tablename__ = 'feed_followed_users'

    followed_user_id = Column(
        Integer, ForeignKey(users_schema + '.user.id'),
        nullable=False)
    followed_user = relationship(
        User, primaryjoin=followed_user_id == User.id
    )

    follower_user_id = Column(
        Integer, ForeignKey(users_schema + '.user.id'),
        nullable=False)
    follower_user = relationship(
        User, primaryjoin=follower_user_id == User.id
    )

    __table_args__ = (
        PrimaryKeyConstraint(followed_user_id, follower_user_id),
        CheckConstraint(
            'followed_user_id != follower_user_id',
            name='check_feed_followed_user_self_follow'),
        Base.__table_args__
    )


User.is_following_users = column_property(
    select([func.count(FollowedUser.followed_user_id) > 0]).
    where(FollowedUser.follower_user_id == User.id).
    correlate_except(FollowedUser),
    deferred=True
)


class DocumentChange(Base):
    """This table contains "changes" that are shown in the homepage feed and
    the user profile.
    For example if a user creates a document or uploads images, an entry is
    added to this table.
    """
    __tablename__ = 'feed_document_changes'

    change_id = Column(Integer, primary_key=True)

    time = Column(DateTime(timezone=True), default=func.now(), nullable=False)

    # the actor: who did the change?
    user_id = Column(
        Integer, ForeignKey(users_schema + '.user.id'),
        nullable=False)
    user = relationship(User, primaryjoin=user_id == User.id)

    # the action type: what did the user do? e.g. create or update a document
    change_type = Column(feed_change_type, nullable=False)

    # the object: what document did the user change?
    document_id = Column(
        Integer, ForeignKey(schema + '.documents.document_id'),
        nullable=False)
    document = relationship(
        Document, primaryjoin=document_id == Document.document_id
    )

    document_type = Column(String(1), nullable=False)

    # activities related to the document
    activities = Column(
        ArrayOfEnum(enums.activity_type), nullable=False, server_default='{}')

    # langs of the document locales
    langs = Column(
        ArrayOfEnum(enums.lang), nullable=False, server_default='{}')

    # For performance reasons, areas and users are referenced in simple integer
    # arrays in 'feed_document_changes', no PK-FK relations are set up.
    # To prevent inconsistencies, triggers are used.

    # ids of the areas where this change happened
    area_ids = Column(ARRAY(Integer), nullable=False, server_default='{}')

    # ids of the users that were involved in this change (e.g. the user that
    # created a document, but also the participants of an outing)
    user_ids = Column(ARRAY(Integer), nullable=False, server_default='{}')

    # images
    image1_id = Column(
        Integer, ForeignKey(schema + '.images.document_id'))
    image1 = relationship(
        Image, primaryjoin=image1_id == Image.document_id)
    image2_id = Column(
        Integer, ForeignKey(schema + '.images.document_id'))
    image2 = relationship(
        Image, primaryjoin=image2_id == Image.document_id)
    image3_id = Column(
        Integer, ForeignKey(schema + '.images.document_id'))
    image3 = relationship(
        Image, primaryjoin=image3_id == Image.document_id)
    more_images = Column(Boolean, server_default='FALSE', nullable=False)

    __table_args__ = (
        # the queries on the feed table always order by time (desc) and
        # change_id, therefore create an index for these two columns.
        Index(
            'ix_guidebook_feed_document_changes_time_and_change_id',
            time.desc(), change_id,
            postgresql_using='btree'),
        Base.__table_args__
    )

    def copy(self):
        copy = DocumentChange()
        copy.document_id = self.document_id
        copy.document_type = self.document_type
        copy.change_type = self.change_type
        copy.activities = self.activities
        copy.langs = self.langs
        copy.area_ids = self.area_ids
        if copy.document_type == OUTING_TYPE:
            copy.user_ids = self.user_ids
        else:
            copy.user_ids = []
        return copy


def update_feed_document_create(document, user_id):
    """Creates a new entry in the feed table when creating a new document.
    """
    if document.redirects_to or \
            document.type in NO_FEED_DOCUMENT_TYPES:
        return

    # make sure all updates are written to the database, so that areas and
    # users can be queried
    DBSession.flush()

    activities = []
    if document.type in [ARTICLE_TYPE, OUTING_TYPE, ROUTE_TYPE,
                         BOOK_TYPE, XREPORT_TYPE]:
        activities = document.activities

    langs = [locale.lang for locale in document.locales]

    user_ids = [user_id]
    if document.type == OUTING_TYPE:
        participant_ids = _get_participants_of_outing(document.document_id)
        user_ids = list(set(user_ids).union(participant_ids))

    area_ids = []
    if document.type != ARTICLE_TYPE:
        area_ids = _get_area_ids(document)

    change = DocumentChange(
        user_id=user_id,
        change_type='created',
        document_id=document.document_id,
        document_type=document.type,
        activities=activities,
        langs=langs,
        area_ids=area_ids,
        user_ids=user_ids
    )
    DBSession.add(change)
    DBSession.flush()


def update_feed_document_update(document, user_id, update_types):
    """Update the feed entry for a document:

    - update `area_ids` if the geometry has changed.
    - update `activities` if figures have changed.
    - update `user_ids` if the document is an outing and the participants
      have changed.

    Only when updating `user_ids`, the "actor" of the feed entry is changed.
    And only then the time is updated and the `change_type` set to `updated`
    to push the entry to the top of the feed.
    """
    if document.redirects_to:
        # TODO delete existing feed entry?
        # see https://github.com/c2corg/v6_api/issues/386
        return
    if document.type in [IMAGE_TYPE, USERPROFILE_TYPE, AREA_TYPE]:
        return

    DBSession.flush()

    # update areas
    if UpdateType.GEOM in update_types:
        update_areas_of_changes(document)

    # updates activities
    if document.type in [ARTICLE_TYPE, OUTING_TYPE, ROUTE_TYPE,
                         BOOK_TYPE, XREPORT_TYPE] and \
            UpdateType.FIGURES in update_types:
        update_activities_of_changes(document)

    update_langs_of_changes(document)

    # update users_ids/participants (only for outings)
    if document.type != OUTING_TYPE:
        return

    update_participants_of_outing(document.document_id, user_id)


def update_participants_of_outing(outing_id, user_id):
    existing_change = get_existing_change(outing_id)

    if not existing_change:
        log.warn('no feed change for document {}'.format(outing_id))
        return

    participant_ids = _get_participants_of_outing(outing_id)
    if set(existing_change.user_ids) == set(participant_ids):
        # participants have not changed, stop
        return
    existing_change.user_ids = participant_ids

    if existing_change.user_id != user_id:
        # a different user is doing this change, only set a different user id
        # if the user is one of the participants (to ignore moderator edits)
        if user_id in participant_ids:
            existing_change.user_id = user_id

    existing_change.change_type = 'updated'
    existing_change.time = func.now()

    DBSession.flush()

    # now also update the participants of other feed entries of the outing:
    # set `user_ids` to the union of the participant ids and the `user_id` of
    # the entry
    participants_and_editor = text(
        'ARRAY(SELECT DISTINCT UNNEST(array_cat('
        '   ARRAY[guidebook.feed_document_changes.user_id], :participants)) '
        'ORDER BY 1)')
    DBSession.execute(
        DocumentChange.__table__.update().
        where(DocumentChange.document_id == outing_id).
        where(DocumentChange.change_id != existing_change.change_id).
        values(user_ids=participants_and_editor),
        {'participants': participant_ids}
    )


def get_existing_change(document_id):
    return DBSession. \
        query(DocumentChange). \
        filter(DocumentChange.document_id == document_id). \
        filter(DocumentChange.change_type.in_(['created', 'updated'])). \
        first()


def get_existing_change_for_user(document_id, user_id):
    return DBSession. \
        query(DocumentChange). \
        filter(DocumentChange.document_id == document_id). \
        filter(DocumentChange.user_id == user_id). \
        order_by(DocumentChange.time.desc()). \
        first()


def update_feed_association_update(
        _parent_document_id, parent_document_type,
        child_document_id, child_document_type, user_id):
    """Update the feed entries when associations have been created or deleted.
    Currently only associations between outings and users are considered.
    """
    if not (parent_document_type == USERPROFILE_TYPE and
            child_document_type == OUTING_TYPE):
        return
    update_participants_of_outing(child_document_id, user_id)


def update_feed_images_upload(images, images_in, user_id):
    """When uploading a set of images, create a feed entry for the document
     the images are linked to.
    """
    if not images or not images_in:
        return
    assert len(images) == len(images_in)

    # get the document that the images were uploaded to
    document_id, document_type = get_linked_document(images_in)
    if not document_id or not document_type:
        return

    image1_id, image2_id, image3_id, more_images = get_images(
        images, images_in, document_id, document_type)

    if not image1_id:
        return

    # load the feed entry for the images
    change = get_existing_change(document_id)
    if not change:
        log.warn('no feed change for document {}'.format(document_id))
        return

    if change.user_id == user_id:
        # if the same user, only update time and change_type.
        # this avoids that multiple entries are shown in the feed for the same
        # document.
        change.change_type = 'updated'
        change.time = func.now()
    else:
        # if different user: first try to get an existing feed entry of the
        # user for the document
        change_by_user = get_existing_change_for_user(document_id, user_id)
        if change_by_user:
            change = change_by_user
            change.change_type = 'added_photos'
            change.time = func.now()
        else:
            change = change.copy()
            change.change_type = 'added_photos'
            change.user_id = user_id
            change.user_ids = list(set(change.user_ids).union([user_id]))

    _update_images(change, image1_id, image2_id, image3_id, more_images)

    DBSession.add(change)
    DBSession.flush()


def _update_images(change, image1_id, image2_id, image3_id, more_images):
    """ Set the new images on a feed entry by keeping the old images if
    there are not enough new ones.
    """
    existing_images = [
        image_id for image_id in [
            change.image1_id, change.image2_id, change.image3_id
        ] if image_id is not None
    ]

    change.image1_id = image1_id
    change.image2_id = image2_id or (existing_images.pop()
                                     if existing_images else None)
    change.image3_id = image3_id or (existing_images.pop()
                                     if existing_images else None)
    change.more_images = more_images or change.more_images or \
        len(existing_images) > 0


def _get_participants_of_outing(outing_id):
    participant_ids = DBSession. \
        query(Association.parent_document_id). \
        filter(Association.child_document_id == outing_id). \
        filter(Association.parent_document_type == USERPROFILE_TYPE). \
        all()
    return [user_id for (user_id,) in participant_ids]


def _get_area_ids(document):
    area_ids = DBSession. \
        query(AreaAssociation.area_id). \
        filter(AreaAssociation.document_id == document.document_id). \
        all()
    return [area_id for (area_id,) in area_ids]


def update_areas_of_changes(document):
    """Update the area ids of all feed entries of the given document.
    """
    areas_select = select(
            [
                # concatenate with empty array to avoid null values
                # select ARRAY[]::integer[] || array_agg(area_id)
                literal_column('ARRAY[]::integer[]').op('||')(
                    func.array_agg(
                        AreaAssociation.area_id,
                        type_=postgresql.ARRAY(Integer)))
            ]).\
        where(AreaAssociation.document_id == document.document_id)

    DBSession.execute(
        DocumentChange.__table__.update().
        where(DocumentChange.document_id == document.document_id).
        values(area_ids=areas_select.as_scalar())
    )


def update_activities_of_changes(document):
    """Update the activities of all feed entries of the given document.
    """
    DBSession.execute(
        DocumentChange.__table__.update().
        where(DocumentChange.document_id == document.document_id).
        values(activities=document.activities)
    )


def update_langs_of_changes(document):
    """Update the langs of all feed entries of the given document.
    """
    langs = DBSession. \
        query(cast(
            func.array_agg(DocumentLocale.lang),
            ArrayOfEnum(enums.lang))). \
        filter(DocumentLocale.document_id == document.document_id). \
        group_by(DocumentLocale.document_id). \
        subquery('langs')
    DBSession.execute(
        DocumentChange.__table__.update().
        where(DocumentChange.document_id == document.document_id).
        values(langs=langs.select()))


def get_linked_document(images_in):
    """Given a list of image inputs, return a linked document from the first
    image.
    """
    assert images_in

    image_in = images_in[0]
    associations = image_in.get('associations')
    if not associations:
        return None, None

    for doc_key, docs in associations.items():
        doc_type = association_keys[doc_key]

        if doc_type in NO_FEED_DOCUMENT_TYPES:
            continue

        if docs:
            return docs[0]['document_id'], doc_type

    return None, None


def get_images(images, images_in, document_id, document_type):
    """Returns the first 3 images that are associated to the given document.
    """
    image_count = len(images)

    # get all the images linked to the document
    image_ids = []
    for i in range(0, image_count):
        image_in = images_in[i]

        if is_linked_to_doc(image_in, document_id, document_type):
            image_ids.append(images[i].document_id)

        if len(image_ids) > 3:
            break

    # then select the first 3 images
    image1_id = None
    image2_id = None
    image3_id = None
    more_images = False

    if image_ids:
        image1_id = image_ids.pop(0)

    if image_ids:
        image2_id = image_ids.pop(0)

    if image_ids:
        image3_id = image_ids.pop(0)

    if image_ids:
        more_images = True

    return image1_id, image2_id, image3_id, more_images


def is_linked_to_doc(image_in, document_id, document_type):
    """Check if the given document is linked to the image.
    """
    associations = image_in.get('associations')
    if not associations:
        return False

    for doc_key, docs in associations.items():
        doc_type = association_keys[doc_key]

        if doc_type != document_type:
            continue

        for doc in docs:
            if doc['document_id'] == document_id:
                return True

    return False

# the document types that have no entry in the feed
NO_FEED_DOCUMENT_TYPES = [IMAGE_TYPE, USERPROFILE_TYPE, AREA_TYPE]
