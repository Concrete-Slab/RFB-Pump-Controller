import customtkinter as ctk
from typing import Any
from pathlib import Path
from PIL import Image
from support_classes.settings_interface import Settings, read_settings
from .UIController import UIController
from .PAGE_EVENTS import PSEvents
import copy

class PortSelectPage(ctk.CTkFrame):
    BOX_WIDTH = 300
    BOX_HEIGHT = 300
    DEFAULT_PORT_MESSAGE = "Select Serial Port"
    DEFAULT_INTERFACE_MESSAGE = "Select Interface"
    DEFAULT_PROMPT = "Configure the serial interface to Teensy 3.5"

    def __init__(self, parent, controller: UIController, *args, starting_prompt: str = DEFAULT_PROMPT, **kwargs):
        super().__init__(parent,width=PortSelectPage.BOX_WIDTH,height=PortSelectPage.BOX_HEIGHT)

        previous_choices = read_settings(Settings.RECENT_SERIAL_PORT,Settings.RECENT_SERIAL_INTERFACE)
        previous_port: str|None = previous_choices[Settings.RECENT_SERIAL_PORT]
        previous_interface: str|None = previous_choices[Settings.RECENT_SERIAL_INTERFACE]

        if previous_port is None:
            self.ports = [PortSelectPage.DEFAULT_PORT_MESSAGE]
        else:
            self.ports = [previous_port]
        previous_port = self.ports[0]

        if previous_interface is None:
            self.interfaces = [PortSelectPage.DEFAULT_INTERFACE_MESSAGE]
        else:
            self.interfaces = previous_interface


        # ------------- LAUNCH OPTIONS ------------------
        self.options_frame = ctk.CTkFrame(self)
        self.options_frame.rowconfigure([0],weight=1,uniform="row")
        self.options_frame.columnconfigure([0,3],weight=1)
        self.options_frame.columnconfigure([1,2],weight=1,uniform="optionscol")

        self.selected_interface = ctk.StringVar(value=self.interfaces[0])
        self.interface_label = ctk.CTkLabel(self.options_frame,text="Serial Interface")
        self.interface_menu = ctk.CTkOptionMenu(self.options_frame,variable=self.selected_interface,values=self.interfaces)
        self.selected_interface.trace_add("write",self.__place_interface)
        
        self.selected_port = ctk.StringVar(value=self.ports[0])
        self.port_label = ctk.CTkLabel(self.options_frame,text="Serial Port")
        self.ports_menu = ctk.CTkOptionMenu(self.options_frame,variable=self.selected_port,values=self.ports)
        self.port_label.grid(row=0,column=0,padx=10,pady=0,sticky="nsew")
        self.ports_menu.grid(row=0,column=1,columnspan=2,padx=10,pady=0,sticky="nsew")

        self.localhost_port = ctk.StringVar(value="8000")
        self.localhost_entry = ctk.CTkEntry(self.options_frame,textvariable=self.localhost_port,validate="key",validatecommand=(self.register(PortSelectPage.__validate), '%P'))
        
        fullpath = Path().absolute() / "ui_pages/ui_widgets/assets/refresh_label.png"
        pilimg = Image.open(fullpath.as_posix())
        refresh_image = ctk.CTkImage(light_image=pilimg,size=(20,20))
        self.refresh_button = ctk.CTkButton(self.options_frame,text=None,image=refresh_image,command=lambda *args: self.UIController.notify_event(PSEvents.UPDATE_PORTS),width=21)
        self.refresh_button.grid(row=0,column=3,padx=0,pady=0,sticky="nsew")

        self.options_frame.grid(row=1,column=0,columnspan=2,padx=10,pady=5,sticky="nsew")

        # ------------ Surrounding Widgets --------------------
        self.columnconfigure([0,1],weight=1)
        self.status = ctk.StringVar(value=starting_prompt)
        self.status_label = ctk.CTkLabel(self,textvariable=self.status)
        self.status_label.grid(row=0,column=0,columnspan=2,padx=10,pady=5,sticky="nsew")

        self.confirm_button = ctk.CTkButton(self,text="Confirm",command=self.__send_config)
        self.confirm_button.grid(row=2,column=1,padx=10,pady=5,sticky="nse")

        self.advanced_var = ctk.StringVar(value="More")
        self.advanced_button = ctk.CTkButton(self,textvariable=self.advanced_var,command=self.__showhide_interfaces)
        self.advanced_button.grid(row=2,column=0,padx=10,pady=5,sticky="nsw")

        # Connect controller and UI
        self.UIController = controller

        self.__show_advanced_settings = not self.UIController.debug

        # Add event listeners:
        # when the controller finds new ports, update the UI
        self.UIController.add_listener(PSEvents.NEW_PORTS,self.__update_ports)
        # when the controller finds new interfaces, update the UI
        self.UIController.add_listener(PSEvents.NEW_INTERFACES,self.__update_interfaces)
        # when the controller errors, update the UI
        self.UIController.add_listener(PSEvents.ERROR,self.__on_error)

        # Get data from the controller
        # Get the current interfaces and update the UI
        self.UIController.notify_event(PSEvents.UPDATE_INTERFACES)
        # Get the current ports and update the UI
        self.UIController.notify_event(PSEvents.UPDATE_PORTS)

        self.__showhide_interfaces()
        
    def __update_ports(self,newPorts:list[str],descriptions:list[str]):
        if len(newPorts)<1:
            self.ports = [PortSelectPage.DEFAULT_PORT_MESSAGE]
        else:
            self.ports = newPorts
        # convert ports to ports with description
        port_text = copy.copy(self.ports)
        for i in range(0,len(port_text)):
            port_text[i] = f"{self.ports[i]} - {descriptions[i]}" if len(descriptions[i])>0 else self.ports[i] 
        
        # check if the previously selected port is still in the list
        prevSelection = self.selected_port.get()
        # the first prevSelection will be from settings and contain only a port:
        if prevSelection in self.ports:
            index = self.ports.index(prevSelection)
            prevSelection = port_text[index]
            self.selected_port.set(value=prevSelection)
        # if previous is not in new list, set to the start of the new list
        if prevSelection not in port_text:
            self.selected_port.set(value=port_text[0])
        # configure the menu with the new values
        self.ports_menu.configure(require_redraw=True,values=port_text)

    def __update_interfaces(self,newInterfaces,requiredkwargs: dict[str,Any]):
        if len(newInterfaces)<1:
            self.interfaces = [PortSelectPage.DEFAULT_INTERFACE_MESSAGE]
        else:
            self.interfaces = newInterfaces
        prevSelection = self.selected_interface.get()
        if prevSelection not in self.interfaces:
            self.selected_interface.set(value=self.interfaces[0])
        self.interface_menu.configure(require_redraw=True,values=self.interfaces)

    def __send_config(self):
        if self.confirm_button._state != ctk.DISABLED:
            def get_port_from_desc(selected_port: str):
                    for port in self.ports:
                        if selected_port.startswith(port):
                            return port
                    return None
            port_desc = self.selected_port.get()
            port = get_port_from_desc(port_desc)
            interface = self.selected_interface.get()
            local_port = self.localhost_port.get()
            if port is None or interface == PortSelectPage.DEFAULT_INTERFACE_MESSAGE or (local_port=="" and interface=="Node Forwarder"):
                
                self.status.set("Please select a valid serial/local port and interface")
                self.UIController.notify_event(PSEvents.UPDATE_PORTS)
            else:
                
                self.confirm_button.configure(state=ctk.DISABLED)
                self.UIController.notify_event(PSEvents.SERIAL_CONFIG,interface,port,local_port=local_port)

    def __on_error(self,error: BaseException):
        self.status.set(str(error))
        self.confirm_button.configure(state="normal")
        self.UIController.notify_event(PSEvents.UPDATE_PORTS)

    def __place_interface(self,*args):
        #TODO make this independent of Node Forwarder: make it place a box for each required argument in the supplied interface!
        new_interface = self.selected_interface.get()
        if new_interface == "Node Forwarder"or new_interface == "Dummy Node Forwarder":
            self.options_frame.columnconfigure([1,2],weight=1,uniform="optionscol2")
            self.options_frame.rowconfigure([0,1],weight=1)
            self.interface_menu.grid(row=1,column=1,columnspan=1,sticky="nsew",padx=10,pady=(10,0))
            self.localhost_entry.grid(row=1,column=2,columnspan=1,sticky="nsew",padx=10,pady=(10,0))
        else:
            self.options_frame.columnconfigure([1],weight=1)
            self.options_frame.rowconfigure([0],weight=1)
            self.options_frame.rowconfigure([1],weight=0)
            self.localhost_entry.grid_remove()
            self.interface_menu.grid(row=1,column=1,columnspan=2,sticky="nsew",padx=10,pady=(10,0))

    def __showhide_interfaces(self):
        if self.__show_advanced_settings:
            # remove advanced settings
            self.localhost_entry.grid_remove()
            self.interface_menu.grid_remove()
            self.interface_label.grid_remove()
            self.advanced_var.set("More")
        else:
            # add advandec settings
            self.interface_label.grid(row=1,column=0,padx=10,pady=(10,0),sticky="nsew")
            self.__place_interface()
            self.advanced_var.set("Less")
        self.__show_advanced_settings = not self.__show_advanced_settings


    @staticmethod
    def __validate(p: str):
        if p.isdigit():
            try:
                int(p)
                return True
            except TypeError:
                return False
        elif p == "":
            return True
        return False
