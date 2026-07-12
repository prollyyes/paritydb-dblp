WITH RECURSIVE eligible_edges AS (
    SELECT DISTINCT
        LEAST(a1.person_id, a2.person_id) AS left_id,
        GREATEST(a1.person_id, a2.person_id) AS right_id
    FROM publication AS p
    JOIN authorship AS a1 USING (publication_id)
    JOIN authorship AS a2 ON a2.publication_id = p.publication_id
                           AND a1.person_id < a2.person_id
    WHERE p.year BETWEEN %(year_from)s AND %(year_to)s
      AND p.venue_id = ANY(%(venue_ids)s)
), paths(current_id, distance, visited) AS (
    SELECT %(source_id)s::TEXT, 0, ARRAY[%(source_id)s::TEXT]
    UNION ALL
    SELECT
        CASE WHEN e.left_id = p.current_id THEN e.right_id ELSE e.left_id END,
        p.distance + 1,
        p.visited || CASE WHEN e.left_id = p.current_id THEN e.right_id ELSE e.left_id END
    FROM paths AS p
    JOIN eligible_edges AS e ON e.left_id = p.current_id OR e.right_id = p.current_id
    WHERE p.distance < %(max_depth)s
      AND NOT (CASE WHEN e.left_id = p.current_id THEN e.right_id ELSE e.left_id END = ANY(p.visited))
)
SELECT %(source_id)s::TEXT AS source_id,
       %(target_id)s::TEXT AS target_id,
       MIN(distance) AS distance
FROM paths
WHERE current_id = %(target_id)s
HAVING MIN(distance) IS NOT NULL;

