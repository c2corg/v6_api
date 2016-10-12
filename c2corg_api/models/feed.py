from c2corg_api.models import Base, schema, users_schema, enums
from c2corg_api.models.area import Area
from c2corg_api.models.document import Document
from c2corg_api.models.enums import feed_change_type
from c2corg_api.models.image import Image
from c2corg_api.models.user import User
from c2corg_api.models.utils import ArrayOfEnum
from sqlalchemy.dialects.postgresql.base import ARRAY
from sqlalchemy.orm import relationship, column_property
from sqlalchemy.sql.expression import select
from sqlalchemy.sql.functions import func
from sqlalchemy.sql.schema import Column, ForeignKey, PrimaryKeyConstraint, \
    CheckConstraint, Index
from sqlalchemy.sql.sqltypes import Integer, String, DateTime, Boolean
from sqlalchemy import event, DDL


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

    time = Column(DateTime, default=func.now(), nullable=False, index=True)

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
        # TODO index for enum array? as text?
        # Index(
        #     'ix_guidebook_feed_document_changes_activities', activities,
        #     postgresql_using='gin'),
        Index(
            'ix_guidebook_feed_document_changes_area_ids', area_ids,
            postgresql_using='gin'),
        Index(
            'ix_guidebook_feed_document_changes_user_ids', user_ids,
            postgresql_using='gin'),
        Base.__table_args__
    )

# For performance reasons, areas and users are referenced in simple integer
# arrays in 'feed_document_changes', no PK-FK relations are set up. To prevent
# inconsistencies, triggers are used.
trigger_ddl = DDL("""
-- when creating a change, check that the given user and area ids are valid
CREATE OR REPLACE FUNCTION guidebook.check_feed_ids() RETURNS TRIGGER AS
$BODY$
DECLARE
  user_id int;
  area_id int;
BEGIN
  -- check user ids
  FOREACH user_id IN ARRAY new.user_ids LOOP
    PERFORM id from users.user where id = user_id;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'Invalid user id: %%', user_id;
    END IF;
  END LOOP;
  -- check area ids
  FOREACH area_id IN ARRAY new.area_ids LOOP
    PERFORM document_id from guidebook.areas where document_id = area_id;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'Invalid area id: %%', area_id;
    END IF;
  END LOOP;
  RETURN null;
END;
$BODY$
language plpgsql;

CREATE TRIGGER guidebook_feed_document_changes_insert
AFTER INSERT OR UPDATE ON guidebook.feed_document_changes
FOR EACH ROW
EXECUTE PROCEDURE guidebook.check_feed_ids();

-- when deleting a user, check that there are no changes referencing the user
CREATE OR REPLACE FUNCTION guidebook.check_feed_user_ids() RETURNS TRIGGER AS
$BODY$
BEGIN
  -- check user ids
  PERFORM change_id from guidebook.feed_document_changes
    where user_ids @> ARRAY[OLD.id] limit 1;
  IF FOUND THEN
    RAISE EXCEPTION 'Row in feed_document_changes still references user id %%',
      OLD.id;
  END IF;
  RETURN null;
END;
$BODY$
language plpgsql;

CREATE TRIGGER users_user_delete
AFTER DELETE ON users.user
FOR EACH ROW
EXECUTE PROCEDURE guidebook.check_feed_user_ids();

-- when deleting an area, check that there are no changes referencing the area
CREATE OR REPLACE FUNCTION guidebook.check_feed_area_ids() RETURNS TRIGGER AS
$BODY$
BEGIN
  -- check area ids
  PERFORM change_id from guidebook.feed_document_changes
    where area_ids @> ARRAY[OLD.document_id] limit 1;
  IF FOUND THEN
    RAISE EXCEPTION 'Row in feed_document_changes still references area id %%',
      OLD.document_id;
  END IF;
  RETURN null;
END;
$BODY$
language plpgsql;

CREATE TRIGGER guidebook_areas_delete
AFTER DELETE ON guidebook.areas
FOR EACH ROW
EXECUTE PROCEDURE guidebook.check_feed_area_ids();
""")
event.listen(DocumentChange.__table__, 'after_create', trigger_ddl)
