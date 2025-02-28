from dataclasses import dataclass
from ui_root import event_group

@event_group
class PrEvents:
    """Events for the profile management page"""
    class Back:
        """The user wishes to stop managing profiles and return to the previous page"""
    class NewProfile:
        """The user wishes to create a new profile"""
    @dataclass
    class EditProfile:
        """The user wishes to edit a given profile"""
        profile_name: str
    @dataclass
    class DeleteProfile:
        """The user wishes to delete a given profile"""
        profile_name: str
    class RequestProfiles:
        """The list of all profiles has been requested"""
    @dataclass
    class UpdateProfiles:
        """The list of all profiles has been fetched and stored in this event"""
        profile_list: list[str]
    @dataclass
    class Error:
        err: BaseException