import os
from pathlib import Path
import customtkinter as ctk
import copy
from typing import Any, TypeVar, Callable, Generic, Protocol
from support_classes import Settings
from .themes import ApplicationTheme
from PIL import Image


class WidgetGroup:
    """Creates a group of show/hide widgets. Can also have other groups as children to show/hide"""
    def __init__(self,initial_row = 0, widgets: list[ctk.CTkBaseClass] = [], rows: list[int] = [], columns: list[int] = [], vars: list["SettingVariable"] = [],children: list["WidgetGroup"]|None = [], parent: "WidgetGroup" = None):
        max_index = min(len(widgets),len(rows),len(columns))
        self.group: list[tuple[ctk.CTkBaseClass,int,int]] = copy.copy([[widgets[i],rows[i],columns[i]] for i in range(0,max_index)])
        self.current_row = initial_row
        self.is_displayed = False
        self.__is_showing = False
        self.__children = copy.copy(children)
        self.__vars = copy.copy(vars)
        self.__parent: WidgetGroup|None = None
        if parent is not None:
            parent.add_child(self)

    def add_at_position(self,widget: ctk.CTkBaseClass, row: int, column: int):
        self.group.append([widget,row,column])
    
    def add_widget(self,widget: ctk.CTkBaseClass, column: int):
        self.group.append([widget,self.current_row,column])

    def nextrow(self):
        self.current_row += 1
    
    def show(self):
        self.__is_showing = True
        # only display if the parent group is displayed
        if self.__parent is None or self.__parent.__is_showing:
            # display all child groups
            for child in self.__children:
                if child.__is_showing:
                    child.show()
            # display all widgets in this group
            for widget_info in self.group:
                widget = widget_info[0]
                row = widget_info[1]
                column = widget_info[2]
                widget.grid(row=row,column = column, padx=10, pady=5,sticky="nsew")
    
    def hide(self):
        self.__hide_with_state()
        self.__is_showing = False
    
    def __hide_with_state(self):
        if not self.__is_showing:
            return
        # hide all child groups
        for child in self.__children:
            child.__hide_with_state()
        # hide all widgets in this group
        for widget_info in self.group:
            widget_info[0].grid_remove()

    def add_child(self,child: "WidgetGroup"):
        if child.__parent is None:
            self.__children.append(child)
            child.__parent = self
        else:
            raise Exception(f"Group {child} already has a parent group!")
    
    def add_var(self,var: "SettingVariable"):
        if var not in self.__vars:
            self.__vars.append(var)
    
    def get_vars(self) -> list["SettingVariable"]:
        if not self.__is_showing:
            return []
        vars_out = self.__vars
        for child in self.__children:
            childvars = child.get_vars()
            vars_out = [*vars_out,*childvars]
        return vars_out

T = TypeVar("T")
class SettingVariable(Generic[T]):
    """Wrapper for a ctk Var object, lining the Var with a specified application setting"""
    def __init__(self,var: ctk.StringVar,setting: Settings,validator: Callable[[T],bool]|None = None, map_fun: Callable[[str],T]|None = None) -> None:
        self.__var = var
        self.__setting = setting
        self.fun = map_fun
        if validator is None:
            validator = lambda _: True
        self.__validator = validator
        self.widget: ctk.CTkBaseClass|None = None
    def get(self) -> str:
        return self.__var.get()
    def set(self,value: str) -> None:
        self.__var.set(value)
    def get_mapped(self) -> T:
        if self.fun:
            return self.fun(self.get())
        return self.get()
    def is_valid(self) -> bool:
        val = self.get()
        return self.__validator(val)
    def trace_add(self,callback: Callable[[str,str,str],None]):
        self.__var.trace_add("write",callback)
    @property
    def setting(self) -> Settings:
        return self.__setting
    def disable(self):
        if self.widget:
            self.widget.configure(state=ctk.DISABLED)
    def enable(self):
        if self.widget:
            self.widget.configure(state=ctk.NORMAL)
        

class _MakerFunction(Protocol):
    def __call__(self,frame: ctk.CTkFrame, name: str, settings: Settings, initial_value: str, **kwargs) -> tuple[ctk.CTkLabel,"SettingVariable",ctk.CTkFrame]: ...

def _makerfunction(fn: _MakerFunction) -> _MakerFunction: return fn

@_makerfunction
def make_entry(frame: ctk.CTkFrame,
                name: str, 
                setting: Settings, 
                initial_value: str,
                entry_validator: Callable[...,bool] = lambda *args,**kwargs: True,
                units: str|None = None,
                map_fun: Callable[[str],Any]|None = None, 
                on_return: Callable[[None],None]|None = None,
                **kwargs
                ) -> tuple[ctk.CTkLabel,"SettingVariable",ctk.CTkFrame]:
    lbl = ctk.CTkLabel(frame,text=name)
    ctkvar = ctk.StringVar(value=initial_value)
    var = SettingVariable(ctkvar,setting,validator=lambda val: entry_validator(val,allow_empty=False),map_fun=map_fun)
    entryparent = ctk.CTkFrame(frame)
    entry = ctk.CTkEntry(entryparent,textvariable=ctkvar, validate='key', validatecommand = (frame.register(entry_validator),"%P"))
    entry.bind("<Return>",lambda *args: on_return() if on_return else None)
    var.widget = entry
    frame.columnconfigure([0],weight=1)
    frame.columnconfigure([1],weight=0)
    if units:
        entry.grid(row=0,column=0,padx=0,pady=0,sticky="nsew")
        unit_label = ctk.CTkLabel(entryparent,text=units)
        unit_label.grid(row=0,column=1,padx=10,pady=0,sticky="nse")
    else:
        entry.grid(row=0,column=0,columnspan=2,padx=0,pady=0,sticky="nsew")
    return lbl,var,entryparent

