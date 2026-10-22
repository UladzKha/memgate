# memgate

Deterministic, standard-library memory-write gate. No model or network access.

Clone alongside the pilot repository, then install with `pip install -e ../memgate`
from the pilot directory. The harness uses `memgate:Gate` as its import path.
`check_batch` links each note to a source
email and returns a `Decision` with `outcome`, ordered `rules`, `source_index`,
and integer `link_score`. Ties go to the first email; no distinctive overlap
leaves the source unset.

Exact email addresses, reference IDs, URLs, paths, and account-like numbers
take precedence when linking. N1 checks targets in the linked source, or in
the inbox if no source could be linked.
