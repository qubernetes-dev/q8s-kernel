import unittest
import pytest

from q8s.deps.parser import Parser


@pytest.mark.skip(reason="Not implemented for now")
class TestParserSimple(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(1, 1)

        with open("tests/fixtures/simple/qiskit.py") as f:
            code = f.read()
            parser = Parser()
            result = parser.parse(code)

            self.assertEqual(result, "qiskit==1.1.0\nqiskit-aer-gpu==0.15.1")


@pytest.mark.skip(reason="Not implemented for now")
class TestParserApp(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(1, 1)

        with open("tests/fixtures/app/main.py") as f:
            code = f.read()
            parser = Parser()
            result = parser.parse(code)

            self.assertEqual(result, "qiskit==1.1.0")


if __name__ == "__main__":
    unittest.main()
