#!/usr/bin/env bash
# Record what the preprod and the production run as GitHub Deployments.
#
# This script only OBSERVES: it reads the public /health endpoint of an
# environment and records the commit it reports as a GitHub Deployment, with
# the workflow's own GITHUB_TOKEN. It never deploys anything and needs no
# credential of the infrastructure (see c2corg/v6-docker-compose#163).
#
# Usage:
#   deployments.sh observe <environment> <health url> <environment url>
#       Record a Deployment when the live commit differs from the latest
#       one recorded for that environment.
#   deployments.sh wait <environment> <health url> <environment url> <sha> <minutes>
#       After a green CI on master: wait until the environment runs <sha>
#       (or a descendant), then record it. If it never shows up, record an
#       `error` status for <sha>. Does not wait when the environment
#       currently runs a commit that is not on master (a PR preview).
#   deployments.sh release-note <sha>
#       If <sha> is the commit of one of the latest releases, append once
#       "Deployed to production on <date>" to its notes.
#
# Environment: GH_TOKEN (for gh), GITHUB_REPOSITORY (owner/repo).
# Optional: DRY_RUN=1 prints the write calls instead of sending them;
# GITHUB_OUTPUT receives `recorded` and `sha`; RUN_URL is the log link.
set -euo pipefail

REPO=${GITHUB_REPOSITORY:?GITHUB_REPOSITORY must be set (owner/repo)}
DEFAULT_BRANCH=${DEFAULT_BRANCH:-master}
POLL_SECONDS=${POLL_SECONDS:-60}
RELEASE_MARKER="Deployed to production on"

warn() { echo "::warning::$*" >&2; }
note() { echo "::notice::$*" >&2; }

output() {
  echo "$1=$2"
  if [[ -n ${GITHUB_OUTPUT:-} ]]; then echo "$1=$2" >>"$GITHUB_OUTPUT"; fi
}

# Write calls (POST/PATCH) go through here, so DRY_RUN can show them
# without changing anything on GitHub.
write_api() {
  if [[ -n ${DRY_RUN:-} ]]; then
    echo "DRY_RUN: gh api $*" >&2
    if [[ " $* " == *" --input - "* ]]; then jq -c . >&2; fi
    echo 0 # a fake id
  else
    gh api "$@"
  fi
}

# Print "<sha> <describe>" from a /health endpoint, or fail. `describe`
# (v6_api#2754) is optional: it is empty when the endpoint does not have it.
read_health() {
  local json sha describe
  json=$(curl --fail --silent --show-error --location --max-time 20 \
    --retry 2 --retry-delay 5 "$1") || return 1
  sha=$(jq -r '.version // empty' <<<"$json") || return 1
  if [[ ! $sha =~ ^[0-9a-f]{40}$ ]]; then
    warn "$1 reports no commit sha as version (got '${sha:0:50}')"
    return 1
  fi
  # Keep it short and printable: it ends up in a status description.
  describe=$(jq -r '.describe // empty' <<<"$json" | tr -cd '[:alnum:]._/+-' | cut -c1-60)
  echo "$sha $describe"
}

# The sha of the latest Deployment recorded for an environment (empty if none).
latest_recorded() {
  gh api "repos/$REPO/deployments?environment=$1&per_page=1" --jq '.[0].sha // empty'
}

# Is <sha> reachable from the default branch?
on_default_branch() {
  local status
  status=$(gh api "repos/$REPO/compare/$DEFAULT_BRANCH...$1" --jq .status) || return 1
  [[ $status == identical || $status == behind ]]
}

# Is <descendant> equal to, or newer than, <ancestor>?
contains() {
  local status
  status=$(gh api "repos/$REPO/compare/$1...$2" --jq .status 2>/dev/null) || return 1
  [[ $status == identical || $status == ahead ]]
}

# "#N (branch)" for the pull request a commit comes from, open ones first.
pull_request_of() {
  gh api "repos/$REPO/commits/$1/pulls" \
    --jq 'sort_by(.state != "open") | .[0] // empty | "#\(.number) (\(.head.ref))"'
}

# A release tag pointing at <sha>, among the latest tags.
tag_at() {
  gh api "repos/$REPO/tags?per_page=30" --jq "[.[] | select(.commit.sha == \"$1\") | .name][0] // empty"
}

# The status description: what runs, and whether it comes from master.
describe_commit() {
  local sha=$1 describe=$2 label pr
  label=${describe:-$(tag_at "$sha")}
  label=${label:-${sha:0:7}}
  if on_default_branch "$sha"; then
    echo "$label ($DEFAULT_BRANCH)"
  else
    pr=$(pull_request_of "$sha")
    echo "$label: preview of ${pr:-a branch}, $DEFAULT_BRANCH is not deployed"
  fi
}

