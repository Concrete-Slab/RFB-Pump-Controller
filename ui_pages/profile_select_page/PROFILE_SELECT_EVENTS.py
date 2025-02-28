from dataclasses import dataclass
from ui_root import event_group

@event_group
class PSEvents:

    class RequestProfiles:
        """Profile list has been requested by user"""
        pass

    @dataclass
    class UpdateProfiles:
        """Profile list has been loaded and is ready to be displayed"""
        profiles: list[str]
        prev_profile: str|None

    class ManageProfiles:
        """User wishes to manage their profiles"""
        pass

    @dataclass
    class ConfirmProfile:
        """User wishes to load program with the selected profile"""
        profile: str

    @dataclass
    class NotifyError:
        """An error has occurred"""
        err: BaseException
