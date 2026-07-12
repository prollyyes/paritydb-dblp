WITH RECURSIVE area_closure AS (
    SELECT area_id FROM area WHERE area_id = %(ancestor_area)s
    UNION ALL
    SELECT child.area_id
    FROM area AS child
    JOIN area_closure AS parent ON child.parent_area_id = parent.area_id
), author_areas AS (
    SELECT
        au.person_id,
        COUNT(DISTINCT va.area_id) AS area_count,
        COUNT(DISTINCT p.publication_id) AS publication_count
    FROM area_closure AS ac
    JOIN venue_area AS va USING (area_id)
    JOIN publication AS p USING (venue_id)
    JOIN authorship AS au USING (publication_id)
    WHERE p.year BETWEEN %(year_from)s AND %(year_to)s
    GROUP BY au.person_id
)
SELECT p.person_id, p.name, a.area_count, a.publication_count
FROM author_areas AS a
JOIN person AS p USING (person_id)
WHERE a.area_count >= %(min_distinct_areas)s
ORDER BY a.area_count DESC, a.publication_count DESC, p.person_id;

