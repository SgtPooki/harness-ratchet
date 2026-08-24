# slugify

`slugify(input: string): string` converts arbitrary text to a URL slug.

Specification:

1. Result contains only lowercase `a-z`, digits `0-9`, and single dashes.
2. Letters are lowercased. Accented Latin letters are transliterated to their
   base letter (é→e, ü→u, ñ→n, etc.) — use Unicode NFD normalization and strip
   combining marks.
3. Any run of characters that are not `a-z0-9` (spaces, underscores,
   punctuation, symbols, emoji) becomes a single dash.
4. No leading or trailing dashes.
5. If nothing remains after the rules above, return `"n-a"`.
