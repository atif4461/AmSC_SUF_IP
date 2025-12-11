import pandas
import numpy as np
import hddm_r
import sys

def translate_dtype(rd: str):
    if rd == "long": return np.int64
    elif rd == "int": return np.int32
    raise "Unknown"

hddm_attributes = {
    "reconstructedPhysicsEvent" : {
        "eventNo": "long",
        "runNo": "int"
    }
}


def make_empty_df(table_name: str, rows: int):
    cols = hddm_attributes[table_name]
    np_df = {col_name: np.empty(rows, dtype=translate_dtype(col_type)) 
               for col_name, col_type in cols.items()}

    return pandas.DataFrame(np_df)


def fill_df(hddm_table, df, columns, next_row:int) -> int:
    for hddm_row in range(0, len(hddm_table)):
        for col_name, col_type in columns.items():
            df.loc[next_row, col_name] = hddm_table[hddm_row].getAttribute(col_name)
        next_row += 1
    return next_row


def process_rest_file(filename: str):
    ifs = hddm_r.istream(filename)
    for rec in ifs:
        rpe_df = make_empty_df("reconstructedPhysicsEvent", len(rec.getReconstructedPhysicsEvents()))
        fill_df(rec.getReconstructedPhysicsEvents(), rpe_df, hddm_attributes["reconstructedPhysicsEvent"], 0)
        print("-----------------")
        print(rpe_df)


if __name__=="__main__":
    print("REST -> pandas converter")
    process_rest_file(sys.argv[1])



