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

`write_memory(notes, inbox, owner)` drops blocked notes and returns tagged
`MemoryEntry` records for `allow` and `allow_tainted` notes. Each record contains
the text, rule IDs, source sender, sender trust, and note targets. The model can
receive only their plain text. Before executing a tool call, use
`guard(tool_name, args, memory, trusted, user_text)`. Its return value compares
equal to `"allow"` or `"deny"`; a denial also has a `.reason` explaining why
the call needs user confirmation. The guard never calls a model or a network
service.
