#!/usr/bin/env bash
# Install the scan-to-vector skill into the personal skills directory of
# Claude Code and/or Codex.
#
#   ./install.sh                  # every agent found on this machine
#   ./install.sh --codex          # only Codex
#   curl -fsSL https://raw.githubusercontent.com/3351666087/scan-to-vector-skill/main/install.sh | bash
#
# Run from a checkout, it installs that checkout's skill; run on its own, it
# downloads the repository from GitHub first. An existing copy is replaced only
# when nobody has changed it since this script installed it; anything else
# needs --force, and the old copy is moved to a backup folder first.
set -euo pipefail

SKILL=scan-to-vector
REPO=${SCAN_TO_VECTOR_REPO:-3351666087/scan-to-vector-skill}
REF=${SCAN_TO_VECTOR_REF:-main}
STAMP=.scan-to-vector-install   # checksums of the installed files

usage() {
  cat <<EOF
Usage: install.sh [--claude] [--codex] [--dir DIR] [--force] [--ref REF]

Copies the $SKILL skill into:
  --claude    \${CLAUDE_CONFIG_DIR:-~/.claude}/skills   (Claude Code)
  --codex     \${CODEX_HOME:-~/.codex}/skills           (Codex)
  --dir DIR   DIR, for any other client that loads SKILL.md folders

With no target given, installs for every agent found on this machine.

  --force     replace a copy that has local changes (it is backed up first)
  --ref REF   branch or tag to download when not run from a checkout (default: $REF)
EOF
}

say()  { printf '%s\n' "$*"; }
warn() { printf 'install.sh: %s\n' "$*" >&2; }
die()  { warn "$*"; exit 2; }

want_claude=0 want_codex=0 extra_dir="" force=0
while [ $# -gt 0 ]; do
  case $1 in
    --claude) want_claude=1 ;;
    --codex)  want_codex=1 ;;
    --dir)    [ $# -ge 2 ] || die "--dir needs a directory"; extra_dir=$2; shift ;;
    --force)  force=1 ;;
    --ref)    [ $# -ge 2 ] || die "--ref needs a branch or tag"; REF=$2; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; die "unknown option: $1" ;;
  esac
  shift
done

claude_root=${CLAUDE_CONFIG_DIR:-$HOME/.claude}
codex_root=${CODEX_HOME:-$HOME/.codex}

if [ $want_claude = 0 ] && [ $want_codex = 0 ] && [ -z "$extra_dir" ]; then
  if [ -d "$claude_root" ] || command -v claude >/dev/null 2>&1; then want_claude=1; fi
  if [ -d "$codex_root" ]  || command -v codex  >/dev/null 2>&1; then want_codex=1; fi
  if [ $want_claude = 0 ] && [ $want_codex = 0 ]; then
    die "found neither Claude Code nor Codex; pass --claude, --codex or --dir DIR"
  fi
fi

tmp="" stage=""
trap 'rm -rf "$tmp" "$stage"' EXIT

# Use the checkout this script lives in, or download one.
src=""
script=${BASH_SOURCE[0]:-}
if [ -n "$script" ] && [ -f "$script" ]; then
  here=$(cd "$(dirname "$script")" && pwd)
  [ -f "$here/skills/$SKILL/SKILL.md" ] && src=$here/skills/$SKILL
fi
if [ -z "$src" ]; then
  command -v curl >/dev/null 2>&1 || die "curl is required to download the skill"
  tmp=$(mktemp -d "${TMPDIR:-/tmp}/$SKILL.XXXXXX")
  say "Downloading $REPO@$REF ..."
  curl -fsSL "https://github.com/$REPO/archive/$REF.tar.gz" | tar -xzf - -C "$tmp" \
    || die "could not download https://github.com/$REPO/archive/$REF.tar.gz"
  for d in "$tmp"/*/skills/$SKILL; do src=$d; done
  [ -f "$src/SKILL.md" ] || die "the download has no skills/$SKILL/SKILL.md"
fi

if command -v sha256sum >/dev/null 2>&1; then
  sha() { sha256sum "$1"; }
else
  sha() { shasum -a 256 "$1"; }
fi

# One "hash  ./path" line per file, in a stable order.
checksums() {
  (cd "$1" && find . -type f ! -name "$STAMP" ! -name .DS_Store ! -path '*/__pycache__/*' \
    | LC_ALL=C sort | while IFS= read -r f; do sha "$f"; done)
}

want=$(checksums "$src")
failed=0 installed=""

install_to() {  # install_to SKILLS_DIR LABEL
  local dir=$1 label=$2 dest=$1/$SKILL backup="" have
  if [ -e "$dest" ] || [ -L "$dest" ]; then
    have=""
    [ -d "$dest" ] && have=$(checksums "$dest")
    if [ "$have" = "$want" ]; then
      [ -L "$dest" ] || [ -f "$dest/$STAMP" ] || printf '%s\n' "$want" > "$dest/$STAMP"
      say "$label: already up to date ($dest)"
      installed=$dest
      return
    fi
    if [ ! -L "$dest" ] && [ -f "$dest/$STAMP" ] && [ "$have" = "$(cat "$dest/$STAMP")" ]; then
      :  # untouched since we installed it, so it is safe to replace
    elif [ $force = 1 ]; then
      backup=$(dirname "$dir")/skill-backups/$SKILL-$(date +%Y%m%d-%H%M%S)
    else
      warn "$label: $dest has local changes or was not installed by this script; left as is."
      warn "$label: re-run with --force to replace it (the old copy is backed up first)."
      failed=1
      return
    fi
  fi

  mkdir -p "$dir"
  stage=$dir/.$SKILL.tmp.$$
  rm -rf "$stage"
  cp -R "$src" "$stage"
  find "$stage" \( -name __pycache__ -o -name .DS_Store -o -name "$STAMP" \) -prune -exec rm -rf {} +
  printf '%s\n' "$want" > "$stage/$STAMP"

  if [ -n "$backup" ]; then
    mkdir -p "$(dirname "$backup")"
    mv "$dest" "$backup"
    say "$label: moved the previous copy to $backup"
  elif [ -e "$dest" ]; then
    rm -rf "$dest"
  fi
  mv "$stage" "$dest"
  stage="" installed=$dest
  say "$label: installed $SKILL to $dest"
}

[ $want_claude = 1 ] && install_to "$claude_root/skills" "Claude Code"
[ $want_codex = 1 ]  && install_to "$codex_root/skills" "Codex"
[ -n "$extra_dir" ]  && install_to "$extra_dir" "$extra_dir"

if [ -n "$installed" ] && ! python3 -c 'import pymupdf, PIL, numpy, scipy' >/dev/null 2>&1; then
  say "The skill's scripts need Python 3.10+ with PyMuPDF, Pillow, numpy and scipy:"
  say "  python3 -m pip install -r \"$installed/requirements.txt\""
fi
if [ -n "$installed" ] && ! command -v tesseract >/dev/null 2>&1; then
  say "They also need Tesseract OCR: brew install tesseract  (or: sudo apt install tesseract-ocr)"
fi
[ $failed = 0 ] && say "Start a new agent session to load the skill."
exit $failed
