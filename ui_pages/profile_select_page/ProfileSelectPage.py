import customtkinter as ctk
from ui_root import UIController
from .PROFILE_SELECT_EVENTS import PSEvents
from ..ui_layout import ApplicationTheme

class ProfileSelectPage(ctk.CTkFrame):
    BOX_WIDTH = 300
    BOX_HEIGHT = 300
    DEFAULT_PROMPT = "To proceed to pump control, configure the microcontroller setup"
    DEFAULT_PROFILE_MESSAGE = "Select Microcontroller Profile"

    def __init__(self, parent, controller: UIController, *args, starting_prompt: str = DEFAULT_PROMPT, **kwargs):
        super().__init__(parent, width=ProfileSelectPage.BOX_WIDTH,height=ProfileSelectPage.BOX_HEIGHT)

        self.UIcontroller = controller
        
        profiles = [ProfileSelectPage.DEFAULT_PROFILE_MESSAGE]

        self._options_frame = ctk.CTkFrame(self)
        self._options_frame.columnconfigure([0],weight=0)
        self._options_frame.columnconfigure([1],weight=1)

        ## ---------------- Microcontroller Profile Selection (options frame) -----------------------
        micro_lbl = ctk.CTkLabel(self._options_frame,text="Microcontroller Profile")
        self._profile_var = ctk.StringVar(value=profiles[0])
        self._micro_dropdown = ctk.CTkOptionMenu(self._options_frame,variable=self._profile_var,values = profiles)
        self._profile_var.trace_add("write", self.__update_choice)

        micro_lbl.grid(row=0,column=0,**ApplicationTheme.GRID_STD)
        self._micro_dropdown.grid(row=0,column=1,**ApplicationTheme.GRID_STD)
        
        ## ---------------- Surrounding Widgets (entire frame) -----------------------
        self._confirm_button = ctk.CTkButton(self,text="Confirm",command=self.__send_config)
        self._new_button = ctk.CTkButton(self,text="Manage Profiles",command=self.__on_manage)
        self._status_var = ctk.StringVar(value=starting_prompt)
        self._status_lbl = ctk.CTkLabel(self,textvariable=self._status_var)

        self.columnconfigure([0,1],weight=1)
        self._status_lbl.grid(row=0,column=0,columnspan=2,**ApplicationTheme.GRID_STD)
        self._options_frame.grid(row=1,column=0,columnspan=2,**ApplicationTheme.GRID_STD)
        self._confirm_button.grid(row=2,column=0,padx=10,pady=5,sticky="nsw")
        self._new_button.grid(row=2,column=1,padx=10,pady=5,sticky="nse")

        self.UIcontroller.add_listener(PSEvents.UpdateProfiles, self.__update_profiles)
        self.UIcontroller.add_listener(PSEvents.NotifyError, self.__on_error)
        self.UIcontroller.add_listener(PSEvents.NotifyInfo,self.__on_info)

        self.UIcontroller.notify_event(PSEvents.RequestProfiles())

    def __on_manage(self):
        self.UIcontroller.notify_event(PSEvents.ManageProfiles())

    def __update_profiles(self, event: PSEvents.UpdateProfiles):
        new_profiles = event.profiles
        if self._selected_profile not in new_profiles:
            new_profiles = [self.DEFAULT_PROFILE_MESSAGE,*new_profiles]
            self._profile_var.set(self.DEFAULT_PROFILE_MESSAGE)
        self._micro_dropdown.configure(values=new_profiles)
        if event.prev_profile is not None:
            self._profile_var.set(event.prev_profile)

    @property
    def _selected_profile(self):
        return self._profile_var.get()
    
    def __update_choice(self,*args):
        if self._selected_profile == self.DEFAULT_PROFILE_MESSAGE:
            state = ctk.DISABLED
        else:
            state = ctk.NORMAL
        self._confirm_button.configure(state=state)
        self._new_button.configure(state=ctk.NORMAL)
        self._micro_dropdown.configure(state=ctk.NORMAL)
        pass

    def __on_info(self, event: PSEvents.NotifyInfo):
        self._status_lbl.configure(text_color=ApplicationTheme.WHITE)
        self._status_var.set(f"{event.info}...")


    def __send_config(self):
        selected_profile = self._profile_var.get()
        if selected_profile == self.DEFAULT_PROFILE_MESSAGE:
            self._status_var.set("Please select a valid profile")
        else:
            self._confirm_button.configure(state=ctk.DISABLED)
            self._new_button.configure(state=ctk.DISABLED)
            self._micro_dropdown.configure(state=ctk.DISABLED)
            self.UIcontroller.notify_event(PSEvents.ConfirmProfile(self._profile_var.get()))

    def __on_error(self, err: PSEvents.NotifyError):
        self.__update_choice()
        self._status_var.set(f"Error: {str(err.err)}")
        self._status_lbl.configure(text_color=ApplicationTheme.ERROR_COLOR)