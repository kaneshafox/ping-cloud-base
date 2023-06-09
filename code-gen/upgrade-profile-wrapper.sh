#!/bin/bash

# This script is a wrapper for the upgrade-profile-repo.sh script and may be used to aid the operator in updating the
# profile repo to a target Beluga version. It abstracts away the location of the upgrade-profile-repo.sh script, which
# performs the actual profile migration to a target Beluga version. The script must be run from the root of the
# profile repo clone directory in the following manner.
#
#     NEW_VERSION=${TARGET_VERSION} ./upgrade-profile-wrapper.sh
#
# For example:
#
#     NEW_VERSION=v1.11.0 ./upgrade-profile-wrapper.sh
#
# It acts on the following environment variables:
#
#     NEW_VERSION -> Required. The new version of Beluga to which to upgrade the profile repo.
#     SUPPORTED_ENVIRONMENTS_TYPES -> An optional space-separated list of environments. Defaults to 'dev test stage prod customer-hub', if unset.
#         If provided, it must contain all or a subset of the environments currently created by the
#         generate-cluster-state.sh script, i.e. dev, test, stage, prod, customer-hub.
#     RESET_TO_DEFAULT -> An optional flag, which if set to true will reset the profile-repo to the OOTB state
#         for the new version. This has the same effect as running the platform code build job.
#
# The script is non-destructive by design and doesn't push any new state to the server. Instead, it will set up a
# parallel branch for every CDE branch corresponding to the environments specified through the SUPPORTED_ENVIRONMENTS_TYPE environment
# variable. For example, if the new version is v1.11.0, then it’ll set up 5 new branches at the new version for the
# default set of environments: v1.11.0-dev, v1.11.0-test, v1.11.0-stage, v1.11.0-master, v1.11.0-customer-hub. These new branches will be
# valid for that version for all regions for the customer’s CDEs. All profile customizations added by field teams will
# be migrated to the new branches verbatim. But changes to OOTB Beluga profiles will be overwritten. So it's up to the
# PS/GSO teams to reconcile those files. The best practice is to NOT change OOTB Beluga profile but rather add new
# files, so they'll always be preserved.

### Global variables and utility functions ###
P1AS_UPGRADES='p1as-upgrades'
UPGRADE_SCRIPT_NAME='upgrade-profile-repo.sh'
UPGRADE_DIR_NAME='upgrade-scripts'

########################################################################################################################
# Invokes pushd on the provided directory but suppresses stdout and stderr.
#
# Arguments
#   ${1} -> The directory to push.
########################################################################################################################
pushd_quiet() {
  # shellcheck disable=SC2164
  pushd "$1" >/dev/null 2>&1
}

########################################################################################################################
# Invokes popd but suppresses stdout and stderr.
########################################################################################################################
popd_quiet() {
  # shellcheck disable=SC2164
  popd >/dev/null 2>&1
}

### SCRIPT START ###

# Verify that required environment variable NEW_VERSION is set
if test -z "${NEW_VERSION}"; then
  echo '=====> NEW_VERSION environment variable must be set before invoking this script'
  exit 1
fi

PING_CLOUD_BASE_REPO_URL="${PING_CLOUD_BASE_REPO_URL:-$(git grep ^K8S_GIT_URL= | head -1 | cut -d= -f2)}"
PING_CLOUD_BASE_REPO_URL="${PING_CLOUD_BASE_REPO_URL:-https://github.com/pingidentity/${PING_CLOUD_BASE}}"

# Clone the upgrade script from p1as-upgrades repo
if ! test "${P1AS_UPGRADES_REPO}"; then
  REPO_CLONE_BASE_DIR="$(mktemp -d)"
  P1AS_UPGRADES_REPO_URL="https://gitlab.corp.pingidentity.com/ping-cloud-private-tenant/p1as-upgrades"

  # Derive the upgrade script version from NEW_VERSION env var
  UPGRADE_SCRIPT_VERSION="PDO-5409-move-upgrade-script"
  # NEW_VERSION=1.18.x.x -> UPGRADE_SCRIPT_VERSION=1.18
  # NEW_VERSION=v1.18-release-branch -> UPGRADE_SCRIPT_VERSION=v1.18-release-branch
  # NEW_VERSION=pdo-my-test -> UPGRADE_SCRIPT_VERSION=PDO-my-test or UPGRADE_SCRIPT_VERSION=v1.18-release-branch

  pushd_quiet "${REPO_CLONE_BASE_DIR}"
  echo "=====> Cloning ${P1AS_UPGRADES}@${UPGRADE_SCRIPT_VERSION} from ${P1AS_UPGRADES_REPO_URL} to '${REPO_CLONE_BASE_DIR}'"
  git clone -c advice.detachedHead=false --depth 1 --branch "${UPGRADE_SCRIPT_VERSION}" "${P1AS_UPGRADES_REPO_URL}"
  if test $? -ne 0; then
    echo "=====> Unable to clone ${P1AS_UPGRADES_REPO_URL}@${UPGRADE_SCRIPT_VERSION} from ${P1AS_UPGRADES_REPO_URL}"
    popd_quiet
    exit 1
  fi
  popd_quiet

  P1AS_UPGRADES_REPO="${REPO_CLONE_BASE_DIR}/${P1AS_UPGRADES}"
fi

UPGRADE_SCRIPT_PATH="${P1AS_UPGRADES_REPO}/${UPGRADE_DIR_NAME}/${UPGRADE_SCRIPT_NAME}"

if test -f "${UPGRADE_SCRIPT_PATH}"; then
  # Execute the upgrade script
  PING_CLOUD_BASE_REPO_URL=${PING_CLOUD_BASE_REPO_URL} "${UPGRADE_SCRIPT_PATH}"
  exit $?
else
  echo "=====> Unable to download Upgrade script version: ${UPGRADE_SCRIPT_VERSION}"
  exit 1
fi