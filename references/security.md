# Review content before public publication

For researched or data-driven work, make sources, access dates or immutable revisions, method, assumptions, and limitations visible in the document. Every number must be traceable or explicitly labeled synthetic/illustrative. Separate measured results from interpretation and unfinished verification. A screenshot alone does not establish correct interaction behavior.

Review all files for secrets, personal information that is not authorized for publication, work/employer confidentiality, and rights to distribute third-party assets. Inspect image/PDF metadata when those formats may contain location, author, or other private information. Use only the user's authorized public content. The publisher's scan does not establish publication rights or privacy.

Authorization applies to the task's intended content and destination. Continue within that scope without repeated confirmation. Clarify when new content or a changed destination falls outside that authorization. Do not turn routine authoring revisions into a new approval gate.

The checker catches common local references, filename case, duplicate IDs, broken HTML fragments, missing language/viewport/title/alt, and selected credential formats. It uses HTMLParser and a small CSS-reference collector. It does not execute JavaScript, discover runtime-built URLs, fully parse CSS/srcset, inspect image/PDF metadata, recognize arbitrary personal data, or prove content safe. Browser verification remains necessary for dynamic interactions.

If a secret reached public Git history, rotate/revoke it. Deleting the file is insufficient. See SECURITY.md for reporting guidance.

The checker treats each publication input as a self-contained document root. A relative link escaping that root is refused; use an absolute public URL to link another published document. This avoids resolving a staged link against an unavailable or unrelated site checkout.
