import tempfile
import unittest
from pathlib import Path

from viewer import claim_viewer_instance


class SingleViewerTests(unittest.TestCase):
    def test_same_archive_has_one_owner_until_release(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'viewer-data'
            first=claim_viewer_instance(root)
            self.assertIsNotNone(first)
            try:
                self.assertIsNone(claim_viewer_instance(root))
                self.assertIsNone(claim_viewer_instance(root/'.'))
            finally:
                first.close()
            second=claim_viewer_instance(root)
            self.assertIsNotNone(second)
            second.close()


if __name__=='__main__':unittest.main()
