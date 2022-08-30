#!/bin/bash
set -e

test "${VERBOSE}" && set -x

# Source common environment variables
SCRIPT_HOME=$(cd $(dirname ${0}); pwd)
. ${SCRIPT_HOME}/../common.sh

configure_aws
configure_kube

pushd "${PROJECT_DIR}"

NEW_RELIC_LICENSE_KEY="${NEW_RELIC_LICENSE_KEY:-ssm://pcpt/sre/new-relic/java-agent-license-key}"
if [[ ${NEW_RELIC_LICENSE_KEY} == "ssm://"* ]]; then
  if ! ssm_value=$(get_ssm_value "${NEW_RELIC_LICENSE_KEY#ssm:/}"); then
    echo "Warn: ${ssm_value}"
    echo "Setting NEW_RELIC_LICENSE_KEY to unused"
    NEW_RELIC_LICENSE_KEY="unused"
  else
    NEW_RELIC_LICENSE_KEY="${ssm_value}"
  fi
fi

export NEW_RELIC_LICENSE_KEY_BASE64=$(base64_no_newlines "${NEW_RELIC_LICENSE_KEY}")
export DATASYNC_P1AS_SYNC_SERVER="pingdirectory-0"

# Deploy the configuration to Kubernetes
if [[ -n ${PINGONE} ]]; then
  set_pingone_api_env_vars
  pip3 install -r ${PROJECT_DIR}/ci-scripts/deploy/ping-one/requirements.txt
  log "Deleting P1 Environment if it already exists"
  python3 ${PROJECT_DIR}/ci-scripts/deploy/ping-one/p1_env_setup_and_teardown.py Teardown 2>/dev/null || true
  log "Creating P1 Environment"
  python3 ${PROJECT_DIR}/ci-scripts/deploy/ping-one/p1_env_setup_and_teardown.py Setup
fi

deploy_file=/tmp/deploy.yaml

# First, we need to deploy cert-manager. This is due to it using Dynamic Admission Control - Mutating Webhooks which
# must be available before we make use cert-manager
kubectl apply -f "${PROJECT_DIR}/k8s-configs/cluster-tools/base/cert-manager/base/cert-manager.yaml"

# Build file while cert-manager webhook service coming up to save time
build_dev_deploy_file "${deploy_file}"

# Wait until the webhook deployment is fully available
wait_for_rollout "deployment/cert-manager-webhook" "cert-manager" "20"

kubectl apply -f "${deploy_file}"

check_if_ready "${PING_CLOUD_NAMESPACE}"

popd  > /dev/null 2>&1
