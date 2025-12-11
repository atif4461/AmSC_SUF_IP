import pandas
import numpy as np
import hddm_r
import sys

def translate_dtype(rd: str):
    if rd == "long": return np.int64
    elif rd == "int": return np.int32
    elif rd == "string": return str
    elif rd == "float": return np.float64
    raise "Unknown"

hddm_tags = [
    "reconstructedPhysicsEvent",
    "comment",
    "dataVersionString",
    "ccdbContext",
    "bcalShower"
]

hddm_attributes = {
    "reconstructedPhysicsEvent" : {
        "eventNo": "long",
        "runNo": "int"
    },
    "comment": {
        "text": "string"
    },
    "dataVersionString": {
        "text": "string"
    },
    "ccdbContext": {
        "text": "string"
    },
    "bcalShower": {
        "x": "float",
        "y": "float",
        "z": "float",
        "t": "float",
        "E": "float",
        "xerr": "float",
        "yerr": "float",
        "zerr": "float",
        "terr": "float",
        "Eerr": "float",
        "xycorr": "float",
        "xzcorr": "float",
        "yzcorr": "float",
        "tzcorr": "float",
        "Ezcorr": "float"
    }
}

hddm_children = {
    "HDDM": [
        "reconstructedPhysicsEvent"
    ],

    "reconstructedPhysicsEvent" : [
        "comment",
        "dataVersionString",
        "ccdbContext",
        "bcalShower"
    ]
}


def getter_name(hddm_attribute_name: str) -> str:
    getter_name = hddm_attribute_name
    first_char = getter_name[0].capitalize()
    getter_name = "get" + first_char + getter_name[1:]
    last_char = getter_name[-1]
    if last_char in "s":
        getter_name += 'es'
    else:
        getter_name += 's'
    return getter_name


def get_child(hddm_parent_row, hddm_child_name):
    return hddm_parent_row.__getattribute__(getter_name(hddm_child_name))()

def visit_children(parent_table, parent_name, depth, parent_id, dfs):
    indent = "  " * depth
    if len(parent_table) == 0:
        print(f"{indent}{parent_name} is empty")

    parent_row_id = 0
    for parent_row in parent_table:
        print(f"{indent}{parent_name}: {parent_row_id}")
        if parent_name in hddm_attributes:
            for col_name in hddm_attributes[parent_name]:
                print(f"{indent}  {col_name}: {parent_row.getAttribute(col_name)}")

        print()
        if parent_name in hddm_children:
            for child_name in hddm_children[parent_name]:
                visit_children(get_child(parent_row, child_name), child_name, depth+1, parent_row_id, dfs)

        parent_row_id += 1


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

def setup_empty_dataframes(entry):
    dfs = {}
    for table_name in hddm_tags:
        row_count = len(get_child(entry, table_name))
        df = make_empty_df(table_name, row_count)
        dfs[table_name] = (df, 0, row_count)
    return dfs

def process_rest_file(filename: str):
    ifs = hddm_r.istream(filename)
    entry = 0
    for rec in ifs:
        print(f"Entry {entry} ====================================")
        dfs = setup_empty_dataframes(rec)
        visit_children(rec.getReconstructedPhysicsEvents(), "reconstructedPhysicsEvent", 0, entry, dfs)
        print(dfs)
        entry += 1


if __name__=="__main__":
    print("REST -> pandas converter")
    process_rest_file(sys.argv[1])



