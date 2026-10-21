import os
from model import *
from csv import DictReader
from model.text import add_color, draw_rich_text

SIGILS = dict()
TRAITS = dict()
SIGIL_DIR = GENERAL_ASSETS_DIR / "sigils"


def get_resized_image(img, height):
    return img.resize((int(img.width * (height / img.height)), height))


def get_outline_asset(path):
    if not os.path.exists(path):
        return path
    directory, filename = os.path.split(path)
    stem, ext = os.path.splitext(filename)
    outline_path = os.path.join(directory, f"{stem}_outline{ext}")
    if os.path.exists(outline_path):
        return outline_path
    return path


def write_description(x_offset, y_offset, starting_size, description_words, color, text_img, size_limit, shortened_format,
            config=DEFAULT_CONFIG, color_map=None):
    description_size = config["sigil_description_font_size"]
    font = ImageFont.truetype(ROOT / "data" / "fonts" / f"{config['font']}.TTF", description_size)
    color_map = color_map or (get_color_mapping("default") if any("{color:" in word for word in description_words) else {})
    description = " ".join(word for word in description_words if not (shortened_format and word == r"\n"))
    _, height, text_img = draw_rich_text(
        text_img, description, font, (0, y_offset), color,
        color_map, config, max_width=size_limit, first_line_offset=starting_size, line_offset=x_offset
    )
    return y_offset + height - description_size, text_img


