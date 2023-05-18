#!/usr/bin/env python3

# **********************************************************************************************************************
# This script is for sealing secrets in the new microservice Helm apps format in the Cluster-State-Repo
#   Note: This script does not work on the 'k8s-configs' directory, it is intended for the new microservice apps
#         that will be using Helm.
#
# Usage: python3 seal.py <CERT_FILE>
# **********************************************************************************************************************

import ruamel.yaml
import sys
import subprocess
import base64 as b64

yaml = ruamel.yaml.YAML()
yaml.preserve_quotes = True

# constants
GLOBAL_KEY = "global"
SECRETS_KEY = "secrets"
SEALED_SECRETS_VAR = "sealedSecrets"


class SealSecrets:

    def __init__(self, cert: str, values_file: str = "values.yaml"):
        self.cert = cert
        self.values_file = values_file
        self.values = self.load_values()

    def load_values(self) -> dict:
        """
        Loads values.yaml file into dictionary object

        :return: The values as a dictionary
        """
        try:
            with open(self.values_file, "r") as values_file:
                values = yaml.load(values_file)
                print("Values file '%s' loaded" % self.values_file)
            return values
        except FileNotFoundError:
            print("Values file '%s' not found" % self.values_file)
            exit(1)

    def write_new_values(self):
        """
        Overwrites values.yaml file with yaml object with updated secret values
        """
        with open(self.values_file, "w") as values_file:
            try:
                yaml.dump(self.values, values_file)
            except Exception as e:
                print("Unable to write new values file '%s'" % self.values_file)
                print(e)

    def seal_secrets(self):
        """
        Seals all secrets in the values.yaml file's .Values.global.secrets object
        values.yaml format expected:
        secrets:
          NAMESPACE:
            SECRETNAME:
              KEY: VALUE
        """

        # Check that secrets exist
        if not self.values[GLOBAL_KEY][SECRETS_KEY]:
            print("No secrets found to seal")
            exit(0)

        print("Using certificate file '%s' for encrypting secrets" % self.cert)

        # Loop through the secrets
        for k8s_namespace in self.values[GLOBAL_KEY][SECRETS_KEY]:
            for k8s_secret in self.values[GLOBAL_KEY][SECRETS_KEY][k8s_namespace]:
                for key in self.values[GLOBAL_KEY][SECRETS_KEY][k8s_namespace][k8s_secret]:
                    # Get the value
                    value = self.values[GLOBAL_KEY][SECRETS_KEY][k8s_namespace][k8s_secret][key]
                    if value is not None:
                        print("Sealing secret '%s, %s, %s'" % (k8s_namespace, k8s_secret, key))

                        # Run seal secret command to get the sealed value
                        p1 = subprocess.Popen(["echo", "-n", b64.b64decode(value.encode("ascii")).decode("ascii")],
                                              stdout=subprocess.PIPE)
                        p2 = subprocess.Popen(["kubeseal", "--cert", self.cert, "--raw", "--namespace", k8s_namespace,
                                               "--name", k8s_secret], stdin=p1.stdout, stdout=subprocess.PIPE,
                                              stderr=subprocess.PIPE)

                        # Check if sealing the secret failed
                        if p2.wait() != 0:
                            print(str(p2.stderr.readline(), 'utf-8'))
                            raise Exception("Error sealing secret. See output above.")

                        sealed_value = str(p2.stdout.readline(), 'utf-8')

                        # Update yaml with sealed value
                        self.values[GLOBAL_KEY][SECRETS_KEY][k8s_namespace][k8s_secret][key] = sealed_value

        # Update sealedSecrets variable to true
        self.values[GLOBAL_KEY][SEALED_SECRETS_VAR] = True

        # Write new values.yaml file
        self.write_new_values()


if __name__ == "__main__":
    cert_file = sys.argv[1]
    seal = SealSecrets(cert_file)
    seal.seal_secrets()
