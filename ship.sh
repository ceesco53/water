#!/usr/bin/env bash
# Commit, push, let CI build the image, then roll the cluster onto that exact build.
#
#   ./ship.sh "Commit message"   commit every change (respecting .gitignore), then ship
#   ./ship.sh                    ship what's already committed
#
# CI (.github/workflows/build-push.yml) builds every push to main and tags the
# image with the commit SHA. Deploying that tag means what runs is exactly
# what's on GitHub, built once. deploy.sh still builds locally -- use it as the
# fallback when CI is down.
set -euo pipefail
cd "$(dirname "$0")"

REPO="ceesco53/water"
IMAGE="ghcr.io/ceesco53/water"
NAMESPACE="water"
WORKFLOW="build-push.yml"
SITE="https://water.ingress.realmclick.com"

branch="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$branch" != "main" ]]; then
  echo "ERROR: on '$branch' -- CI only builds main."
  exit 1
fi

# ── Commit ───────────────────────────────────────────────────────────────────
if [[ $# -gt 0 ]]; then
  git add -A
  if git diff --cached --quiet; then
    echo "→ Nothing to commit"
  else
    echo "→ Committing:"
    git diff --cached --stat
    git commit -q -m "$1"
  fi
elif [[ -n "$(git status --porcelain)" ]]; then
  echo "ERROR: uncommitted changes -- pass a commit message to include them, or stash them:"
  git status --short
  exit 1
fi

sha="$(git rev-parse HEAD)"

# ── Push ─────────────────────────────────────────────────────────────────────
# The SSH key on this machine is a deploy key for another repo (read-only
# here), so push over HTTPS with the gh CLI's login instead.
echo ""
echo "→ Pushing ${sha:0:7} to $REPO"
git -c credential.helper= -c 'credential.https://github.com.helper=!gh auth git-credential' \
  push "https://github.com/$REPO.git" HEAD:main
git fetch -q origin

# ── Wait for CI ──────────────────────────────────────────────────────────────
echo ""
echo "→ Waiting for CI to pick up ${sha:0:7}"
run_id=""
for _ in $(seq 1 30); do
  run_id="$(gh run list -R "$REPO" --workflow "$WORKFLOW" --commit "$sha" --limit 1 \
    --json databaseId -q '.[0].databaseId' 2>/dev/null || true)"
  [[ -n "$run_id" ]] && break
  sleep 2
done
if [[ -z "$run_id" ]]; then
  echo "ERROR: no CI run for ${sha:0:7} after 60s -- check $WORKFLOW, or deploy locally with ./deploy.sh"
  exit 1
fi

# Re-shipping a commit whose build already failed (e.g. after fixing a secret)
conclusion="$(gh run view "$run_id" -R "$REPO" --json conclusion -q .conclusion)"
if [[ "$conclusion" == "failure" || "$conclusion" == "cancelled" ]]; then
  echo "→ Last build of ${sha:0:7} $conclusion -- rerunning"
  gh run rerun "$run_id" -R "$REPO"
  sleep 5
fi

echo "→ Watching CI run $run_id"
if ! gh run watch "$run_id" -R "$REPO" --exit-status; then
  echo "ERROR: CI failed -- see: gh run view $run_id -R $REPO --log-failed"
  exit 1
fi

# ── Deploy ───────────────────────────────────────────────────────────────────
echo ""
echo "→ Deploying $IMAGE:${sha:0:7}"
# Apply the manifests too, so changes to k8s/ ship with the code -- with the
# deployment's image pinned to this commit's build instead of :latest.
kubectl apply -f k8s/namespace.yaml -f k8s/pvc.yaml -f k8s/service.yaml -f k8s/ingress.yaml
sed "s|image: $IMAGE:latest|image: $IMAGE:$sha|" k8s/deployment.yaml | kubectl apply -f -
kubectl rollout status deployment/water -n "$NAMESPACE" --timeout=180s

if curl -fsS --max-time 30 "$SITE/api/health" >/dev/null; then
  echo ""
  echo "✓ Shipped ${sha:0:7} — $SITE"
else
  echo "ERROR: rolled out, but $SITE/api/health isn't responding"
  exit 1
fi
