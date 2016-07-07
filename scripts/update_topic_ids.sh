#!/bin/sh
sudo -u postgres psql -d c2corg_$USER <<EOF

CREATE EXTENSION IF NOT EXISTS dblink;

/*
-- Analyse duplicated topics

SELECT *
FROM
    dblink(
        'hostaddr=127.0.0.1 port=5433 dbname=discourse user=discourse password=discourse',
        '
        SELECT *
        FROM (
            SELECT
                id,
                title,
                category_id,
                count(id) OVER (PARTITION BY title) AS duplicate_count
            FROM topics
            WHERE deleted_at IS NULL AND category_id = 28
            ORDER BY title
        ) AS qualified_topics
        WHERE duplicate_count > 1;
        '
    )
    AS topics(
        topic_id integer,
        title text,
        category_id integer,
        duplicated_count integer
    );
*/

TRUNCATE TABLE guidebook.documents_topics;

INSERT INTO guidebook.documents_topics (
    document_locale_id,
    topic_id
)
SELECT
    documents_locales.id,
    topics.topic_id
FROM
    guidebook.documents_locales
    INNER JOIN
        -- Note that we exclude duplicated topics
        dblink(
            'hostaddr=127.0.0.1 port=5433 dbname=discourse user=discourse password=discourse',
            '
            SELECT id, title
            FROM (
                SELECT
                    id,
                    title,
                    count(id) OVER (PARTITION BY title) > 1 AS duplicated
                FROM topics
                WHERE deleted_at IS NULL AND category_id = 28
                ORDER BY title
            ) AS qualified_topics
            WHERE NOT duplicated;
            '
        )
        AS topics(
            topic_id integer,
            title text
        )
        ON topics.title = document_id || '_' || lang;
EOF
