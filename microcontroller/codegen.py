from dataclasses import dataclass
from pathlib import Path
from support_classes import open_local, get_path
import os
import copy

PREAMBLE_PATH = Path(__file__).parent/"preamble.cpp"
MAIN_CODE_PATH = Path(__file__).parent/"main_code.cpp"
CODEGEN_PATH = Path("codegen")
SUPPORTED_EXTENSIONS = ["cpp"]

@dataclass
class PinDefs:
    tacho_pin: int
    pwm_pin: int

    @staticmethod
    def from_tuple(tp: tuple[int,int]) -> "PinDefs":
        return PinDefs(tacho_pin=tp[0],pwm_pin=tp[1])
    def as_tuple(self) -> tuple[int,int]:
        return [self.tacho_pin,self.pwm_pin]

def generate_code(name: str, pump_list: list[PinDefs]) -> Path:
    
    pump_cpp_arr = f"PumpConnection pumps[{len(pump_list)}] = "+"{"
    for pump in pump_list:
        pump_cpp_arr += f"PumpConnection({pump.pwm_pin},{pump.tacho_pin}),"
    pump_cpp_arr = pump_cpp_arr[:-1]+"}"
    
    #TODO insert this line into the pre-prepared code
    with open(PREAMBLE_PATH,"r") as f:
        preamble = f.read()
    with open(MAIN_CODE_PATH,"r") as f:
        main_code = f.read()

    code_out = f"""{preamble}
{pump_cpp_arr}

{main_code}
"""
    return _save_code(name,code_out)

def _save_code(filename: str, code: str):
    filename_parts = filename.split(".")
    if len(filename_parts) == 1:
        filename_parts += [".cpp"]
    pwd_test = CODEGEN_PATH/"".join(filename_parts)
    i=1
    while os.path.exists(get_path(pwd_test)):
        filename_parts[-2] = filename_parts[-2] + f"({i})"
        i += 1
        filename = "".join(filename_parts)
        pwd_test = CODEGEN_PATH/filename
    with open_local(pwd_test,"w") as f:
        f.write(code)
    return get_path(pwd_test)
    

def maybe_generate_code(name: str, pump_list: list[PinDefs], compare_to: list[PinDefs] = None, silent=False) -> Path|None:
    if len(pump_list)<1:
        ## no pin assignments - code can't be generated
        if silent:
            return
        raise CodeGenerationException("Codegen failed - pump list is empty")
    if compare_to is None:
        ## nothing to check against for modifications - always generate
        return generate_code(name,pump_list)
    ## check for modifications and only re-generate if they exist

    if len(pump_list) != len(compare_to):
        return generate_code()
    for (new,original) in zip(pump_list,compare_to):
        if new.pwm_pin != original.pwm_pin or new.tacho_pin != original.tacho_pin:
            return generate_code()
    if silent:
        return
    raise CodeGenerationException("Generated code is identical to already existing code")

class CodeGenerationException(BaseException):
    pass


# def copy_custom_code(custom_path: Path|str, num_pumps: int):
#     if isinstance(custom_path, str):
#         custom_path = Path(custom_path)
#     if num_pumps<1:
#         raise ValueError("You must use at least 1 pump")
#     # check for errors in opening
#     with open(custom_path,"r") as f:
#         pass

