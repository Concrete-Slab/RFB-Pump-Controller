import customtkinter as ctk

from ui_pages.ui_widgets.themes import ApplicationTheme
from .PROFILE_MANAGER_EVENTS import PrEvents
from ui_root import UIController


class ProfileManagerPage(ctk.CTkFrame):

    def __init__(self,master: ctk.CTkFrame, controller: UIController):

        super().__init__(master)
        
        self.controller = controller

        self.__profile_names = []
        
        
        self.__profiles_frame = ctk.CTkFrame(self)
        self.__profiles_frame.columnconfigure([1,2],weight=0,uniform="edit_delete")
        self.__profiles_frame.columnconfigure(0,weight=1)

        self._status_var = ctk.StringVar(value="Edit, Delete, or Create a Profile")
        self._status_lbl = ctk.CTkLabel(self,textvariable=self._status_var)

        self._name_lbl = ctk.CTkLabel(self.__profiles_frame,text="Profile Name")
        self._option_lbl = ctk.CTkLabel(self.__profiles_frame,text="Options")
        self._name_lbl.grid(row=0,column=0,**ApplicationTheme.GRID_STD)
        self._option_lbl.grid(row=0,column=1,columnspan=2,**ApplicationTheme.GRID_STD)

        back_button = ctk.CTkButton(self,text="Back",command=lambda: self.controller.notify_event(PrEvents.Back()))
        new_button = ctk.CTkButton(self,text="New Profile",command=lambda: self.controller.notify_event(PrEvents.NewProfile()))

        self.columnconfigure([0,1],weight=1,uniform="base_buttons")
        self.rowconfigure([1],weight=1)
        self.rowconfigure([0,2],weight=1)

        self._status_lbl.grid(row=0,column=0,columnspan=2,**ApplicationTheme.GRID_STD)
        self.__profiles_frame.grid(row=1,column=0,columnspan=2,**ApplicationTheme.GRID_STD)
        back_button.grid(row=2,column=0,padx=10,pady=5,sticky="nsw")
        new_button.grid(row=2,column=1,padx=10,pady=5,sticky="nse")
        
        self.controller.add_listener(PrEvents.UpdateProfiles,self.__update_profiles)
        self.controller.add_listener(PrEvents.Error,self.__on_error)

        self.controller.notify_event(PrEvents.RequestProfiles())

    def __on_error(self, error_event: PrEvents.Error):
        self._status_var.set(f"Error: {str(error_event.err)}")
        self._status_lbl.configure(text_color=ApplicationTheme.ERROR_COLOR)

    def __update_profiles(self, event: PrEvents.UpdateProfiles):
        new_profiles = event.profile_list
        if set(self.__profile_names) != set(new_profiles):
            for child in self.__profiles_frame.winfo_children():
                if child != self._name_lbl and child!=self._option_lbl:
                    child.grid_forget()
            for i,profile_name in enumerate(new_profiles):
                self.__create_profile_widget(profile_name,i+1)
        
        if len(new_profiles)>0:
            self.__profiles_frame.rowconfigure(list(range(0,len(new_profiles))),weight=1,uniform="profiles")
        else:
            self._name_lbl.grid_forget()
            self._option_lbl.grid_forget()
            if len(self.__profile_names)>0:
                self.__profiles_frame.rowconfigure(list(range(1,len(self.__profile_names)+1)),weight=0)
            lbl = ctk.CTkLabel(self.__profiles_frame,text="No profiles found!")
            lbl.grid(row=0,column=0,columnspan=3,padx=0,pady=0,sticky="nsew")
        self.__profile_names = new_profiles
        
        

    def __create_profile_widget(self,profile_name,rownum):
        lbl = ctk.CTkLabel(self.__profiles_frame, text=profile_name)
        edit = ctk.CTkButton(self.__profiles_frame,text="Edit",command=lambda: self.controller.notify_event(PrEvents.EditProfile(profile_name)))
        delete = ctk.CTkButton(self.__profiles_frame,text="Delete",command=lambda: self.controller.notify_event(PrEvents.DeleteProfile(profile_name)))

        lbl.grid(row=rownum, column=0, **ApplicationTheme.GRID_STD)
        edit.grid(row=rownum, column=1, **ApplicationTheme.GRID_STD)
        delete.grid(row=rownum, column=2, **ApplicationTheme.GRID_STD)
