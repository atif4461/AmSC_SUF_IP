import hddm_r
from pathlib import Path
from . import hddm_r_to_pandas
from . import message

class HDDMReader:

    def __init__(self, filename, batch_size, loop, include_tables):
        schemafile = Path(__file__).parent.parent.parent / "cpp/hddm_r/hddm_r.xml"
        hddm_r_to_pandas.hddm_r_to_pandas.process_schemafile(schemafile)

        self._batch_size = batch_size
        self._filename = filename
        self._ifs = hddm_r.istream(filename)
        self._loop = loop
        self._next_entry = 0
        self._include_tables = include_tables

    def read_batch(self):
        batch = []
        if self._loop:
            while True:
                for rec in self._ifs:
                    batch.append(rec)
                    if len(batch) == self._batch_size:
                        starting_entry = self._next_entry
                        self._next_entry += len(batch)
                        return self.convert(batch, starting_entry)

                # Restart the file reader
                self._ifs = hddm_r.istream(self._filename)
        else:
            for rec in self._ifs:
                batch.append(rec)
                if len(batch) == self._batch_size:
                    starting_entry = self._next_entry
                    self._next_entry += len(batch)
                    return self.convert(batch, starting_entry)
            return self.convert(batch, self._next_entry)


    def convert(self, batch, starting_entry):
        if len(batch) == 0:
            return None

        print(f"Converting entries {starting_entry}..{starting_entry+len(batch)-1}")
        dfs = hddm_r_to_pandas.hddm_r_to_pandas.setup_empty_dataframes(batch)
        next_entry = starting_entry
        for rec in batch:
            for toplevel_table_name in hddm_r_to_pandas.hddm_r_to_pandas.hddm_children["entry"]:
                hddm_r_to_pandas.hddm_r_to_pandas.visit(hddm_r_to_pandas.hddm_r_to_pandas.get_child(rec, toplevel_table_name), toplevel_table_name, next_entry, "entry", dfs)
            next_entry += 1
        return message.Message(dfs)


