import pandas
import numpy as np
import hddm_r
import sys

def translate_dtype(rd: str):
    if rd == "long": return np.int64
    elif rd == "int": return np.int32
    elif rd == "string": return str
    elif rd == "float": return np.float64
    raise Exception(f"Unknown dtype: {rd}")

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
    "entry": [
        "reconstructedPhysicsEvent"
    ],

    "reconstructedPhysicsEvent" : [
        "comment",
        "dataVersionString",
        "ccdbContext",
        "bcalShower"
    ]
}

hddm_parents = {
    "reconstructedPhysicsEvent": ["entry"],
    "comment": ["reconstructedPhysicsEvent"],
    "dataVersionString": ["reconstructedPhysicsEvent"],
    "ccdbContext": ["reconstructedPhysicsEvent"],
    "bcalShower": ["reconstructedPhysicsEvent"],
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


def fill_df(hddm_table, df, columns, next_row:int) -> int:
    for hddm_row in range(0, len(hddm_table)):
        for col_name, col_type in columns.items():
            df.loc[next_row, col_name] = hddm_table[hddm_row].getAttribute(col_name)
        next_row += 1
    return next_row


def visit(table, table_name, depth, parent_id, parent_name, dfs):

    df,next_row,total_rows = dfs[table_name]
    for row in table:

        if table_name in hddm_parents:
            # Disable all other foreign keys
            for col_name in hddm_parents[table_name]:
                df.loc[next_row, col_name] = -1  # In case we have multiple foreign keys

        # Set the foreign key for THIS parent
        df.loc[next_row, parent_name] = parent_id

        if table_name in hddm_attributes:
            # Set the attributes
            for col_name in hddm_attributes[table_name]:
                df.loc[next_row, col_name] = row.getAttribute(col_name)

        if table_name in hddm_children:
            for child_name in hddm_children[table_name]:
                visit(get_child(row, child_name), child_name, depth+1, next_row, table_name, dfs)

        next_row += 1

    dfs[table_name][1] = next_row


def make_empty_df(table_name: str, rows: int):

    cols = {parent_name:"int" for parent_name in hddm_parents[table_name]}
    cols.update(hddm_attributes[table_name])

    np_df = {col_name: np.empty(rows, dtype=translate_dtype(col_type)) 
               for col_name, col_type in cols.items()}

    return pandas.DataFrame(np_df)


def setup_empty_dataframes(batch):
    row_counts = {table_name: 0 for table_name in hddm_tags}
    for entry in batch:
        for table_name in hddm_tags:
            row_counts[table_name] += len(get_child(entry, table_name))

    print("Row counts:")
    print(row_counts)

    dfs = {}
    for table_name, row_count in row_counts.items():
        df = make_empty_df(table_name, row_count)
        dfs[table_name] = [df, 0, row_count]
    return dfs

def print_dfs(dfs):
    for table_name in hddm_tags:
        df, rows_filled, rows_total = dfs[table_name]
        print(f"{table_name}: {rows_filled}/{rows_total} rows filled")
        if not df.empty:
            print(df)

def process_batch(batch, next_entry):
    print("====================================================")
    print(f"Entries {next_entry}..{next_entry+len(batch)-1}")
    dfs = setup_empty_dataframes(batch)
    for rec in batch:
        for toplevel_table_name in hddm_children["entry"]:
            visit(get_child(rec, toplevel_table_name), toplevel_table_name, 0, next_entry, "entry", dfs)
        next_entry += 1
    print_dfs(dfs)
    batch.clear()
    return next_entry

def process_rest_file(filename: str, batch_size: int):
    ifs = hddm_r.istream(filename)
    next_entry = 0
    batch = []
    for rec in ifs:
        batch.append(rec)
        if len(batch) == batch_size:
            next_entry = process_batch(batch, next_entry)
    if batch:
        process_batch(batch, next_entry)


if __name__=="__main__":
    process_rest_file(sys.argv[1], 4)



