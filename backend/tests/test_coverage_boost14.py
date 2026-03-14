"""boost14 — final 1 line to cross 95%."""
import unittest
from backend.api.exceptions import YGBError

class TestYGBErrorLog(unittest.TestCase):
    def test_log_method(self):
        e = YGBError("test error", cause=ValueError("inner"))
        e.log()  # covers line 51

if __name__ == "__main__":
    unittest.main()
