

import pandas as pd
import pyarrow as pa
import pyarrow.ipc as ipc

from amsc import message

def test_basic():

    df_a = pd.DataFrame({
        "x": [1, 2, 3, 100],
        "y": ["a", "b", "c", "d"]
    })

    df_b = pd.DataFrame({
        "u": [10.0, 20.0],
        "v": [True, False],
        "w": [100, 200]
    })

    msg = message.Message({"a": (df_a,-1,-1), "b": (df_b,-1,-1)})
    msg.print_all()
    ser = msg.to_arrow()
    print("Serialized to", len(ser), "bytes")
    deser = msg.from_arrow(ser)
    deser.print_all()



if __name__ == "__main__":
    test_basic()
