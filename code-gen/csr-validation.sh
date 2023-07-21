#!/bin/bash

#**********************************************************************************************************************
# This script is for validating the new microservice Helm apps in the Cluster-State-Repo
#   Note: This script does not work on the 'k8s-configs' directory, it is intended for the new microservice apps
#         that will be using Helm.
#**********************************************************************************************************************

########################################################################################################################
# Pulls all helm charts in the provided directory, so that kustomize runs with locally pulled chart
# This is the workaround for https://github.com/kubernetes-sigs/kustomize/issues/4381
#
# Arguments
#   ${1} -> The directory that contains the helm chart(s) definition.
########################################################################################################################
pull_helm_charts() {
  local app_dir="${1}"

  # make the charts dir if it doesn't exist
  local chart_dir="${app_dir}/charts"
  mkdir -p "${chart_dir}"

  # find all files with "helmCharts" definitions and loop through them
  chart_files=$(grep -Rl "helmCharts:" "${app_dir}")
  for chart_file in ${chart_files}; do
    # determine the number of chart definitions in the kustomization.yaml file
    num_charts=$(yq ".helmCharts | length" "${chart_file}")

    # loop through chart definitions in the file
    for (( i=1; i<=num_charts; i++ ))
    do
      # use yq to get the chart's information (repo, version)
      chart_version="$(index="${i}" yq ".helmCharts[${index}].version" "${chart_file}")"
      chart_repo="$(index="${i}" yq ".helmCharts[${index}].repo" "${chart_file}")"

      # pull the chart
      helm pull --untar --untardir "${chart_dir}" "${chart_repo}" --version "${chart_version}"
    done
  done
}

########################################################################################################################
# Removes "charts" directories
########################################################################################################################
cleanup_charts() {
  # find & delete all "charts" directories
  find . -type d -name "charts" -exec rm -rf {} +
}


#### SCRIPT START ####

# if VERBOSE is true, then output line-by-line execution
"${VERBOSE:-false}" && set -x

failures_list=""
RED="\033[0;31m"
NO_COLOR="\033[0m"

# delete any "charts" directories that exist from previous runs to force helm to pull new charts
cleanup_charts

# find all the apps in the CSR directory except k8s-configs, values-files, hidden ('.'), or base directories
app_region_paths=$(find . -type d -depth 2 ! -path './k8s-configs*' ! -path './values-files*' ! -path './.*' ! -path './*/base')
echo "Validating the following app paths:"
echo "${app_region_paths}"

# validate kustomize build succeeds for each app
for app_path in ${app_region_paths}; do
  # pull the helm charts
  pull_helm_charts "${app_path}"

  # kustomize build
  result=$( (kustomize build --load-restrictor LoadRestrictionsNone --enable-helm "${app_path}") 2>&1)
  # if kustomize build fails: add to failure list and output the error
  if test $? -ne 0; then
    failures_list="${failures_list}kustomize build: ${app_path}\n"
    # Use printf to print in color
    printf "\n${RED}+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++\n"
    printf "Kustomize build validation for \"${app_path}\" failed with the below error:\n"
    printf "${result}\n"
    printf "+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++${NO_COLOR}\n\n"
  fi
done

# delete the "charts" directories created from the test
cleanup_charts

# if there are failures fail the script overall
if [[ ${failures_list} != "" ]] ; then
  echo "The following validation checks failed! Please check above error output & fix!"
  printf "${failures_list}"
  exit 1
fi

echo ""
echo "All validations passed!"
