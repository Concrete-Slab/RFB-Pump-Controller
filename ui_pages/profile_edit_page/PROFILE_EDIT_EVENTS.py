from dataclasses import dataclass
from pathlib import Path
from ui_root import event_group

@event_group
class MEvents:
    class RequestPorts:
        """Signals that the user wishes to refresh the serial port list"""
    @dataclass
    class UpdatePorts:
        """Signals the controller has retrieved the serial port list"""
        ports: list[str]
        descriptions: list[str]
    @dataclass
    class RequestProfile:
        """Signals a request for the current profile info from the UI"""
    @dataclass
    class UpdateManualProfile:
        """Signals the controller has retrieved manually-coded profile information"""
        name: str
        serial_port: str
        num_pumps: str
    @dataclass
    class UpdateAutoprofile:
        name: str
        serial_port: str
        pin_assignments: list[tuple[int,int]]
        code_location: str|None = None
        device_name: str|None = None
    @dataclass
    class SaveManualProfile:
        """Signals the user wishes to save the current manually-coded profile and return"""
        name: str
        serial_port: str
        num_pumps: str
    @dataclass
    class SaveAutoProfile:
        """Signals the user wishes to save the current auto-coded profile and return"""
        name: str
        serial_port: str
        pin_assignments: list[tuple[int,int]]
        code_location: str|None = None
        device_name: str|None = None
    @dataclass
    class GenerateCode:
        """Signals the user wishes to generate code based on pin assignments and profile name"""
        name: str
        pin_assignments: list[tuple[int,int]]
    @dataclass
    class NotifyGenerated:
        "Notifies that code has been generated and provides its filepath"
        code_path: Path
    class Cancel:
        """Signals the user wishes to cancel the modifications and return"""
    @dataclass
    class Error:
        """Signals an error has occurred"""
        err: BaseException
    