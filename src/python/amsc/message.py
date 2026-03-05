
class Message:
    def __init__(self, named_dataframes):
        self._named_dataframes = named_dataframes

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


