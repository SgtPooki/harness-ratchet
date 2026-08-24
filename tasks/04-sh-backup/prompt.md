`backup.sh` is supposed to copy every `.log` file under the `data/` directory
(recursively) into `backup/`, flattening the directory structure and prefixing
each copied file with its last-modified date as `YYYY-MM-DD_`. It works in the
happy case but silently loses or mangles some files in real use.

Fix `backup.sh` so it handles all legal filenames. Keep it a POSIX-ish bash
script; do not rewrite it in another language. Test data is in `data/`.