# Create a Deployment of <sha> on <environment> and give it a status.
record() {
  local environment=$1 env_url=$2 sha=$3 state=$4 description=$5 id production=false
  [[ $environment == production ]] && production=true
  description=${description:0:140} # GitHub's limit for status descriptions
  # required_contexts must be an empty JSON array, which -f/-F cannot send.
  id=$(jq -n --arg ref "$sha" --arg environment "$environment" \
    --arg description "$description" --argjson production "$production" \
    '{ref: $ref, environment: $environment, description: $description,
      auto_merge: false, required_contexts: [],
      production_environment: $production, transient_environment: false}' |
    write_api "repos/$REPO/deployments" --input - --jq .id) || {
    # e.g. a commit GitHub does not know (from a fork's branch)
    warn "could not create a deployment of $sha on $environment"
    return 1
  }
  write_api "repos/$REPO/deployments/$id/statuses" \
    -f state="$state" -f description="$description" -f environment_url="$env_url" \
    -f log_url="${RUN_URL:-}" -F auto_inactive=true --silent
  note "$environment: recorded $sha ($state): $description"
}

cmd_observe() {
  local environment=$1 health_url=$2 env_url=$3 live sha describe
  output recorded false
  if ! live=$(read_health "$health_url"); then
    # The infrastructure's own alerts cover outages: only a warning here.
    warn "$environment: cannot read $health_url, nothing recorded"
    return 0
  fi
  read -r sha describe <<<"$live"
  output sha "$sha"
  if [[ $(latest_recorded "$environment") == "$sha" ]]; then
    echo "$environment still runs $sha, already recorded"
    return 0
  fi
  record "$environment" "$env_url" "$sha" success "$(describe_commit "$sha" "$describe")" || return 0
  output recorded true
}

cmd_wait() {
  local environment=$1 health_url=$2 env_url=$3 target=$4 minutes=$5 live sha deadline
  deadline=$(($(date +%s) + minutes * 60))
  if live=$(read_health "$health_url"); then
    read -r sha _ <<<"$live"
    if [[ $sha != "$target" ]] && ! on_default_branch "$sha"; then
      # The environment follows a PR branch, not master: it will not pick
      # up this commit, which is not a failure. Record what it runs instead.
      note "$environment previews $sha, not $DEFAULT_BRANCH: not waiting for $target"
      cmd_observe "$environment" "$health_url" "$env_url"
      return 0
    fi
  fi
  while :; do
    if live=$(read_health "$health_url"); then
      read -r sha _ <<<"$live"
      # A newer commit may have overtaken this one: that's fine too.
      if [[ $sha == "$target" ]] || contains "$target" "$sha"; then
        cmd_observe "$environment" "$health_url" "$env_url"
        return 0
      fi
    fi
    if (($(date +%s) >= deadline)); then break; fi
    sleep "$POLL_SECONDS"
  done
  # GitHub only sees the symptom; the cause stays in the VM's journal and alerts.
  record "$environment" "$env_url" "$target" error \
    "not live on $environment after $minutes min (paused, or deployment failed: see the alerts)" || true
  output recorded true
  output sha "$target"
  echo "::error::$target is not live on $environment after $minutes min" >&2
  return 1
}

cmd_release_note() {
  local sha=$1 tag commit id body
  # Only the latest releases: an older one being in production again is a
  # rollback, and its notes already say when it was first deployed.
  for tag in $(gh api "repos/$REPO/releases?per_page=5" --jq '.[] | select(.draft | not) | .tag_name'); do
    commit=$(gh api "repos/$REPO/commits/$tag" --jq .sha)
    [[ $commit == "$sha" ]] || continue
    id=$(gh api "repos/$REPO/releases/tags/$tag" --jq .id)
    body=$(gh api "repos/$REPO/releases/$id" --jq '.body // ""')
    if [[ $body == *"$RELEASE_MARKER"* ]]; then
      echo "release $tag already says when it was deployed"
      return 0
    fi
    write_api -X PATCH "repos/$REPO/releases/$id" --silent \
      -f body="$body"$'\n\n'"$RELEASE_MARKER $(date -u +%Y-%m-%d)."
    note "release $tag: noted the production deployment"
    return 0
  done
  echo "$sha is not the commit of one of the latest releases"
}

case ${1:-} in
observe) shift && cmd_observe "$@" ;;
wait) shift && cmd_wait "$@" ;;
release-note) shift && cmd_release_note "$@" ;;
*)
  sed -n '2,/^set /p' "$0" | sed '$d; s/^# \{0,1\}//' >&2
  exit 2
  ;;
esac
