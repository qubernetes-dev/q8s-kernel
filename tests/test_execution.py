import unittest
from unittest.mock import patch

import requests
from dxf.exceptions import DXFUnauthorizedError

from q8s.execution import ContainerImageValidator


class MockResponse:
    def __init__(self, status_code):
        self.status_code = status_code


class TestContainerImageValidator(unittest.TestCase):

    @patch("q8s.execution.DXF")
    def test_validate_dockerhub_success_without_pat(self, MockDXF):
        instance = MockDXF.return_value

        result = ContainerImageValidator.validate("user/repo:tag")

        self.assertTrue(result)
        MockDXF.assert_called_once_with("registry-1.docker.io", repo="user/repo")
        instance.authenticate.assert_not_called()
        instance.get_alias.assert_called_once_with("tag")

    @patch("q8s.execution.DXF")
    def test_validate_custom_registry_with_pat_authenticate_called(self, MockDXF):
        instance = MockDXF.return_value

        result = ContainerImageValidator.validate(
            "myregistry.com/user/repo:tag", registry_pat="token123"
        )

        self.assertTrue(result)
        MockDXF.assert_called_once_with("myregistry.com", repo="user/repo")
        instance.authenticate.assert_called_once_with(
            username="user", password="token123", actions=["pull"]
        )
        instance.get_alias.assert_called_once_with("tag")

    @patch("q8s.execution.DXF")
    def test_validate_uses_latest_tag_by_default(self, MockDXF):
        instance = MockDXF.return_value

        result = ContainerImageValidator.validate("user/repo")

        self.assertTrue(result)
        MockDXF.assert_called_once_with("registry-1.docker.io", repo="user/repo")
        instance.get_alias.assert_called_once_with("latest")

    @patch("q8s.execution.DXF")
    def test_validate_unauthorized_raises_value_error(self, MockDXF):
        instance = MockDXF.return_value
        instance.get_alias.side_effect = DXFUnauthorizedError()

        with self.assertRaises(ValueError) as ctx:
            ContainerImageValidator.validate("user/repo:tag")

        self.assertIn("requires authentication", str(ctx.exception))

    @patch("q8s.execution.DXF")
    def test_validate_http_403_invalid_pat(self, MockDXF):
        instance = MockDXF.return_value

        http_error = requests.exceptions.HTTPError()

        http_error.response = MockResponse(403)
        instance.get_alias.side_effect = http_error

        with self.assertRaises(ValueError) as ctx:
            ContainerImageValidator.validate("user/repo:tag", registry_pat="badpat")

        self.assertIn("invalid registry PAT", str(ctx.exception))

    @patch("q8s.execution.DXF")
    def test_validate_http_404_not_found(self, MockDXF):
        instance = MockDXF.return_value

        http_error = requests.exceptions.HTTPError()

        http_error.response = MockResponse(404)
        instance.get_alias.side_effect = http_error

        with self.assertRaises(ValueError) as ctx:
            ContainerImageValidator.validate("user/repo:missing")

        self.assertIn("not found", str(ctx.exception))

    def test_validate_empty_image_raises(self):
        with self.assertRaises(ValueError):
            ContainerImageValidator.validate("")

    @patch("q8s.execution.DXF")
    def test_validate_invalid_reference_raises(self, MockDXF):
        with self.assertRaises(ValueError) as ctx:
            ContainerImageValidator.validate("invalidimage")
            self.assertIn("Invalid container image reference", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
