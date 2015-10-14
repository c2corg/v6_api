Versioning in c2c.org v6
=========================

The versioning is essential for the wiki functionality of the portal. The
following explains the main idea and implementation.

Data model
-----------

The base class for all documents (waypoints, routes, ...) is `Document`.
The translatable fields for each document are in `DocumentLocale` (and in its
child classes like `WaypointLocale`). And the geometries are in `DocumentGeometry`.
The tables for `Document`, `DocumentLocale` and `DocumentGeometry` always
contain the current version of a document (like a materialized view).

Besides `Document`, `DocumentLocale` and `DocumentGeometry`, there are the
classes `ArchiveDocument`, `ArchiveDocumentLocale` and `ArchiveDocumentGeometry`
which contain all versions of a document, its locales and geometry (including the
current version).

For the versioning there are two more classes: `HistoryMetaData` and `DocumentVersion`.
`HistoryMetaData` contains a change comment and the date. `DocumentVersion`
is the list of actual versions of a document for a language. A *document version*
for a language/culture references an entry in `ArchiveDocument`,
`ArchiveDocumentLocale`, `ArchiveDocumentGeometry` and `HistoryMetaData`.
It has the following fields: `document_id`, `culture`, `document_archive_id`,
`document_locales_archive_id`, `document_geometry_archive_id` and
`history_metadata_id`.

`Document`, `DocumentLocale` and `DocumentGeometry` all have a version field
that is configured as [SQLAlchemy version counter](http://docs.sqlalchemy.org/en/latest/orm/versioning.html).
This version is incremented every time the row is updated. At the same time this
version field serves as optimistic lock. When an update is made, the current
version has to be provided to prevent concurrent updates. The update statement
will look something like this:

    UPDATE document_locale SET version = 2, name = '...'
    WHERE id = 123 AND version = 1

Creating a new document
-----------------------

When creating a new document, for example a waypoint, with one locale, the
following happens:

 - An insert is made in the table of `Document` (and in the `Waypoint` table).
 - An insert is made in the table of `DocumentLocale` (and of `WaypointLocale`).
 - An insert is made in the table of `DocumentGeometry`.
 - An insert is made in the table of `ArchiveDocument` (and of `ArchiveWaypoint`).
 - An insert is made in the table of `ArchiveDocumentLocale` (and of `ArchiveWaypointLocale`).
 - An insert is made in the table of `ArchiveDocumentGeometry`.
 - An insert is made in the table of `HistoryMetaData`.
 - An insert is made in the table of `DocumentVersion`. This entry has a foreign
   key pointing to the new row in `ArchiveDocument`, `ArchiveDocumentLocale`
   and `ArchiveDocumentGeometry`.

Updating an existing document
------------------------------

Updating an existing document is a bit more involved. To avoid that data is
duplicated for no reason, it makes a difference if only figures (in `Document`/
`Waypoint`) are changed, if only translation fields are changed or if only
the geometry has changed.. The process is as follows (see `views.document.DocumentRest._put`):

 - Using Colander a `Document` instance `document_in` is created from the JSON
   input data.
 - The current version of the document is loaded from the database.
 - The version numbers of the current document, its locales and geometry are stored
   in a dictionary `old_versions`.
 - Then the attributes of `document_in` are copied onto `document`, so that
   `document` reflects the changes that should be made.
 - `document` is flushed to the database. SQLAlchemy will automatically
   update the version numbers in `Document`, `DocumentLocale` and `DocumentGeometry`
   in case an attribute has changed. By comparing with the old version numbers, we
   can detect if only figures have changed, if only locales have changed or if only
   the geometry has changed.

Depending on the *update types* (`FIGURES`, `LANG`, `GEOM`) the following actions
are done.

**Only FIGURES**

 * Because only the figures have changed, we only insert the new document in
   `ArchiveDocument` (and `ArchiveWaypoint`). No new version is inserted in
   `ArchiveDocumentLocale`.
 * A new entry is inserted in `HistoryMetaData`.
 * For every locale a new entry is made in `DocumentVersion` referencing the
   new entry in `ArchiveDocument`, the old locale version in `ArchiveDocumentLocale`
   and also the old geometry in `ArchiveDocumentGeometry`.

**Only LANG**

 * Because only locales have changed, we only insert the changed locale(s) in
   `ArchiveDocumentLocale` (and `ArchiveWaypointLocale`). No new version is
   inserted in `ArchiveDocument`.
 * A new entry is inserted in `HistoryMetaData`.
 * For every locale that has changed and for every new locale a new entry is made
   in `DocumentVersion` referencing the old entry in `ArchiveDocument`, the old
   entry in `ArchiveDocumentGeometry` and the new locale version in `ArchiveDocumentLocale`.

**Only GEOM**

 * Because only the geometry has changed, we only insert the new geometry in
   `ArchiveDocumentGeometry`. No new version is inserted in
   `ArchiveDocumentLocale` or `ArchiveDocument`.
 * A new entry is inserted in `HistoryMetaData`.
 * For every locale a new entry is made in `DocumentVersion` referencing the
   new entry in `ArchiveDocumentGeometry`, the old locale version in `ArchiveDocumentLocale`
   and also the old entry in `ArchiveDocument`.

**GEOM xor LANG xor FIGURES**

At least two types (figures, geometry or locales) have changed.

 * The new document is inserted in `ArchiveDocument` (and `ArchiveWaypoint`),
   the locale(s) that have changed are inserted in `ArchiveDocumentLocale`
   (and `ArchiveWaypointLocale`) and if the geometry has changed a new entry
   is added to `ArchiveDocumentGeometry`.
 * A new entry is inserted in `HistoryMetaData`.
 * For every locale a new entry is made in `DocumentVersion` referencing the
   new entry in `ArchiveDocument` and the new locale version in `ArchiveDocumentLocale`
   (or the old version if that particular locale has not changed).
