SELECT
    p.venue_id,
    CASE
        WHEN %(bucket)s = 'decade' THEN (p.year / 10) * 10
        ELSE p.year
    END AS bucket_start,
    COUNT(DISTINCT p.publication_id) AS publication_count
FROM publication AS p
WHERE p.year BETWEEN %(year_from)s AND %(year_to)s
  AND p.venue_id = ANY(%(venue_ids)s)
GROUP BY p.venue_id, bucket_start
ORDER BY bucket_start, p.venue_id;

