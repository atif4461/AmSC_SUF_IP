
import pandas as pd

def increment(x):
    return x+1

def make_dummy_hits_df():

    hits_df = pd.DataFrame({
        "entry_id": [1, 1, 1, 2, 2],
        "coll_id":  [0, 0, 1, 0, 1],
        "obj_id":   [10, 11, 12, 20, 21],
        "cell_id":  [101, 102, 103, 101, 104],
        "energy":   [3.2, 1.8, 5.4, 2.1, 4.9],
    })

    # Enforce dtypes explicitly
    hits_df = hits_df.astype({
        "entry_id": "int32",
        "coll_id": "int32",
        "obj_id": "int32",
        "cell_id": "int32",
        "energy": "float64",
    })

    return hits_df



def serialize_arrow(df: pd.DataFrame) -> bytes:
    table = pa.Table.from_pandas(df, preserve_index=False)

    sink = pa.BufferOutputStream()
    writer = ipc.RecordBatchStreamWriter(sink, table.schema)
    writer.write_table(table)
    writer.close()

    return sink.getvalue().to_pybytes()

