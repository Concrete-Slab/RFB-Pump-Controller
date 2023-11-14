

class ApplicationTheme:
    FONT = 'Helvetica'
    MAIN_FONT_SIZE = 60
    INPUT_FONT_SIZE = 26
    LABEL_FONT_SIZE = 35
    SWITCH_FONT_SIZE = 18
    BUTTON_CORNER_RADIUS = 6
    GREEN = '#50BFAB'
    DARK_GREEN = '#3A8A7B'
    WHITE = '#F2F2F2'
    BLACK = '#1F1F1F'
    LIGHT_GRAY = '#E8E8E8'
    GRAY = '#D9D9D9'
    TITLE_HEX_COLOR = 0X00ABBF50

    def __init__(self, main_font_size=MAIN_FONT_SIZE, input_font_size=INPUT_FONT_SIZE,

                 label_font_size=LABEL_FONT_SIZE, button_corner_radius=BUTTON_CORNER_RADIUS, title_color=TITLE_HEX_COLOR):
        self.main_font_size = main_font_size
        self.input_font_size = input_font_size
        self.label_font_size = label_font_size
        self.button_corner_radius = button_corner_radius
        self.title_color = title_color