def make_fileselect(frame: ctk.CTkFrame,
                     name: str,
                     setting: Settings,
                     initial_value: str,
                     file_command: Callable[[None],Path] = lambda: ctk.filedialog.askdirectory(),
                     validator: Callable[...,bool]|None = None,
                     on_return: Callable[[None],None]|None = None,
                     **kwargs
                     ):
    lbl = ctk.CTkLabel(frame,text=name)
    ctkvar = ctk.StringVar(value=initial_value)
    def default_validator(value: str):
        if value == "":
            return False
        elif os.path.isdir(value):
            return True
        return False

    var = SettingVariable(ctkvar,
                           setting,
                           validator=lambda value: validator(value,allow_empty=False) if validator else default_validator,
                           map_fun=Path)
    entryparent = ctk.CTkFrame(frame)
    entry = ctk.CTkEntry(entryparent,textvariable=ctkvar)
    def _command():
        directory = file_command()
        if directory != "":
            var.set(directory)
    if on_return:
        entry.bind("<Return>",on_return)
    var.widget=entry
    button = ctk.CTkButton(entryparent,text="Select Directory",command=_command)
    entryparent.columnconfigure(0,weight=1)
    entryparent.columnconfigure(1,weight=0)
    entry.grid(row=0,column=0,padx=(0,10),pady=0,sticky="nsew")
    button.grid(row=0,column=1,padx=(10,0),pady=0,sticky="nse")
    frame.columnconfigure(0,weight=0)
    frame.columnconfigure(1,weight=1)
    return lbl,var,entryparent

@_makerfunction
def make_menu(frame: ctk.CTkFrame,
                name: str, 
                setting: Settings, 
                initial_value: str,
                map_fun: Callable[[str],Any] | None = None,
                values: list[str] = ["Please Select a Value"],
                refresh_function: Callable[[None],None] | None = None
                ) -> tuple[ctk.CTkLabel,"SettingVariable",ctk.CTkFrame]:
    lbl = ctk.CTkLabel(frame,text=name)
    ctkvar = ctk.StringVar(value=initial_value)
    var = SettingVariable(ctkvar,setting,map_fun=map_fun)
    menuparent = ctk.CTkFrame(frame,corner_radius=ApplicationTheme.BUTTON_CORNER_RADIUS)
    menu = ctk.CTkOptionMenu(menuparent,variable=ctkvar,values=values,corner_radius=ApplicationTheme.BUTTON_CORNER_RADIUS)
    var.widget=menu
    ctkvar.set(initial_value)
    if refresh_function:
        menuparent.columnconfigure([0],weight=1)
        fullpath = Path().absolute() / "ui_pages/ui_widgets/assets/refresh_label.png"
        pilimg = Image.open(fullpath.as_posix())
        refresh_image = ctk.CTkImage(light_image=pilimg,size=(20,20))
        refresh_button = ctk.CTkButton(menuparent,text=None,image=refresh_image,command=refresh_function,width=21)
        menu.grid(row=0,column=0,padx=0,pady=0,sticky="nsew")
        refresh_button.grid(row=0,column=1,padx=(10,0),pady=0,sticky="nse")
    else:
        menuparent.columnconfigure(0,weight=1)
        menu.grid(row=0,column=0,columnspan=2,padx=0,pady=0,sticky="nsew")
    return lbl,var,menuparent

@_makerfunction
def make_segmented_button(frame: ctk.CTkFrame,
                           name: str,
                           setting: Settings,
                           initial_value: str,
                           map_fun: Callable[[str],None]|None = None,
                           values: list[str] = ["Please Select a Value"],
                           command: Callable[[None],None] = lambda: None,
                           **kwargs
                           ) -> tuple[ctk.CTkLabel,SettingVariable,ctk.CTkFrame]:
    lbl = ctk.CTkLabel(frame,text=name)
    ctkvar = ctk.StringVar(value=initial_value)
    var = SettingVariable(ctkvar,setting,map_fun=map_fun)
    segmentparent = ctk.CTkFrame(frame)
    button = ctk.CTkSegmentedButton(segmentparent,variable=ctkvar,values=values,command=command)
    ctkvar.set(initial_value)
    segmentparent.columnconfigure(0,weight=1)
    button.grid(row=0,column=0,padx=0,pady=0,sticky="nsew")
    return lbl,var,segmentparent

def make_and_grid(maker_function: _MakerFunction,
                   frame: ctk.CTkFrame,
                   name: str, 
                   setting: Settings,
                   initial_value: str,
                   grid_row: int,
                   map_fun: Callable[[str],Any]|None = None,
                   **kwargs) -> "SettingVariable":
    lbl,var,widgetframe = maker_function(frame,name,setting,initial_value,map_fun=map_fun,**kwargs)
    lbl.grid(row=grid_row,column=0,padx=10,pady=5,sticky="nsew")
    widgetframe.grid(row=grid_row,column=1,padx=10,pady=5,sticky="ew")
    return var

def make_and_group(maker_function: _MakerFunction,
                    frame: ctk.CTkFrame,
                    name: str,
                    setting: Settings,
                    initial_value: str,
                    group: "WidgetGroup",
                    map_fun: Callable [[str],Any] | None = None,
                    **kwargs
                    ) -> "SettingVariable":
    lbl,var,widgetframe = maker_function(frame,name,setting,initial_value,map_fun=map_fun,**kwargs)
    group.add_widget(lbl,0)
    group.add_widget(widgetframe,1)
    group.add_var(var)
    group.nextrow()
    return var

class _ValidatorFunction(Protocol):
    def __call__(a: str,allow_true = True) -> bool: ...

def validator_function(fn: _ValidatorFunction) -> _ValidatorFunction: return fn
