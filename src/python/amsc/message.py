
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


