Both `signup.py` and `mailer.py` contain their own private copy of email
normalization logic, and the two copies have drifted apart, causing duplicate
accounts.

Refactor: create a single `normalize_email` function in a new `emailutil.py`
module and make BOTH `signup.py` and `mailer.py` use it. The correct behavior:
strip surrounding whitespace, lowercase the ENTIRE address. Nothing else — no
gmail-dot games, no plus-tag stripping.

Constraints: the public functions `register(email)` and `send_receipt(email)`
must keep their names and signatures, and neither `signup.py` nor `mailer.py`
may contain its own normalization implementation afterwards (they must import
the shared one).
