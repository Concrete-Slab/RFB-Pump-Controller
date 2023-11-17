import customtkinter as ctk
from typing import Any
from .UIController import UIController
from .PAGE_EVENTS import PSEvents


class PortSelectPage(ctk.CTkFrame):
    BOX_WIDTH = 300
    BOX_HEIGHT = 300
    DEFAULT_PORT_MESSAGE = "Select Serial Port"
    DEFAULT_INTERFACE_MESSAGE = "Select Interface"
    DEFAULT_PROMPT = "Configure the serial interface to Teensy 3.5"

    def __init__(self, parent, controller: UIController, *args, starting_prompt: str = DEFAULT_PROMPT, **kwargs):
        super().__init__(parent,width=PortSelectPage.BOX_WIDTH,height=PortSelectPage.BOX_HEIGHT)
        self.interfaces = [PortSelectPage.DEFAULT_INTERFACE_MESSAGE]
        self.ports = [PortSelectPage.DEFAULT_PORT_MESSAGE]

        self.selected_interface = ctk.StringVar(value=self.interfaces[0])
        self.interface_menu = ctk.CTkOptionMenu(self,variable=self.selected_interface,values=self.interfaces)
        self.selected_interface.trace_add("write",self.__place_interface)
        
        self.selected_port = ctk.StringVar(value=self.ports[0])
        self.ports_menu = ctk.CTkOptionMenu(self,variable=self.selected_port,values=self.ports)

        self.localhost_port = ctk.StringVar(value="8000")
        self.localhost_entry = ctk.CTkEntry(self,textvariable=self.localhost_port,validate="key",validatecommand=(self.register(PortSelectPage.__validate), '%P'))

        self.status = ctk.StringVar(value=starting_prompt)
        self.status_label = ctk.CTkLabel(self,textvariable=self.status)

        self.confirm_button = ctk.CTkButton(self,text="Confirm",command=self.__send_config)

        # Connect controller and UI
        self.UIController = controller

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


        # Place the widgets onto the screen
        self.columnconfigure([0,1,2,3],weight=1,uniform="col")
        self.status_label.grid(row=0,column=0,columnspan=3,padx=10,pady=10,sticky="nsew")
        self.__place_interface()
        self.ports_menu.grid(row=1,column=2,columnspan=2,padx=10,pady=10,sticky="nsew")
        self.confirm_button.grid(row=2,column=3,padx=10,pady=10,sticky="nsew")
        
    def __update_ports(self,newPorts:list[str],descriptions:list[str]):
        self.ports = [PortSelectPage.DEFAULT_PORT_MESSAGE]+newPorts
        port_text = self.ports
        for i in range(1,len(port_text)):
            port_text[i] = f"{self.ports[i]} - {descriptions[i-1]}"
        prevSelection = self.selected_port.get()
        if prevSelection not in self.ports:
            self.selected_port.set(value=self.ports[0])
        self.ports_menu.configure(require_redraw=True,values=port_text)

    def __update_interfaces(self,newInterfaces,requiredkwargs: dict[str,Any]):
        self.interfaces = [PortSelectPage.DEFAULT_INTERFACE_MESSAGE]+newInterfaces
        prevSelection = self.selected_interface.get()
        if prevSelection not in self.interfaces:
            self.selected_interface.set(value=self.interfaces[0])
        self.interface_menu.configure(require_redraw=True,values=self.interfaces)

    def __send_config(self):
        if self.confirm_button._state != ctk.DISABLED:
            def get_port_from_desc(selected_port):
                    for port in self.ports:
                        if port.startswith(selected_port):
                            return selected_port
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
            self.interface_menu.grid(row=1,column=0,columnspan=1,sticky="nsew",padx=10,pady=10)
            self.localhost_entry.grid(row=1,column=1,columnspan=1,sticky="nsew",padx=10,pady=10)
        else:
            self.localhost_entry.grid_remove()
            self.interface_menu.grid(row=1,column=0,columnspan=2,sticky="nsew",padx=10,pady=10)

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
