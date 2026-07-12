WITH eligible_edges AS (
    SELECT DISTINCT
        LEAST(a1.person_id, a2.person_id) AS left_id,
        GREATEST(a1.person_id, a2.person_id) AS right_id
    FROM publication AS p
    JOIN authorship AS a1 USING (publication_id)
    JOIN authorship AS a2 ON a2.publication_id = p.publication_id
                           AND a1.person_id < a2.person_id
    WHERE p.year BETWEEN %(year_from)s AND %(year_to)s
      AND p.venue_id = ANY(%(venue_ids)s)
), neighbours AS (
    SELECT left_id AS person_id, right_id AS neighbour_id FROM eligible_edges
    UNION ALL
    SELECT right_id, left_id FROM eligible_edges
), candidates AS (
    SELECT second.neighbour_id AS candidate_id,
           COUNT(DISTINCT first.neighbour_id) AS mutual_coauthor_count
    FROM neighbours AS first
    JOIN neighbours AS second ON second.person_id = first.neighbour_id
    WHERE first.person_id = %(source_id)s
      AND second.neighbour_id <> %(source_id)s
      AND NOT EXISTS (
          SELECT 1 FROM neighbours AS direct
          WHERE direct.person_id = %(source_id)s
            AND direct.neighbour_id = second.neighbour_id
      )
    GROUP BY second.neighbour_id
)
SELECT p.person_id AS candidate_id, p.name, c.mutual_coauthor_count
FROM candidates AS c
JOIN person AS p ON p.person_id = c.candidate_id
WHERE c.mutual_coauthor_count >= %(min_mutuals)s
ORDER BY c.mutual_coauthor_count DESC, p.person_id
LIMIT %(limit)s;

