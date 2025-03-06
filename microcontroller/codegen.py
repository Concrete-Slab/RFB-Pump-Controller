from dataclasses import dataclass
from pathlib import Path
from support_classes import open_local, get_path, PumpConfig
from enum import Enum
import os

PREAMBLE_PATH = Path(__file__).parent/"preamble.cpp"
MAIN_CODE_PATH = Path(__file__).parent/"main_code.cpp"
NAME_VALUE_FUNCTION_PATH = Path(__file__).parent/"name_value_speeds.cpp"
COMMA_SEPARATED_FUNCTION_PATH = Path(__file__).parent/"comma_separated_speeds.cpp"
CODEGEN_PATH = Path("codegen")
SUPPORTED_EXTENSIONS = ["ino","cpp"]

class SpeedFormats(Enum):
    COMMA_SEPARATED = "comma_separated"
    """Speeds are sent in the format a_speed,b_speed,c_speed,...
    Less serial bytes and less processing, but prone to errors if computer code and micro code are not exactly matched"""
    NAME_VALUE = "name_value"
    """Speeds are sent in the format <pump_name,pump_speed><pump_name,pump_speed>...
    Requires more processing but is robust to discrepancies in list ordering between computer and microcontroller"""


@dataclass
class PinDefs:
    tacho_pin: int
    pwm_pin: int

    @staticmethod
    def from_tuple(tp: tuple[int,int]) -> "PinDefs":
        return PinDefs(tacho_pin=tp[0],pwm_pin=tp[1])
    def as_tuple(self) -> tuple[int,int]:
        return [self.tacho_pin,self.pwm_pin]

def generate_code(name: str, pump_list: list[PinDefs], spd_format: SpeedFormats = SpeedFormats.COMMA_SEPARATED) -> Path:
    
    # Pump array initialisation line
    pump_cpp_arr = f"PumpConnection pumps[{len(pump_list)}] = "+"{"
    for i,pump in enumerate(pump_list):
        pump_cpp_arr += f"PumpConnection({pump.pwm_pin},{pump.tacho_pin},'{PumpConfig.allowable_values[i]}'),"
    pump_cpp_arr = pump_cpp_arr[:-1]+"};"

    # ISR function names and definition lines
    ISR_funs: dict[str,str] = {}
    for i in range(0,len(pump_list)):
        ISR_funs = {**ISR_funs,f"ISR_{i}":f"void ISR_{i}(){{ pumps[{i}].isr(); }}"}
    ISR_defs = "\n".join(ISR_funs.values())
    ISR_array_inner = "*"+",*".join(ISR_funs.keys())
    ISR_array = f"ISRPointer isrFuns[numPumps] = {{{ISR_array_inner}}};"

    match spd_format:
        case SpeedFormats.COMMA_SEPARATED:
            spd_filename = COMMA_SEPARATED_FUNCTION_PATH
        case SpeedFormats.NAME_VALUE:
            spd_filename = NAME_VALUE_FUNCTION_PATH
    
    with open(spd_filename,"r") as f:
        spd_function = f.read()
    with open(PREAMBLE_PATH,"r") as f:
        preamble = f.read()
    with open(MAIN_CODE_PATH,"r") as f:
        main_code = f.read()

    code_out = f"""
{preamble}
const unsigned int numPumps = {len(pump_list)};
{pump_cpp_arr}

{ISR_defs}

{ISR_array}

{spd_function}

{main_code}
"""
    return _save_code(name,code_out)

def _save_code(filename: str, code: str):
    filename_parts = filename.split(".")

    if len(filename_parts) == 1:
        filename_parts += ["ino"]

    def get_pwd():
        if filename_parts[-1] == "ino":
            # arduino sketch requires a parent directory with the same name
            pwd = CODEGEN_PATH/filename_parts[-2]/".".join(filename_parts)
        else:
            # otherwise, no need to have parent directory
            pwd = CODEGEN_PATH/".".join(filename_parts)
        return pwd
    i=1
    part_before_extension = filename_parts[-2]
    pwd_test = get_pwd()
    while os.path.exists(get_path(pwd_test)):
        filename_parts[-2] = part_before_extension + f"_{i}"
        i += 1
        pwd_test = get_pwd()
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

