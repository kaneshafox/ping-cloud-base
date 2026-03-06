import os
import time
import unittest
import warnings
import zipfile
from pathlib import Path

import boto3
import pingone_ui as p1_ui
import urllib3
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


@unittest.skipIf(
	os.environ.get("ENV_TYPE") == "customer-hub",
	"Customer-hub CDE detected, skipping test module",
)
class TestPfTemplatesUI(unittest.TestCase):
	@classmethod
	def setUpClass(cls) -> None:
		cls.tenant_domain = os.getenv("TENANT_DOMAIN")
		cls.self_service_url = f"https://self-service.{cls.tenant_domain}"
		cls.region = os.getenv("REGION", "us-west-2")
		cls.config_data_bucket = (
			os.getenv("CONFIG_DATA_BUCKET_URI")
		).replace("s3://", "").strip("/")

		resources_dir = Path(__file__).parent / "resources"
		cls.templates_zip_path = resources_dir / "templates.zip"
		cls.zip_slip_path = resources_dir / "slip.zip"

		cls.config_type_keys = ["templates", "language-packs"]

		cls.config = p1_ui.PingOneUITestConfig(
			app_name="SelfServiceUI",
			console_url=cls.self_service_url,
			roles={"p1asSelfServiceRoles": ["all-tls-admin"]},
			access_granted_xpaths=[],
			access_denied_xpaths=[],
			create_local_only=True,
		)

		cls.ui_driver = p1_ui.PingOneUIDriver()
		cls.ui_driver.setup_browser(window_size="1920,1080")
		cls.ui_driver.login(
			url=cls.config.console_url,
			username=cls.config.local_user.username,
			password=cls.config.local_user.password,
		)
		cls.browser = cls.ui_driver.browser

		warnings.filterwarnings(
			"ignore", category=urllib3.exceptions.InsecureRequestWarning
		)

		cls.wait_time_sec = 10
		cls.wait = WebDriverWait(cls.browser, 30)
		cls.loader_locator = (
			By.CSS_SELECTOR,
			'div[aria-label="Loading in progress"]',
		)

		cls.s3 = boto3.client("s3", region_name=cls.region)

	@classmethod
	def tearDownClass(cls) -> None:
		cls.browser.quit()

	def wait_for_loader(self):
		try:
			WebDriverWait(self.browser, self.wait_time_sec).until(
				EC.presence_of_element_located(self.loader_locator)
			)
		except TimeoutException:
			pass

		try:
			WebDriverWait(self.browser, self.wait_time_sec).until_not(
				EC.presence_of_element_located(self.loader_locator)
			)
		except TimeoutException:
			pass

	def select_test_environment(self):
		env_selector_btn = self.wait.until(
			EC.element_to_be_clickable((By.CSS_SELECTOR, '[data-testid="env-selector"]'))
		)
		env_selector_btn.click()
		self.wait.until(
			EC.presence_of_element_located(
				(By.XPATH, '//ul[@aria-label="Environment Selector" and @role="menu"]')
			)
		)
		menu_item = self.wait.until(
			EC.element_to_be_clickable((By.XPATH, '//li[@role="menuitem"]'))
		)
		menu_item.click()
		self.wait.until(
			EC.invisibility_of_element_located(
				(By.XPATH, '//ul[@aria-label="Environment Selector" and @role="menu"]')
			)
		)

	def navigate_to_page(self, path: str):
		print(f"Navigating to {path} page")
		nav_id = f"/self-service/configurations/{path}"
		nav_xpath = f'//*[@id="{nav_id}"]'

		# Expand Product Configuration section only when the nested nav item is not visible.
		nav_candidates = self.browser.find_elements(By.XPATH, nav_xpath)
		nav_is_visible = any(candidate.is_displayed() for candidate in nav_candidates)

		if not nav_is_visible:
			product_configuration_section = self.wait.until(
				EC.element_to_be_clickable(
					(By.CSS_SELECTOR, 'div[data-testid="Product Configuration"]')
				)
			)
			product_configuration_section.click()
			self.wait_for_loader()

		nav_btn = self.wait.until(
			EC.element_to_be_clickable((By.XPATH, nav_xpath))
		)
		classes = nav_btn.get_attribute("class") or ""
		if "is-selected" not in classes.split():
			nav_btn.click()
			self.wait_for_loader()

	def get_config_display_name(self, config_key: str) -> str:
		return {
			"templates": "Templates",
			"language-packs": "Language Packs",
		}.get(config_key, config_key)

	def list_container(self):
		return self.wait.until(
			EC.visibility_of_element_located(
				(By.CSS_SELECTOR, 'div[data-testid="PingFederate Configuration"]')
			)
		)

	def get_row(self, config_key: str):
		container = self.list_container()
		# Prefer backend key lookup; fall back to visible display name for UI compatibility.
		rows = container.find_elements(
			By.CSS_SELECTOR,
			f'div[role="row"][data-key="{config_key}"]',
		)
		if rows:
			return rows[0]

		display_name = self.get_config_display_name(config_key)
		return container.find_element(
			By.XPATH,
			f'.//div[@role="row"][.//*[normalize-space()="{display_name}"]]',
		)

	def has_configure_button(self, config_key: str) -> bool:
		row = self.get_row(config_key)
		return (
			len(
				row.find_elements(
					By.XPATH,
					'.//button[normalize-space()="Configure"]',
				)
			)
			> 0
		)

	def assert_all_unconfigured(self):
		for config_key in self.config_type_keys:
			with self.subTest(msg=f"{config_key} should be unconfigured"):
				self.assertTrue(
					self.has_configure_button(config_key),
					f"Expected Configure button for '{config_key}'",
				)

	def click_configure_for(self, config_key: str):
		row = self.get_row(config_key)
		configure_btn = row.find_element(
			By.XPATH,
			'.//button[normalize-space()="Configure"]',
		)
		configure_btn.click()

	def upload_zip_from_modal(self, zip_path: Path):
		self.wait.until(
			EC.visibility_of_element_located(
				(By.XPATH, '//div[@role="dialog"]//*[text()="Upload File"]')
			)
		)

		file_input = self.wait.until(
			EC.presence_of_element_located(
				(By.CSS_SELECTOR, 'div[role="dialog"] input[type="file"]')
			)
		)
		file_input.send_keys(str(zip_path))

		save_btn = self.wait.until(
			EC.element_to_be_clickable(
				(By.XPATH, '//div[@role="dialog"]//button[normalize-space()="Save"]')
			)
		)
		save_btn.click()

	def get_toast_notification(self):
		toast = self.wait.until(
			EC.visibility_of_element_located(
				(By.XPATH, "//div[@role='status' and @aria-label]")
			)
		)
		toast_type = toast.get_attribute("aria-label")
		try:
			message_element = toast.find_element(By.TAG_NAME, "span")
			toast_text = message_element.text.strip()
		except Exception:
			toast_text = toast.text.strip()
		return toast_type, toast_text

	def get_row_badge_text(self, config_key: str) -> str | None:
		row = self.get_row(config_key)
		badges = row.find_elements(By.XPATH, './/span[contains(@class, "badge")]')
		if badges:
			for badge in badges:
				text = badge.text.strip()
				if text:
					return text

		known_badges = ["Upload Error", "Error", "Complete", "Updating", "Creating"]
		for label in known_badges:
			if row.find_elements(By.XPATH, f'.//*[normalize-space()="{label}"]'):
				return label
		return None

	def wait_for_status(self, config_key: str, expected_status: str, interval_sec: int = 10, tries: int = 3):
		# Poll status across page refreshes using fixed retries.
		last_seen = None
		for _ in range(tries):
			try:
				badge = self.get_row_badge_text(config_key)
				if badge:
					last_seen = badge
				if badge == expected_status:
					return badge
			except NoSuchElementException:
				pass

			time.sleep(interval_sec)
			self.browser.refresh()
			self.wait_for_loader()
			self.list_container()

		self.fail(
			f"Timed out waiting for {config_key} status '{expected_status}'. "
			f"Last seen: {last_seen}"
		)

	def reset_to_default(self, config_key: str):
		# Open row action menu and execute reset flow via confirmation modal.
		row = self.get_row(config_key)

		more_options_btn = row.find_element(
			By.CSS_SELECTOR,
			'button[aria-label="more options"]',
		)
		more_options_btn.click()

		reset_option = self.wait.until(
			EC.element_to_be_clickable((By.XPATH, "//li[@data-key='delete']"))
		)
		reset_option.click()

		modal = self.wait.until(
			EC.visibility_of_element_located((By.CSS_SELECTOR, 'div[role="dialog"]'))
		)
		modal_locator = (By.CSS_SELECTOR, 'div[role="dialog"]')

		checkbox_label = WebDriverWait(modal, self.wait_time_sec).until(
			EC.element_to_be_clickable((By.XPATH, "//label[@for='confirm-reset']"))
		)
		checkbox_label.click()

		reset_btn = WebDriverWait(modal, self.wait_time_sec).until(
			EC.element_to_be_clickable(
				(By.XPATH, '//div[@role="dialog"]//button[normalize-space()="Reset"]')
			)
		)
		reset_btn.click()

		self.wait.until(EC.invisibility_of_element_located(modal_locator))

	def ensure_config_unconfigured(self, config_key: str):
		self.browser.refresh()
		self.wait_for_loader()
		self.list_container()
		if not self.has_configure_button(config_key):
			self.reset_to_default(config_key)
			_, msg = self.get_toast_notification()
			self.assertIn("reset to default", msg.lower())
			self.browser.refresh()
			self.wait_for_loader()
			self.assertTrue(self.has_configure_button(config_key))

	def get_expected_template_object_keys(self, zip_path: Path) -> set[str]:
		keys = set()
		with zipfile.ZipFile(zip_path, "r") as zf:
			for info in zf.infolist():
				if info.is_dir():
					continue
				clean_name = info.filename.lstrip("/")
				keys.add(f"pingfederate/templates/{clean_name}")
		return keys

	def get_s3_keys_under_prefix(self, bucket: str, prefix: str) -> set[str]:
		keys = set()
		paginator = self.s3.get_paginator("list_objects_v2")
		for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
			for content in page.get("Contents", []):
				keys.add(content["Key"])
		return keys

	def open_view_panel(self, config_key: str):
		row = self.get_row(config_key)
		row.click()
		self.wait.until(
			EC.visibility_of_element_located((By.CSS_SELECTOR, 'div[data-testid="view"]'))
		)

	def get_upload_errors_from_view(self) -> list[str]:
		panel = self.wait.until(
			EC.visibility_of_element_located((By.CSS_SELECTOR, 'div[data-testid="view"]'))
		)
		items = panel.find_elements(By.XPATH, ".//li")
		errors = []
		for item in items:
			text = item.text.strip()
			if text:
				errors.append(text)
		return errors

	def setUp(self) -> None:
		self.select_test_environment()
		self.navigate_to_page("pingfederate")

	def test_templates_upload_success_and_reset(self):
		# Upload templates, verify status/S3 artifacts, then reset.
		self.assertTrue(
			self.templates_zip_path.exists(),
			f"Templates zip file not found: {self.templates_zip_path}",
		)
		self.assertTrue(
			self.config_data_bucket,
			"Missing CONFIG_DATA_S3_BUCKET_URI (or SS_CONFIG_DATA_BUCKET_URI)",
		)

		# Ensure both configurable items start from unconfigured state.
		for config_key in self.config_type_keys:
			self.ensure_config_unconfigured(config_key)
		self.assert_all_unconfigured()

		# Upload the valid templates zip.
		self.click_configure_for("templates")
		self.upload_zip_from_modal(self.templates_zip_path)

		toast_type, message = self.get_toast_notification()
		self.assertEqual(toast_type, "Success Message")
		self.assertIn("Templates", message)
		self.assertTrue(
			"configured" in message.lower() or "updated" in message.lower(),
			f"Unexpected upload success message: {message}",
		)
		print(f"Upload success: {message}")

		# Wait for the "Creating" state before final completion validation.
		WebDriverWait(self.browser, 30).until(
			lambda _: self.get_row_badge_text("templates") == "Creating"
		)
		print("Observed status after upload: Creating")

		time.sleep(10)
		self.browser.refresh()
		self.wait_for_loader()
		
        # Wait for the status to turn "Complete"
		badge = self.get_row_badge_text("templates")
		if badge != "Complete":
			badge = self.wait_for_status(
				config_key="templates",
				expected_status="Complete",
				interval_sec=10,
				tries=3,
			)
		self.assertEqual(badge, "Complete")
		print("Status changed to Complete")

		# Verify uploaded objects and deployed bundle were written to config-data bucket.
		expected_keys = self.get_expected_template_object_keys(self.templates_zip_path)
		actual_keys = self.get_s3_keys_under_prefix(
			bucket=self.config_data_bucket,
			prefix="pingfederate/templates/",
		)
		missing = expected_keys.difference(actual_keys)
		self.assertFalse(missing, f"Missing uploaded files in S3: {sorted(missing)}")
		print("Verified uploaded template files in S3")

		deployed_key = "pingfederate/deployed/templates.zip"
		deployed_obj = self.s3.list_objects_v2(
			Bucket=self.config_data_bucket,
			Prefix=deployed_key,
			MaxKeys=1,
		)
		self.assertTrue(
			any(content.get("Key") == deployed_key for content in deployed_obj.get("Contents", [])),
			f"Expected deployed zip not found: {deployed_key}",
		)
		print("Verified deployed templates.zip in S3")

		# Reset templates back to default.
		self.reset_to_default("templates")
		_, reset_message = self.get_toast_notification()
		self.assertIn("reset to default", reset_message.lower())
		print(f"Reset completed: {reset_message}")

		self.browser.refresh()
		self.wait_for_loader()
		self.assertTrue(
			self.has_configure_button("templates"),
			"Configure button did not re-appear after reset",
		)

	def test_templates_zip_slip_shows_error_details(self):
		# Upload malicious zip and confirm validation errors are surfaced.
		self.assertTrue(
			self.zip_slip_path.exists(),
			f"Zip-slip test file not found: {self.zip_slip_path}",
		)

		self.ensure_config_unconfigured("templates")

		# Upload invalid archive.
		self.click_configure_for("templates")
		self.upload_zip_from_modal(self.zip_slip_path)

		toast_type, message = self.get_toast_notification()
		self.assertEqual(toast_type, "Success Message")
		self.assertIn("Templates", message)
		print(f"Zip-slip upload success: {message}")

		badge = self.wait_for_status(
			config_key="templates",
			expected_status="Upload Error",
			interval_sec=10,
			tries=3,
		)
		self.assertEqual(badge, "Upload Error")
		print(f"Observed expected error status: {badge}")

		# Validate detailed errors in the side panel.
		self.open_view_panel("templates")
		errors = self.get_upload_errors_from_view()
		self.assertTrue(errors, "Expected upload errors in view panel but found none")
		print(f"Captured upload errors: {errors}")

		joined_errors = " ".join(errors).lower()
		self.assertTrue(
			any(keyword in joined_errors for keyword in ["unsafe path", "error", "..", "zip"]),
			f"Unexpected upload error text: {errors}",
		)

		self.browser.refresh()
		self.wait_for_loader()
		self.list_container()

		# Reset templates back to default.
		self.reset_to_default("templates")
		_, reset_message = self.get_toast_notification()
		self.assertIn("reset to default", reset_message.lower())
		print(f"Reset completed: {reset_message}")

		self.browser.refresh()
		self.wait_for_loader()
		self.assertTrue(self.has_configure_button("templates"))
