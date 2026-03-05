
import pyarrow as pa
import pyarrow.ipc as ipc
import pandas as pd

class Message:
    def __init__(self, named_dataframes):
        self._named_dataframes = named_dataframes

    def __getitem__(self, key):
        return self._named_dataframes[key][0]

    @classmethod
    def from_arrow(cls, serialized: bytes):
        named_dataframes = {}
        source = pa.BufferReader(serialized)
        while source.tell() < source.size():
            reader = ipc.open_stream(source)
            table = reader.read_all()
            name = table.schema.metadata[b"name"].decode()
            dataframe = table.to_pandas()
            named_dataframes[name] = (dataframe, -1, -1)
        return cls(named_dataframes)


    def to_arrow(self) -> bytes:
        sink = pa.BufferOutputStream()
        for name in self._named_dataframes:
            df = self._named_dataframes[name][0]
            table = pa.Table.from_pandas(df)
            metadata = {b"name": name.encode()}
            table = table.replace_schema_metadata(metadata)
            writer = ipc.new_stream(sink, table.schema)
            writer.write_table(table)
            writer.close()
        return sink.getvalue().to_pybytes()

    def print_short(self):
        entries_table, _, _ = self._named_dataframes["reconstructedPhysicsEvent"]
        print("----------------------------------------------------")
        print(entries_table)
        print("----------------------------------------------------")


    def print_all(self):
        print("====================================================")
        for table_name in self._named_dataframes:

            df, rows_filled, rows_total = self._named_dataframes[table_name]
            if not df.empty:
                print(f"{table_name}")
                print("----------------------------------------------------")
                print(df)
                print("----------------------------------------------------")
            else:
                print(f"{table_name}: Empty")
        print("====================================================")

    def print_selected(self, include_tables):

        if include_tables is None:
            self.print_all()
            return

        print("====================================================")
        for table_name in include_tables:
            if table_name not in self._named_dataframes:
                print(f"{table_name}: Missing")
                continue

            df, rows_filled, rows_total = self._named_dataframes[table_name]
            if not df.empty:
                print(f"{table_name}")
                print("----------------------------------------------------")
                print(df)
                print("----------------------------------------------------")
            else:
                print(f"{table_name}: Empty")
        print("====================================================")


