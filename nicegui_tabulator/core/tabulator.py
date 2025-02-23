from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, Union
from nicegui.element import Element
from nicegui.awaitable_response import AwaitableResponse
from warnings import warn
from .utils import DeferredTask
from nicegui.elements.teleport import Teleport as teleport
from .types import CellSlotProps, T_Row_Range_Lookup
from . import utils

try:
    import pandas as pd
except ImportError:
    pass


class Tabulator(
    Element, component="tabulator.js", dependencies=["libs/tabulator.min.js"]
):
    def __init__(
        self,
        options: Dict,
        row_key: Optional[str] = "id",
    ) -> None:
        """Create a new tabulator table.

        Args:
            options (Dict): The options for the tabulator table.
            row_key (str, optional): The field to be used as the unique index for each row. Defaults to "id".
        """
        super().__init__()
        self.__deferred_task = DeferredTask()

        if row_key:
            options.update(index=row_key)

        self._props["options"] = options
        self.add_resource(Path(__file__).parent / "libs")

        self._cell_slot_map: Dict[str, Callable] = {}
        self._teleport_slots_cache: Dict[Tuple[str, int], teleport] = {}

        def on_update_cell_slot(e):
            field = e.args["field"]
            row_number = e.args["rowNumber"]
            row_index = e.args["rowIndex"]
            key = (field, row_index)

            if field not in self._cell_slot_map:
                return

            if key in self._teleport_slots_cache:
                # TODO:how reuse the teleport instead of creating a new one?
                tp = self._teleport_slots_cache[key]
                tp.delete()

            fn = self._cell_slot_map[field]
            tp = fn(row_number, row_index)
            if tp:
                self._teleport_slots_cache[key] = tp

            self.run_method("resetRowFormat", row_number)

        self.on("updateCellSlot", on_update_cell_slot)

        def on_connected():
            self.__deferred_task.flush()
            self.__deferred_task.component_connected = True

        self.on("connected", on_connected)

    @property
    def index_field(self):
        """Get the index field for the tabulator table.By default Tabulator will look for this value in the id field for the data."""
        return self._props["options"].get("index", "id")

    @property
    def data(self):
        """Get or set the data for the tabulator table."""
        if "data" not in self._props["options"]:
            self._props["options"]["data"] = []
        return self._props["options"]["data"]

    def delete(self) -> None:
        for tp in self._teleport_slots_cache.values():
            tp.delete()
        return super().delete()

    def on_event(
        self,
        event: str,
        callback: Callable[..., None],
    ):
        """
        Register an event listener for the tabulator table.

        Args:
            event (str): The name of the event to listen for.
            callback (Callable[..., None]): The function to call when the event is triggered.

        """

        if event.endswith("tableBuilding"):
            warn("The 'tableBuilding' event cannot be triggered.")
            return self

        if not event.startswith("table:"):
            event = f"table:{event}"

        @self.__deferred_task.register
        def _():
            self.run_method("onEvent", event)

        self.on(event, callback)

        return self

    def run_table_method(
        self, name: str, *args, timeout: float = 1, check_interval: float = 0.01
    ) -> AwaitableResponse:
        """
        Run a method on the tabulator table.

        Args:
            name (str): The name of the method to run.
            *args: The arguments to pass to the method.
            timeout (float, optional): The maximum time to wait for the method to complete. Defaults to 1.
            check_interval (float, optional): The interval at which to check if the method has completed. Defaults to 0.01.

        """
        return self.run_method("run_table_method", name, *args, timeout=timeout)

    def set_columns(self, columns: List[Dict]) -> None:
        """
        To replace the current column definitions for all columns in a table.

        @see https://tabulator.info/docs/6.2/columns#replace

        Args:
            columns (List[Dict]): The list of column definition objects for the table.

        ## Example Usage

        .. code-block:: python
            table = Tabulator({...})

            new_columns = [
                {'title':"Name", 'field':"name"},
                {'title':"Age", 'field':"age"},
            ]

            table.set_columns(new_columns)

        """

        @self.__deferred_task.register
        def _():
            self.run_method("setColumns", columns)

    def update_column_definition(self, field: str, definition: Dict) -> None:
        """
        Update an existing column definition.

        @see https://tabulator.info/docs/6.2/columns#update

        Args:
            field (str): The field name of the column you want to update.
            definition (Dict): The new column definition object for the column.

        ## Example Usage

        .. code-block:: python
            table = Tabulator({...})
            table.update_column_definition("name", {'title':"Updated Title"})

        """

        @self.__deferred_task.register
        def _():
            self.run_method("updateColumnDefinition", field, definition)

    def add_column(
        self,
        definition: Dict,
        before: Optional[bool] = None,
        position: Optional[str] = None,
    ) -> None:
        """
        Add a column to the table.

        @see https://tabulator.info/docs/6.2/columns#add


        Args:
            definition (Dict): The column definition object for the column you want to add.
            before (Optional[bool], optional): Determines how to position the new column. A value of true will insert the column to the left of existing columns, a value of false will insert it to the right. If a Position argument is supplied then this will determine whether the new colum is inserted before or after this column.
            position (Optional[str], optional): The field to insert the new column next to, this can be any of the standard column component look up options.

        ## Example Usage

        .. code-block:: python
            table = Tabulator({...})
            table.add_column({'title':"Age", 'field':"age"}, True, "name")

        """

        @self.__deferred_task.register
        def _():
            self.run_table_method("addColumn", definition, before, position)

    @classmethod
    def from_pandas(
        cls,
        df: "pd.DataFrame",
        *,
        index: Optional[str] = None,
        auto_index=False,
        options: Optional[Dict] = None,
        column_definition: Optional[Callable[[str], Dict]] = None,
    ):
        """Create a table from a Pandas DataFrame.

        Note:
        If the DataFrame contains non-serializable columns of type `datetime64[ns]`, `timedelta64[ns]`, `complex128` or `period[M]`,
        they will be converted to strings.

        Args:
            df (pd.DataFrame): The DataFrame to create the table from.
            index (str, optional): The field to be used as the unique index for each row.
            auto_index (bool, optional): If `True` and the `index` parameter is `None`, a sequence number column will be automatically generated as the index.
            options (Dict, optional): The options for the tabulator table.
            column_definition (Callable[[str], Dict], optional): A function that takes a column name and returns a column definition object for that column.
        """

        def is_special_dtype(dtype):
            return (
                pd.api.types.is_datetime64_any_dtype(dtype)
                or pd.api.types.is_timedelta64_dtype(dtype)
                or pd.api.types.is_complex_dtype(dtype)
                or isinstance(dtype, pd.PeriodDtype)
            )

        special_cols = df.columns[df.dtypes.apply(is_special_dtype)]
        if not special_cols.empty:
            df = df.copy()
            df[special_cols] = df[special_cols].astype(str)

        if isinstance(df.columns, pd.MultiIndex):
            raise ValueError(
                "MultiIndex columns are not supported. "
                "You can convert them to strings using something like "
                '`df.columns = ["_".join(col) for col in df.columns.values]`.'
            )

        columns: List[Dict] = [
            {"title": col, "field": col}
            if column_definition is None
            else {"field": col, **column_definition(col)}
            for col in df.columns
        ]

        options = options or {}

        if index is not None:
            options["index"] = index
        elif auto_index:
            col_name = utils.generate_dataframe_unique_id_column_name()
            df = df.assign(**{col_name: range(len(df))})
            columns.insert(0, {"title": col_name, "field": col_name, "visible": False})
            options["index"] = col_name

        options.update({"data": df.to_dict(orient="records"), "columns": columns})

        return cls(options, row_key=None)

    def add_cell_slot(
        self,
        field: str,
    ):
        """
        Add a cell slot to the table.

        @see https://github.com/CrystalWindSnake/nicegui-tabulator?tab=readme-ov-file#cell-slots


        Args:
            field (str): The field name of the column you want to add a cell slot to.


        ## Example Usage

        .. code-block:: python
            from nicegui import ui
            from nicegui_tabulator import tabulator,CellSlotProps

            table = tabulator({...})

            @table.add_cell_slot("name")
            def name_cell(props: CellSlotProps):
                ui.input(value=props.value, placeholder="Enter name")

        """
        id = f"c{self.id}"

        def wrapper(build_fn: Callable[[CellSlotProps], None]):
            def fn(row_number: int, row_index: int):
                options = self._props["options"]
                data = options.get("data", [])
                if not data:
                    return
                row = data[row_index]

                class_name = f"ng-cell-slot-{field}-{row_index}"
                with teleport(f"#{id} .{class_name}") as tp:
                    cell_slot = CellSlotProps(
                        field=field,
                        value=row[field],
                        row=row,
                        row_number=row_number,
                        row_index=row_index,
                        table=self,
                    )
                    build_fn(cell_slot)

                return tp

            self.update_column_definition(
                field,
                {
                    ":formatter": rf"""
        function(cell, formatterParams, onRendered){{
        
            const row = cell.getRow();
            const table = row.getTable();
            const field = cell.getField();

            onRendered(function(){{
                const rowNumber = row.getPosition();
                const rowIndexValue = row.getIndex();
                const indexField = table.options.index;
                const rowIndex = table.options.data.findIndex(r => r[indexField] === rowIndexValue);
                const target = cell.getElement();
                target.innerHTML = `<div class="ng-cell-slot-${{field}}-${{rowIndex}} fit"></div>`
                const tableObject = getElement({self.id});
                runMethod(tableObject, 'updateCellSlot',[field,rowNumber,rowIndex]);
            }});
        }}
        """
                },
            )
            self._cell_slot_map[field] = fn

        return wrapper

    def set_data(self, data: List[Dict]):
        """set the data of the table.

        @see https://tabulator.info/docs/6.2/data#array

        Args:
            data (List[Dict]): The data to set for the table.


        """
        self._set_data_on_server(data)
        self.run_table_method("setData", data)
        return self

    def replace_data(self, data: List[Dict]):
        """replace the data of the table.

        @see https://tabulator.info/docs/6.2/update#alter-replace

        Args:
            data (List[Dict]): The data to replace the current data with.

        """
        self.set_data(data)
        return self

    def update_data(self, data: List[Dict]):
        """update the data of the table.

        @see https://tabulator.info/docs/6.2/update#alter-update

        Args:
            data (List[Dict]): The data to update the current data with.

        """
        self._update_data_on_server(data)
        self.run_table_method("updateData", data)
        return self

    def add_data(
        self,
        data: List[Dict],
        at_top: Optional[bool] = None,
        index: Optional[Union[int, str]] = None,
    ):
        """add data to the table.

        @see https://tabulator.info/docs/6.2/update#alter-add

        Args:
            data (List[Dict]): The data to add to the current data.
            at_top (Optional[bool], optional): determines whether the data is added to the top or bottom of the table. A value of true will add the data to the top of the table, a value of false will add the data to the bottom of the table. If the parameter is not set the data will be placed according to the addRowPos global option.
            index (Optional[Union[int, str]], optional): table row index. position the new rows next to the specified row (above or below based on the value of the second argument). This argument will take any of the standard row component look up options

        """
        self._add_data_on_server(data, at_top, index)
        self.run_table_method("addData", data, at_top, index)
        return self

    def update_or_add_data(self, data: List[Dict]):
        """update or add data to the table.
        If the data you are passing to the table contains a mix of existing rows to be updated and new rows to be added then you can call the updateOrAddData function. This will check each row object provided and update the existing row if available, or else create a new row with the data.

        @see https://tabulator.info/docs/6.2/update#alter-add

        Args:
            data (List[Dict]): The data to update or add to the current data.

        """
        self._update_or_add_data_on_server(data)
        self.run_table_method("updateOrAddData", data)
        return self

    def clear_data(self):
        """clear the data of the table.

        @see https://tabulator.info/docs/6.2/update#alter-empty

        """
        self._set_data_on_server([])
        self.run_table_method("clearData")
        return self

    def sync_data_to_client(self):
        """sync server data to the client.

        @see https://github.com/CrystalWindSnake/nicegui-tabulator/tree/main?tab=readme-ov-file##cell-slot
        """
        self.set_data(self._props["options"]["data"])
        return self

    def _add_data_on_server(
        self,
        data: List[Dict],
        at_top: Optional[bool] = None,
        index: Optional[Union[int, str]] = None,
    ):
        at_top = (
            at_top
            if at_top is not None
            else self._props["options"].get("addRowPos", "bottom") == "top"
        )

        if index is None:
            row_index = 0 if at_top else len(self.data)
        else:
            index_field = self.index_field
            indices = [
                i for i, row in enumerate(self.data) if row[index_field] == index
            ]
            if not indices:
                row_index = 0 if at_top else len(self.data)
            else:
                row_index = indices[0] + (0 if at_top else 1)

        self._set_data_on_server(self.data[:row_index] + data + self.data[row_index:])

    def _set_data_on_server(self, data: List[Dict]):
        if "data" not in self._props["options"]:
            self._props["options"]["data"] = None
        self._props["options"]["data"] = data[:]

    def _update_data_on_server(self, data: List[Dict]):
        index_field = self.index_field
        update_dict = {record[index_field]: record for record in data}

        for row in self.data:
            update_id = row.get(index_field, None)
            if not update_id:
                continue

            update_record = update_dict.get(update_id, None)

            if update_record:
                row.update(update_record)

    def _update_or_add_data_on_server(self, data: List[Dict]):
        index_field = self.index_field
        update_dict = {item[index_field]: item for item in data}

        for item in self.data:
            if item[index_field] in update_dict:
                item.update(update_dict.pop(item[index_field]))

        self._set_data_on_server([*self.data, *update_dict.values()])

    def print(
        self,
        *,
        row_range_lookup: Optional[T_Row_Range_Lookup] = None,
        style: Optional[bool] = True,
        config: Optional[Dict] = None,
    ):
        """A full page printing of the contents of the table without any other elements from the page.

        Args:
            row_range_lookup (Optional[T_Row_Range_Lookup], optional): Determins which rows are shown in the printed table, if no value is set it will use the value set in the printRowRange option.
            style (Optional[bool], optional): Determines if the output of the function should be styled to match the table (true) or be a blank html table (false), if you leave this argument out it will take the value of the printStyled option. Defaults to True.
            config (Optional[Dict], optional): An object that can be used to override the object set on the printConfig option. Defaults to None.
        """
        self.sync_data_to_client()
        self.run_table_method("print", row_range_lookup, style, config)

    async def get_selected_data(self) -> List[Dict]:
        """Get the selected data from the table."""
        return await self.run_table_method("getSelectedData")
