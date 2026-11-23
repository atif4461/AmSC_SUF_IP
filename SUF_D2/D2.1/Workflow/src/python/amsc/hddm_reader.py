
from gluex import hddm_r
import pandas
import numpy as np
import xml.etree.ElementTree as ET

from . import message

def translate_dtype(rd: str):
    if rd == "long": return np.int64
    elif rd == "int": return np.int32
    elif rd == "string": return str
    elif rd == "float": return np.float64
    elif rd == "Particle_t": return str
    raise Exception(f"Unknown dtype: {rd}")

hddm_reserved_attrs = [
    "minOccurs",
    "maxOccurs",
    "lunit",
    "tunit",
    "punit",
    "aunit",
    "Eunit",
    "dEdx_unit"
]

hddm_getter_names = {
    "vertex" : "getVertices",
    "momentum" : "getMomenta",
    "ecalShowerProperties" : "getEcalShowerPropertiesList",
    "fcalShowerProperties" : "getFcalShowerPropertiesList"
}

hddm_tags = []
hddm_attributes = {}
hddm_children = {}
hddm_parents = {}


def getter_name(hddm_tag_name: str) -> str:
    if hddm_tag_name in hddm_getter_names:
        return hddm_getter_names[hddm_tag_name]

    getter_name = hddm_tag_name
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


def visit(table, table_name, parent_id, parent_name, dfs):

    df,next_row,total_rows = dfs[table_name]
    for row in table:

        if table_name in hddm_parents:
            # Disable all other foreign keys
            for col_name in hddm_parents[table_name]:
                df.loc[next_row, col_name] = -1

        # Set the foreign key for THIS parent
        df.loc[next_row, parent_name] = parent_id

        if table_name in hddm_attributes:
            # Set the attributes
            for col_name in hddm_attributes[table_name]:
                df.loc[next_row, col_name] = row.getAttribute(col_name)

        if table_name in hddm_children:
            for child_name in hddm_children[table_name]:
                visit(get_child(row, child_name), child_name, next_row, table_name, dfs)

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

    dfs = {}
    for table_name, row_count in row_counts.items():
        df = make_empty_df(table_name, row_count)
        dfs[table_name] = [df, 0, row_count]
    return dfs

def print_dfs(dfs):
    for table_name in hddm_tags_to_show:
        print("----------------------------------------------------")
        df, rows_filled, rows_total = dfs[table_name]
        print(f"{table_name}")
        if not df.empty:
            print("----------------------------------------------------")
            print(df)

def process_batch(batch, next_entry):
    print("====================================================")
    print(f"Entries {next_entry}..{next_entry+len(batch)-1}")
    dfs = setup_empty_dataframes(batch)
    for rec in batch:
        for toplevel_table_name in hddm_children["entry"]:
            visit(get_child(rec, toplevel_table_name), toplevel_table_name, next_entry, "entry", dfs)
        next_entry += 1
    print_dfs(dfs)
    return next_entry

def process_schemafile(schemafile_name: str):
    tree = ET.parse(schemafile_name)
    process_schema(tree.getroot())


def process_schema(root):
    # A second reader must not append its schema to the previous reader's tables.
    hddm_tags.clear()
    hddm_attributes.clear()
    hddm_parents.clear()
    hddm_children.clear()
    process_element("entry", root)


def process_element(element_name: str, element):
    global hddm_tags
    global hddm_attributes
    global hddm_parents
    global hddm_children

    if element_name != 'entry':
        hddm_tags.append(element_name)

    if element_name not in hddm_attributes:
        hddm_attributes[element_name] = {}

    for attr_name, attr_val in element.attrib.items():
        if attr_name not in hddm_reserved_attrs:
            hddm_attributes[element_name][attr_name] = attr_val

    for child in element:
        child_name = child.tag.split("}",1)[-1]
        if element_name not in hddm_children:
            hddm_children[element_name] = []
        hddm_children[element_name].append(child_name)

        if child_name not in hddm_parents:
            hddm_parents[child_name] = []
        hddm_parents[child_name].append(element_name)


        process_element(child_name, child)

def print_schemafile():
    print("======================")
    for table, children in hddm_children.items():
        print(table)
        for child in children:
            print(f"    {child}")


def process_rest_file(datafile_name: str, batch_size: int):
    ifs = hddm_r.istream(datafile_name)
    next_entry = 0
    batch = []
    for rec in ifs:
        batch.append(rec)
        if len(batch) == batch_size:
            next_entry = process_batch(batch, next_entry)
            batch.clear()
    if batch:
        process_batch(batch, next_entry)
        batch.clear()


class HDDMReader:


    def __init__(self, filename, batch_size, loop):
        # Generated getters and attributes follow the installed bindings' schema.
        # The checked-in XML may describe a newer version with unsupported fields.
        process_schema(ET.fromstring(hddm_r.DocumentString))

        self._batch_size = batch_size
        self._filename = filename
        self._ifs = hddm_r.istream(filename)
        self._loop = loop
        self._next_entry = 0

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
        dfs = setup_empty_dataframes(batch)
        next_entry = starting_entry
        for rec in batch:
            for toplevel_table_name in hddm_children["entry"]:
                visit(get_child(rec, toplevel_table_name), toplevel_table_name, next_entry, "entry", dfs)
            next_entry += 1
        return message.Message(dfs)


