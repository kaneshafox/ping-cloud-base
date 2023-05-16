import ruamel.yaml
import sys
import subprocess
import inquirer

yaml = ruamel.yaml.YAML()
yaml.preserve_quotes = True

# constants
SECRETS_KEY = "secrets"


class SealSecrets:

    def __init__(self, cert: str, overwrite_values: bool, values_file: str = "values.yaml"):
        self.cert = cert
        self.overwrite_values = overwrite_values
        self.values_file = values_file
        self.values = self.load_values()

    def load_values(self) -> dict:
        """
        :return: dict of values.yaml.
        :raise: Exception if values.yaml file is not found.
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
        :raise: Exception if cannot write to file_path.
        """
        if self.overwrite_values:
            file_path = self.values_file
        else:
            file_path = "new_values.yaml"

        with open(file_path, "w") as values_file:
            try:
                yaml.dump(self.values, values_file)
            except Exception as e:
                print("Unable to write new values file '%s'" % file_path)
                print(e)

    def seal_secrets(self):
        """
        :return: dict of values.yaml.
        :raise: Exception if cannot write to file_path.
        """

        # Check that secrets exist
        if not self.values[SECRETS_KEY]:
            print("No secrets found to seal")
            exit(0)

        # Seal the secret values
        print("Using certificate file '%s' for encrypting secrets" % self.cert)

        # Loop through the secrets
        # YAML format expected:
        #    secrets:
        #      NAMESPACE:
        #        SECRET_NAME:
        #          KEY: VALUE
        for k8s_namespace in self.values[SECRETS_KEY]:
            for k8s_secret in self.values[SECRETS_KEY][k8s_namespace]:
                for key in self.values[SECRETS_KEY][k8s_namespace][k8s_secret]:
                    value = self.values[SECRETS_KEY][k8s_namespace][k8s_secret][key]
                    if value is not None:
                        print("Sealing secret '%s, %s, %s'" % (k8s_namespace, k8s_secret, key))

                        # Run seal secret command to get the sealed value
                        p1 = subprocess.Popen(["echo", "-n", value], stdout=subprocess.PIPE)
                        p2 = subprocess.Popen(["kubeseal", "--cert", self.cert, "--raw", "--namespace", k8s_namespace,
                                               "--name", k8s_secret], stdin=p1.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

                        # Check if sealing the secret failed
                        if p2.wait() != 0:
                            print("Error sealing secret. See output below.")
                            print(str(p2.stderr.readline(), 'utf-8'))
                            break

                        sealed_value = str(p2.stdout.readline(), 'utf-8')

                        # Update yaml with sealed value
                        self.values[SECRETS_KEY][k8s_namespace][k8s_secret][key] = sealed_value

        # Write new values.yaml file
        self.write_new_values()


if __name__ == "__main__":
    cert_file = sys.argv[1]

    questions = [
        inquirer.List("overwrite", message="Do you want to overwrite the current values.yaml?", choices=["Yes", "No"]),
    ]

    answers = inquirer.prompt(questions)

    if answers["Yes"]:
        print("Continuing with  overwriting values.yaml")
        overwrite = True
    else:
        overwrite = False

    seal = SealSecrets(cert_file, overwrite)
    seal.seal_secrets()
