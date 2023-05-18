import unittest
import subprocess
import os
import yaml

PCB_DIR = os.getenv("PROJECT_DIR", os.getenv("PCB_PATH", "ping-cloud-base"))
SEAL_SCRIPT_PATH = os.getenv("SEAL_SCRIPT", ("%s/code-gen/seal.py" % PCB_DIR))


def run_seal_script(cert) -> subprocess.Popen[bytes]:
    p1 = subprocess.Popen(["python3", SEAL_SCRIPT_PATH, cert], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return p1


def get_valid_yaml():
    return {'global': {'sealedSecrets': False, 'secrets': {
        'test-ns': {'test-secret': {'valueone': 'VGhpcyBpcyBhIHRlc3Q=', 'valuetwo': 'dGVzdDI='}}}}}


def write_values_file(values):
    with open("values.yaml", "w") as file:
        try:
            yaml.dump(values, file)
        except Exception as e:
            print("Unable to write values.yaml file")
            raise e


class TestSealScript(unittest.TestCase):
    cert_file = None
    tmp_dir = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.cert_file = "cert.pem"
        p1 = subprocess.Popen(["kubeseal", "--fetch-cert", "--controller-namespace", "kube-system"],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if p1.wait() != 0:
            print(str(p1.stderr.readline(), 'utf-8'))
            raise Exception("Unable to get kubeseal cert. See output above.")
        else:
            with open(cls.cert_file, "a") as file:
                try:
                    for line in p1.stdout:
                        file.write(str(line, 'utf-8'))
                except Exception as e:
                    print("Unable to write cert to file")
                    raise e

    @classmethod
    def tearDownClass(cls) -> None:
        # Delete cert.pem
        if os.path.exists("cert.pem"):
            os.remove("cert.pem")

    def tearDown(self) -> None:
        # Delete values.yaml
        if os.path.exists("values.yaml"):
            os.remove("values.yaml")

    def test_incorrect_usage(self):
        results = subprocess.Popen(["python3", SEAL_SCRIPT_PATH], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        error_code = results.wait()
        self.assertEqual(error_code, 1, "seal script succeeded when not passing in cert file")
        error_msg = str(results.communicate()[0], 'utf-8')
        self.assertIn("Error in usage. No cert file passed in.", error_msg, "seal script returned incorrect error "
                                                                            "message")

    def test_values_file_not_exists(self):
        results = run_seal_script(self.cert_file)
        error_code = results.wait()
        self.assertEqual(error_code, 1, "seal script succeeded when values.yaml doesn't exist")
        error_msg = str(results.communicate()[0], 'utf-8')
        self.assertIn("Values file 'values.yaml' not found", error_msg, "seal script returned incorrect error "
                                                                        "message")

    def test_no_secrets_found(self):
        write_values_file({'global': {'sealedSecrets': False, 'secrets': {}}})
        results = run_seal_script(self.cert_file)
        error_code = results.wait()
        self.assertEqual(error_code, 0, "seal script failed when no secrets found")
        msg = str(results.communicate()[0], 'utf-8')
        self.assertIn("No secrets found to seal", msg, "seal script returned incorrect response")

    def test_invalid_cert_file(self):
        write_values_file(get_valid_yaml())
        results = run_seal_script("invalidcert.pem")
        error_code = results.wait()
        self.assertEqual(error_code, 1, "seal script succeeded when invalid cert file passed")
        error_msg = str(results.communicate()[0], 'utf-8')
        self.assertIn("error: open invalidcert.pem: no such file or directory", error_msg, "seal script returned "
                                                                                           "incorrect error message")

    def test_success(self):
        write_values_file(get_valid_yaml())
        results = run_seal_script(self.cert_file)
        error_code = results.wait()
        self.assertEqual(error_code, 0, "seal script failed when it should have succeeded")
