/** Convert text to a URL slug. See README.md for the full specification. */
export function slugify(input) {
  return input
    .toLowerCase()
    .replace(/\s+/g, "-")
    .replace(/[^a-z0-9-]/g, "");
}
