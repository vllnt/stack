#!/usr/bin/env bash
#
# privacy-denylist.sh — fail when a tracked file matches a denylist pattern
# outside the allowlist.
#
# Patterns (extended regex, one per line, '#' comments; matched case-insensitively):
#   .privacy-denylist          required, tracked, structural patterns only
#   .privacy-denylist.local    optional, untracked, for names that must stay private
#   $PRIVACY_DENYLIST_EXTRA    optional, newline-separated; set it from a CI secret
# Allowlist (.privacy-allowlist): regexes matched against "path:line:token" for each
# matched token, so an allowed token never hides another match on the same line.
#
# Matched content and pattern text are never printed: CI logs of a public
# repository are public.
#
# Limits: only tracked files at the checked-out revision are scanned, not the
# commits of a pull request (gitleaks covers secret-shaped data in all history).
# UTF-16 text is not matched, and the allowlist file itself is not scanned.
#
# Exit codes: 0 clean, 1 match found, 2 misuse or invalid pattern.

set -u

cd "$(git rev-parse --show-toplevel)" || exit 2

DENY=.privacy-denylist
ALLOW=.privacy-allowlist
SELF=scripts/privacy-denylist.sh

tracked="$(mktemp)"
extra="$(mktemp)"
patterns="$(mktemp)"
allow_patterns="$(mktemp)"
hits="$(mktemp)"
kept="$(mktemp)"
probe_dir="$(mktemp -d)"
trap 'rm -rf "$tracked" "$extra" "$patterns" "$allow_patterns" "$hits" "$kept" "$probe_dir"' EXIT
printf '\n' > "$probe_dir/empty.txt"
printf 'a b\n' > "$probe_dir/text.txt"

strip() { sed -E '/^[[:space:]]*(#|$)/d'; }
# lines <file>: the file with a guaranteed final newline.
lines() { cat "$1"; printf '\n'; }

# rx <engine> <flags> <pattern> <probe file>: run one pattern through the engine
# that will use it. git grep -E (POSIX regcomp) rejects PCRE syntax such as
# (?i), (?:...) and lookarounds that GNU grep -E accepts, so denylist patterns
# are validated with git grep itself; allowlist patterns run under GNU grep.
rx() {
  local engine="$1" flags="$2" pattern="$3" probe="$4"
  if [[ "$engine" == git ]]; then
    git -C "$probe_dir" grep --no-index "-${flags}E" -e "$pattern" -- "$probe" 2> /dev/null
  else
    grep "-${flags}E" -e "$pattern" "$probe_dir/$probe" 2> /dev/null
  fi
}

# valid_regexes <file> <label> <engine>: every line must compile and must not match
# the empty string. Reports every bad pattern by index so one run finds them all.
valid_regexes() {
  local file="$1" label="$2" engine="$3" n=0 bad=0 line status probe
  while IFS= read -r line || [[ -n "$line" ]]; do
    n=$((n + 1))
    rx "$engine" q "$line" empty.txt > /dev/null
    status=$?
    if (( status > 1 )); then
      echo "error: $label pattern #$n is not a valid regex" >&2
      bad=1
      continue
    fi
    if (( status == 0 )); then
      echo "error: $label pattern #$n matches the empty string" >&2
      bad=1
      continue
    fi
    # Zero-width patterns (\b, ^, $) match inside real text but report nothing.
    probe="$(rx "$engine" o "$line" text.txt)"
    if [[ -z "$probe" ]] && rx "$engine" q "$line" text.txt > /dev/null; then
      echo "error: $label pattern #$n is zero-width" >&2
      bad=1
    fi
  done < "$file"
  return "$bad"
}

if [[ ! -f "$DENY" ]]; then
  echo "error: $DENY is required" >&2
  exit 2
fi
lines "$DENY" | strip > "$tracked"
{
  [[ -f "$DENY.local" ]] && lines "$DENY.local"
  [[ -n "${PRIVACY_DENYLIST_EXTRA:-}" ]] && printf '%s\n' "$PRIVACY_DENYLIST_EXTRA"
} | strip > "$extra"
cat "$tracked" "$extra" > "$patterns"
[[ -f "$ALLOW" ]] && lines "$ALLOW" | strip > "$allow_patterns"

if [[ ! -s "$tracked" ]]; then
  echo "error: $DENY has no patterns" >&2
  exit 2
fi
valid_regexes "$patterns" "denylist" git || exit 2
valid_regexes "$allow_patterns" "allowlist" grep || exit 2
if [[ -s "$allow_patterns" ]] && [[ -z "$(printf '%s\n' 'zz/canary.md:1:canary.ts''.net' | grep -avEf "$allow_patterns")" ]]; then
  echo "error: allowlist is too broad; it would hide an obvious match" >&2
  exit 2
fi

# -a scans binary files as text; -o reports each matched token on its own line.
git grep -naoiE -f "$patterns" -- . ":(exclude)$DENY" ":(exclude)$ALLOW" ":(exclude)$SELF" > "$hits" 2> /dev/null
status=$?
if (( status > 1 )); then
  echo "error: git grep failed" >&2
  exit 2
fi

if [[ -s "$allow_patterns" ]]; then
  grep -avEf "$allow_patterns" "$hits" > "$kept"
  status=$?
  if (( status > 1 )); then
    echo "error: allowlist filtering failed" >&2
    exit 2
  fi
  mv "$kept" "$hits"
fi

if [[ -s "$hits" ]]; then
  echo "FAIL privacy denylist: $(wc -l < "$hits" | tr -d ' ') match(es); content withheld"
  cut -d: -f1,2 "$hits" | sort -u | sed 's/^/  /'
  exit 1
fi

extra_count="$(wc -l < "$extra" | tr -d ' ')"
if [[ "${CI:-}" == "true" && "$extra_count" == "0" ]]; then
  echo "::warning title=Privacy guard::No private patterns loaded; only the tracked structural patterns were checked."
fi
echo "OK    privacy denylist: no matches ($(wc -l < "$tracked" | tr -d ' ') tracked + $extra_count private patterns)"
