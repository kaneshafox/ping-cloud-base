import json
import os

import p1_test_base
from k8s_utils import K8sUtils


class TestArgoSSO(p1_test_base.P1TestBase):
    def setUp(self) -> None:
        self.tenant_name = os.getenv("TENANT_NAME", f"{os.getenv('USER')}-primary")
        self.group_names = [
            "argo-pingbeluga",
            f"{self.tenant_name}-argo-configteam",
            "argo-pingplatform",
        ]
        self.app_name = f"client-{self.tenant_name}-argo-sso"
        self.k8s = K8sUtils()

    def test_groups_created(self):
        for group_name in self.group_names:
            with self.subTest(msg=f"{group_name} created"):
                p1_group = self.get(self.cluster_env_endpoints.groups, group_name)
                self.assertIsNotNone(p1_group, f"Group '{group_name}' not created")

    def test_app_created(self):
        p1_app = self.get(self.cluster_env_endpoints.applications, self.app_name)
        self.assertIsNotNone(p1_app, f"Application '{self.app_name}' not created")

    def test_sso_configmap_created(self):
        sso_configmap_data = self.k8s.get_configmap_values(namespace="argocd", configmap_name="argocd-sso-status")
        self.assertTrue(json.loads(sso_configmap_data["sso.configured"].lower()))
