import pyduinocli as pdc
from dataclasses import dataclass

class ArduinoCLIException(BaseException):
    pass

class ArduinoInterface:
    @dataclass
    class BoardProps:
        fqbn: str
        ports: list[str]

    def __init__(self):
        self.adi = pdc.Arduino()
        try:
            self.adi.version()
        except FileNotFoundError:
            raise ArduinoCLIException("arduinocli installation not found")

    def get_boards(self):
        dict_out = self.adi.board.list()["result"]
        return dict_out

if __name__ == "__main__":
    a = ArduinoInterface()
    print(a.get_boards())
        

        