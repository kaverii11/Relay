#!/bin/sh
# Run before uploading to Drive. Fails if a Groq key or an Authorization header
# appears anywhere in the submission (logs, raw files, CSVs, code).
cd "$(dirname "$0")/.." || exit 1
hits=$(grep -rIl --exclude-dir=.venv --exclude-dir=.git --exclude=.env --exclude=check_secrets.sh \
       -e 'gsk_[A-Za-z0-9]\{20,\}' -e 'org_[0-9a-z]\{20,\}' -e 'Bearer [A-Za-z0-9_]\{20,\}' -e '"authorization"' . )
if [ -n "$hits" ]; then echo "SECRET-LIKE STRINGS FOUND IN:"; echo "$hits"; exit 1; fi
echo "clean: no gsk_ / Groq org ids / Bearer tokens / authorization headers"
