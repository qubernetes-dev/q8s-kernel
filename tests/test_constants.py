import unittest

from q8s.constants import get_base_images


class TestGetBaseImages(unittest.TestCase):

    def test_get_base_images_default(self):
        images = get_base_images()
        self.assertEqual(
            images,
            {
                "cpu": "python:3.12-slim",
                "gpu": "ghcr.io/qubernetes-dev/cuda:12.8.1-r2-py3.12",
                "qpu": "python:3.12-slim",
            },
        )

    def test_get_base_images_custom_version(self):
        images = get_base_images("3.11")
        self.assertEqual(
            images,
            {
                "cpu": "python:3.11-slim",
                "gpu": "ghcr.io/qubernetes-dev/cuda:12.8.1-r2-py3.11",
                "qpu": "python:3.11-slim",
            },
        )

    def test_get_base_images_invalid_version_raises(self):
        for version in ("2.7", "3", "3.11.0.1", "3.11a"):
            with self.subTest(version=version):
                with self.assertRaises(ValueError):
                    get_base_images(version)


if __name__ == "__main__":
    unittest.main()
