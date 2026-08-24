#!/bin/bash
# Copy all .log files under data/ into backup/, flattened, prefixed with
# their last-modified date as YYYY-MM-DD_.
set -e

mkdir -p backup

for f in $(find data -name '*.log'); do
  mtime=$(stat -f %Sm -t %Y-%m-%d $f 2>/dev/null || stat -c %y $f | cut -d' ' -f1)
  base=$(basename $f)
  cp $f backup/${mtime}_${base}
done

echo "backed up $(ls backup | wc -l | tr -d ' ') files"
