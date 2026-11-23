import unittest
from unittest.mock import patch

from gluex import hddm_r

from amsc.hddm_reader import HDDMReader
from amsc.message import Message


class HDDMReaderTests(unittest.TestCase):
    def test_installed_bindings_convert_and_round_trip_for_repeated_readers(self):
        record = hddm_r.HDDM()
        events = record.addReconstructedPhysicsEvents(1)
        events[0].eventNo = 42
        events[0].runNo = 11650

        # Use a native record from the installed bindings, without a dataset file.
        with patch(
            "amsc.hddm_reader.hddm_r.istream",
            side_effect=lambda filename: iter([record]),
        ):
            for _ in range(2):
                reader = HDDMReader("unused.hddm", batch_size=1, loop=False)
                batch = reader.read_batch()
                decoded = Message.from_arrow(batch.to_arrow())
                reco = decoded["reconstructedPhysicsEvent"]
                self.assertEqual(len(reco), 1)
                self.assertEqual(reco.iloc[0]["eventNo"], 42)
                self.assertEqual(reco.iloc[0]["runNo"], 11650)
                self.assertIsNone(reader.read_batch())


if __name__ == "__main__":
    unittest.main()