class Sigil:

    def __init__(self, name: str, description: str, tags: list, is_trait: bool = False,
                 image: Image = None,short_image: Image = None, base_game_image: Image = None):
        self.name = name
        self.description = description
        self.token_needed = description.count("TOKEN")
        self.tags = tags
        self.tokens = []
        self.is_trait = is_trait
        self.image = image
        self.short_image = short_image
        self.base_game_image = base_game_image

    def copy(self):
        return Sigil(self.name, self.description, self.tags, self.is_trait, self.image, self.short_image, self.base_game_image)
    
    def addToken(self, token: object):
        self.tokens.append(token)
        self.image = None
        self.short_image = None

    def get_description(self):
        final_description = self.description
        for token in self.tokens:
            final_description = final_description.replace("TOKEN", str(token), 1)
        return final_description

    def sigilImage(self, color='black', config=DEFAULT_CONFIG):
        name = self.name.translate(str.maketrans("", "", " ',-!?"))
        path = SIGIL_DIR / f"{name}.png"
        if not config["allow_colored_sigils"] or color != "black":
            path = get_outline_asset(path)
        try:
            sigil_img = Image.open(path).convert("RGBA")
        except FileNotFoundError as e:
            path = SIGIL_DIR / "X.png"
            if not config["allow_colored_sigils"] or color != "black":
                path = get_outline_asset(path)
            sigil_img = Image.open(path).convert("RGBA")
        scale = config["sigil_img_scale"] / 100
        sigil_img = sigil_img.resize((round(sigil_img.width * scale), round(sigil_img.height * scale)))
        if color != 'black':
            add_color(sigil_img, color)
        return sigil_img

    def __draw_base_game(self, sigil_img, color, config, color_map):
        name_size = config["sigil_name_font_size"]
        image_space = config["sigil_img_space"]
        description_space = config["sigil_space"] - 5 - image_space
        font_path = ROOT / "data" / "fonts" / f"{config['font']}.TTF"
        heavyweight_font = ImageFont.truetype(font_path, name_size)
        text_img = Image.new("RGBA", (description_space, name_size), (0, 0, 0, 0))
        text_width, _, text_img = draw_rich_text(text_img, self.name, heavyweight_font, (0, 0), color, color_map, config)
        text_img = text_img.crop((0, 0, round(text_width), name_size))
        final_img_width = max(sigil_img.width, text_img.width)
        final_img_height = sigil_img.height + text_img.height + 5
        final_img = Image.new("RGBA", (final_img_width, final_img_height), (0, 0, 0, 0))

        final_img.paste(sigil_img, ((final_img_width - sigil_img.width) // 2, 0))
        final_img.paste(text_img, ((final_img_width - text_img.width) // 2, sigil_img.height + 5))
        return final_img

    @staticmethod
    def __get_trait_image(color, description_words, config, color_map):
        description_size = config["trait_description_font_size"]
        size_limit = config['sigil_space'] - 10
        text_img = Image.new("RGBA", (size_limit, description_size), (0, 0, 0, 0))
        heavyweight_font = ImageFont.truetype(ROOT / "data" / "fonts" / f"{config['font']}.TTF", description_size)
        _, _, text_img = draw_rich_text(text_img, " ".join(description_words), heavyweight_font, (0, 0), color, color_map, config, max_width=size_limit, align="center")
        return text_img

    def getImage(self, color='black', base_game: bool = False, shortened_format: bool = False, config=DEFAULT_CONFIG, color_map=None):
        name_size = config["sigil_name_font_size"]
        description_size = config["sigil_description_font_size"]
        image_space = config["sigil_img_space"]
        description_space = config["sigil_space"] - 5 - image_space
        font_path = ROOT / "data" / "fonts" / f"{config['font']}.TTF"
        description = self.get_description()
        has_dynamic_color = "{color:" in self.name or "{color:" in description
        if color_map is None:
            color_map = get_color_mapping("default") if has_dynamic_color else {}
        use_cache = config == DEFAULT_CONFIG
        if use_cache and base_game and self.base_game_image and color == "black" and not has_dynamic_color:
            return self.base_game_image
        if use_cache and shortened_format and self.short_image and color == "black" and not has_dynamic_color:
            return self.short_image
        if use_cache and not base_game and not shortened_format and self.image and color == "black" and not has_dynamic_color:
            return self.image

        if not self.is_trait:
            sigil_img = self.sigilImage(color, config)

        if base_game:
            if self.is_trait:
                image = Image.new("RGBA", (0, 0))
            else:
                image = self.__draw_base_game(sigil_img, color, config, color_map)
            if use_cache:
                self.base_game_image = image
            return image

        description_words = description.split()

        if self.is_trait:
            trait_image = self.__get_trait_image(color, description_words, config, color_map)
            if use_cache and not has_dynamic_color:
                self.image = trait_image
                self.base_game_image = self.image
            return trait_image

        heavyweight_font = ImageFont.truetype(font_path, name_size)
        text_img = Image.new("RGBA", (description_space, name_size), (0, 0, 0, 0))
        sigil_name = self.name + (":" if shortened_format else "")
        size, _, text_img = draw_rich_text(
            text_img, sigil_name, heavyweight_font, (0, 0), color, color_map, config
        )
        if shortened_format:
            # Draw sigil using shortened formatting
            y_offset, text_img = write_description(
                0, name_size - description_size - 1, size, description_words,
                color, text_img, description_space, shortened_format, config, color_map
            )
        else:
            # Draw sigil normally
            new_height = text_img.size[1] + name_size
            new_img = Image.new("RGBA", (description_space, new_height), (0, 0, 0, 0))
            new_img.paste(text_img, (0, 0))
            text_img = new_img
            heavyweight_font = ImageFont.truetype(font_path, description_size)
            size = description_size

            y_offset, text_img = write_description(
                description_size, name_size, size, description_words,
                color, text_img, description_space, shortened_format, config, color_map
            )

        text_height = y_offset + description_size
        final_img_height = max(text_height, sigil_img.height)
        final_img = Image.new("RGBA", (config['sigil_space'], final_img_height), (0, 0, 0, 0))
        final_img.paste(sigil_img, ((image_space - sigil_img.width) // 2, min((final_img_height - sigil_img.height) // 2, 10)))
        final_img.paste(text_img.crop((0, 0, text_img.width, text_height)), (image_space, (final_img_height - text_height) // 2))
        if use_cache and not has_dynamic_color:
            if shortened_format:
                self.short_image = final_img
            else:
                self.image = final_img
        return final_img


def add_sigil(csv_dict):
    global SIGILS
    SIGILS[csv_dict['Name']] = Sigil(
        csv_dict["Name"], 
        csv_dict["Description"], 
        csv_dict["Tags"]
    )

def add_trait(csv_dict):
    global TRAITS
    TRAITS[csv_dict['Name']] = Sigil(
        csv_dict["Name"], 
        csv_dict["Description"], 
        csv_dict["Tags"], 
        is_trait=True
    )
