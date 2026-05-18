-- 0021_match_citation_chunks_rpc.sql
-- Stored function used by app/notices/retriever.py to do ANN against the
-- citation corpus with a topic-tag pre-filter. Lives as a function (not
-- inline supabase-py) because pgvector operators aren't exposed through
-- the postgrest query builder.

CREATE OR REPLACE FUNCTION match_citation_chunks(
  query_embedding vector(768),
  match_topic_tags text[],
  match_k int
)
RETURNS TABLE (
  id          uuid,
  source      text,
  source_ref  text,
  subsection  text,
  language    text,
  title       text,
  body        text,
  distance    float
)
LANGUAGE sql STABLE AS $$
  WITH groups AS (
    SELECT
      c.id, c.source::text, c.source_ref, c.subsection, c.language::text,
      c.title, c.body,
      (c.embedding <=> query_embedding) AS distance,
      ROW_NUMBER() OVER (
        PARTITION BY c.source, c.source_ref, c.subsection
        ORDER BY (c.embedding <=> query_embedding)
      ) AS rn_per_group
    FROM citation_corpus_chunks c
    WHERE c.topic_tags && match_topic_tags
  )
  SELECT id, source, source_ref, subsection, language, title, body, distance
  FROM (
    SELECT *,
           DENSE_RANK() OVER (ORDER BY distance) AS group_rank
    FROM groups
    WHERE rn_per_group = 1
  ) ranked
  WHERE group_rank <= match_k
  UNION ALL
  SELECT g.id, g.source, g.source_ref, g.subsection, g.language, g.title, g.body, g.distance
  FROM groups g
  JOIN (
    SELECT source, source_ref, subsection
    FROM (
      SELECT source, source_ref, subsection,
             DENSE_RANK() OVER (ORDER BY distance) AS group_rank
      FROM groups WHERE rn_per_group = 1
    ) t WHERE group_rank <= match_k
  ) top_groups USING (source, source_ref, subsection)
  WHERE g.rn_per_group > 1
  ORDER BY distance, language;
$$;

REVOKE ALL ON FUNCTION match_citation_chunks(vector, text[], int) FROM public;
GRANT EXECUTE ON FUNCTION match_citation_chunks(vector, text[], int) TO authenticated;
GRANT EXECUTE ON FUNCTION match_citation_chunks(vector, text[], int) TO service_role;
