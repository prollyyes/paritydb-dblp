WITH eligible_publications AS (
    SELECT publication_id
    FROM publication
    WHERE year BETWEEN %(year_from)s AND %(year_to)s
      AND venue_id = ANY(%(venue_ids)s)
), author_stats AS (
    SELECT
        a.person_id,
        COUNT(DISTINCT a.publication_id) AS publication_count,
        COUNT(DISTINCT co.person_id) FILTER (WHERE co.person_id <> a.person_id) AS coauthor_count
    FROM authorship AS a
    JOIN eligible_publications AS ep USING (publication_id)
    LEFT JOIN authorship AS co ON co.publication_id = a.publication_id
    GROUP BY a.person_id
)
SELECT p.person_id, p.name, s.publication_count, s.coauthor_count
FROM author_stats AS s
JOIN person AS p USING (person_id)
WHERE s.publication_count >= %(min_publications)s
ORDER BY s.publication_count DESC, s.coauthor_count DESC, p.person_id
LIMIT %(limit)s;

