import os
from model import *
from csv import DictReader

SIGILS = dict()
TRAITS = dict()
SIGIL_IMG_SPACE = DEFAULT_CONFIG['sigil_img_space']
SIGIL_DESC_SPACE = DEFAULT_CONFIG['sigil_space'] - 5 - SIGIL_IMG_SPACE
SIGIL_NAME_SIZE = DEFAULT_CONFIG['sigil_name_font_size']
SIGIL_DESCRIPTION_SIZE = DEFAULT_CONFIG['sigil_description_font_size']
TRAIT_DESCRIPTION_SIZE = DEFAULT_CONFIG['trait_description_font_size']
SIGIL_DESC_ICON_SIZE = DEFAULT_CONFIG['sigil_description_icon_size']
TRAIT_DESC_ICON_SIZE = DEFAULT_CONFIG['trait_description_icon_size']
SIGIL_SCALE = DEFAULT_CONFIG["sigil_img_scale"] / 100


def get_resized_image(img, height):
    return img.resize((int(img.width * (height / img.height)), height))


def write_description(x_offset, y_offset, starting_size, description_words, color, text_img, size_limit, shortened_format):
    draw = ImageDraw.Draw(text_img)
    font = ImageFont.truetype(FONT, SIGIL_DESCRIPTION_SIZE)
    space_size = draw.textlength(" ", font=font)
    size = starting_size - (0 if shortened_format else space_size)

    def add_new_line():
        """Helper function to add a new line to the image."""
        nonlocal y_offset, text_img, draw
        y_offset += SIGIL_DESCRIPTION_SIZE
        new_height = text_img.size[1] + SIGIL_DESCRIPTION_SIZE
        new_img = Image.new("RGBA", (size_limit, new_height), (0, 0, 0, 0))
        new_img.paste(text_img, (0, 0))
        text_img = new_img
        draw = ImageDraw.Draw(text_img)

    for word in description_words:
        # If word contains icons, treat it as a composite block
        if "{" in word:
            sub_words = [x for s in word.split("{") for x in s.split("}")]
            components = []
            for i, sub_word in enumerate(sub_words):
                if not sub_word:
                    continue
                if i % 2 == 0:
                    components.append(("text", sub_word))
                else:
                    components.append(("icon", sub_word))

            # Measure total width of the block
            total_width = 0
            rendered_icons = []
            for kind, content in components:
                if kind == "text":
                    total_width += draw.textlength(content, font=font)
                else:
                    colon_id = content.index(":")
                    icon_type = "sigils" if "sigil" in content else "icons"
                    icon_name = content[colon_id + 1:]
                    icon_path = f"assets/general_assets/{icon_type}/{icon_name}.png"
                    if color != "black":
                        new_path = f"assets/general_assets/sigils/{icon_type}/{icon_name[:-1]}_outline.png"
                        if os.path.exists(new_path):
                            icon_path = new_path
                    try:
                        icon = get_resized_image(Image.open(icon_path), SIGIL_DESC_ICON_SIZE)
                    except FileNotFoundError:
                        icon = get_resized_image(Image.open("assets/general_assets/sigils/X.png"), SIGIL_DESC_ICON_SIZE)
                    if color != "black":
                        add_color(icon, color)
                    rendered_icons.append((content, icon))
                    total_width += icon.width

            # Check if fits on current line
            if size + total_width + space_size > size_limit:
                add_new_line()
                size = x_offset - space_size

            # Draw block directly
            cursor_x = size + space_size
            icon_index = 0
            for kind, content in components:
                if kind == "text":
                    draw.text((cursor_x, y_offset), content, fill=color, font=font)
                    cursor_x += draw.textlength(content, font=font)
                else:
                    _, icon = rendered_icons[icon_index]
                    text_img.paste(icon, (int(cursor_x), y_offset), icon)
                    cursor_x += icon.width
                    icon_index += 1

            size = cursor_x

        # Line jump
        elif word == "\\n":
            if not shortened_format:
                add_new_line()
                size = x_offset - space_size

        # Plain word
        else:
            word_width = draw.textlength(word, font=font)
            if size + word_width + space_size > size_limit:
                add_new_line()
                draw.text((x_offset, y_offset), word, fill=color, font=font)
                size = x_offset + word_width
            else:
                draw.text((size, y_offset), " " + word, fill=color, font=font)
                size += word_width + space_size

    return y_offset, text_img


def add_color(image: Image.Image, color):
    for x in range(image.width):
        for y in range(image.height):
            pixel_color = (color[0], color[1], color[2], image.getpixel((x, y))[3])
            image.putpixel((x, y), pixel_color)


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

    def sigilImage(self, color='black'):
        name = self.name.translate(str.maketrans("", "", " ',-!?"))
        path = f"assets/general_assets/sigils/{name}.png"
        if not DEFAULT_CONFIG["allow_colored_sigils"] or (color != "black" and "has_color" in self.tags):
            new_path = f"assets/general_assets/sigils/{name}_outline.png"
            if os.path.exists(new_path):
                path = new_path
        try:
            sigil_img = Image.open(path).convert("RGBA")
        except FileNotFoundError as e:
            sigil_img = Image.open("assets/general_assets/sigils/X.png").convert("RGBA")
        sigil_img = sigil_img.resize((round(sigil_img.width * SIGIL_SCALE), round(sigil_img.height * SIGIL_SCALE)))
        if color != 'black':
            add_color(sigil_img, color)
        return sigil_img

    def __draw_base_game(self, sigil_img, color):
        heavyweight_font = ImageFont.truetype(FONT, SIGIL_NAME_SIZE)
        text_img = Image.new("RGBA", (SIGIL_DESC_SPACE, SIGIL_NAME_SIZE), (0, 0, 0, 0))
        draw = ImageDraw.Draw(text_img)
        draw.text((0, 0), self.name, fill=color, font=heavyweight_font)

        text_img = text_img.crop((0, 0, round(draw.textlength(self.name, font=heavyweight_font)), SIGIL_NAME_SIZE))
        final_img_width = max(sigil_img.width, text_img.width)
        final_img_height = sigil_img.height + text_img.height + 5
        final_img = Image.new("RGBA", (final_img_width, final_img_height), (0, 0, 0, 0))

        final_img.paste(sigil_img, ((final_img_width - sigil_img.width) // 2, 0))
        final_img.paste(text_img, ((final_img_width - text_img.width) // 2, sigil_img.height + 5))
        return final_img

    @staticmethod
    def __get_trait_image(color, description_words):
        size_limit = DEFAULT_CONFIG['sigil_space'] - 10
        text_img = Image.new("RGBA", (size_limit, TRAIT_DESCRIPTION_SIZE), (0, 0, 0, 0))
        draw = ImageDraw.Draw(text_img)
        lengths = [0]
        words_per_phrase = [0]
        heavyweight_font = ImageFont.truetype(FONT, TRAIT_DESCRIPTION_SIZE)

        # Calculate x_offset for each step
        def add_width(width, added_width=None):
            if lengths[-1] + width > size_limit:
                lengths.append(width if added_width is None else added_width)
                words_per_phrase.append(1)
            else:
                lengths[-1] += width
                words_per_phrase[-1] += 1

        for i, word in enumerate(description_words):
            if "{" in word:
                if word[-1] != "}":
                    bracket_index = word.index("}") + 1
                    description_words.insert(i + 1, "HIB" + word[bracket_index:])
                    word = word[0:bracket_index]
                colon_id = word.index(":")
                icon_type = "sigils" if "sigil" in word else "icons"
                icon_path = f"assets/general_assets/{icon_type}/{word[colon_id+1:-1]}.png"
                try:
                    icon = get_resized_image(Image.open(icon_path), TRAIT_DESC_ICON_SIZE)
                except FileNotFoundError:
                    icon = get_resized_image(Image.open("assets/general_assets/sigils/X.png"), TRAIT_DESC_ICON_SIZE)
                add_width(icon.width)
            else:
                word = " " + word if "HIB" not in word else word[3:]
                add_width(draw.textlength(word, font=heavyweight_font), draw.textlength(word, font=heavyweight_font))

        # Write the trait
        x_offset = (text_img.width - lengths[0]) // 2
        y_offset = 0
        word_id = 0

        def add_new_line():
            nonlocal y_offset, text_img
            y_offset += TRAIT_DESCRIPTION_SIZE
            new_height = text_img.size[1] + TRAIT_DESCRIPTION_SIZE
            new_img = Image.new("RGBA", (size_limit, new_height), (0, 0, 0, 0))
            new_img.paste(text_img, (0, 0))
            text_img = new_img

        def add_image(img):
            nonlocal word_id, x_offset, y_offset, text_img
            if word_id >= words_per_phrase[0]:
                add_new_line()
                words_per_phrase.pop(0)
                lengths.pop(0)
                x_offset = (text_img.width - lengths[0]) // 2
                word_id = 0
            text_img.paste(img, (int(x_offset), y_offset), img)
            x_offset += img.width

        for word in description_words:
            if "{" in word:
                if word[-1] != "}":
                    word = word[0:word.index("}") + 1]
                colon_id = word.index(":")
                icon_type = "sigils" if "sigil" in word else "icons"
                icon_path = f"assets/general_assets/{icon_type}/{word[colon_id + 1:-1]}.png"
                if color != 'black':
                    new_path = f"assets/general_assets/{icon_type}/{word[colon_id + 1:-1]}_outline.png"
                    if os.path.exists(new_path):
                        icon_path = new_path
                try:
                    icon = get_resized_image(Image.open(icon_path), TRAIT_DESC_ICON_SIZE)
                except FileNotFoundError:
                    icon = get_resized_image(Image.open("assets/general_assets/sigils/X.png"), TRAIT_DESC_ICON_SIZE)
                if color != 'black':
                    add_color(icon, color)
                x_offset += draw.textlength(" ", font=heavyweight_font)
                add_image(icon)
            elif word_id < words_per_phrase[0]:
                word = " " + word if "HIB" not in word else word[3:]
                draw.text((x_offset, y_offset), word, fill=color, font=heavyweight_font)
                x_offset += draw.textlength(word, font=heavyweight_font)
            else:
                words_per_phrase.pop(0)
                lengths.pop(0)
                x_offset = (text_img.width - lengths[0]) // 2
                word_id = 0

                add_new_line()

                draw = ImageDraw.Draw(text_img)
                word = word if "HIB" not in word else word[3:]
                draw.text((x_offset, y_offset), word, fill=color, font=heavyweight_font)
                x_offset += draw.textlength(word, font=heavyweight_font)
            word_id += 1
        return text_img

    def getImage(self, color='black', base_game: bool = False, shortened_format: bool = False):
        if base_game and self.base_game_image and color == "black":
            return self.base_game_image
        if shortened_format and self.short_image and color == "black":
            return self.short_image
        if not base_game and not shortened_format and self.image and color == "black":
            return self.image

        if not self.is_trait:
            sigil_img = self.sigilImage(color)

        if base_game:
            if self.is_trait:
                self.base_game_image = Image.new("RGBA", (0, 0))
            else:
                # Draw sigil using base game aesthetic
                self.base_game_image = self.__draw_base_game(sigil_img, color)
            return self.base_game_image

        description_words = self.get_description().split()

        if self.is_trait:
            self.image = self.__get_trait_image(color, description_words)
            self.base_game_image = self.image
            return self.image

        heavyweight_font = ImageFont.truetype(FONT, SIGIL_NAME_SIZE)
        text_img = Image.new("RGBA", (SIGIL_DESC_SPACE, SIGIL_NAME_SIZE), (0, 0, 0, 0))
        draw = ImageDraw.Draw(text_img)
        sigil_name = self.name + (":" if shortened_format else "")
        size = round(draw.textlength(sigil_name, font=heavyweight_font))
        draw.text((0, 0), sigil_name, fill=color, font=heavyweight_font)
        if shortened_format:
            # Draw sigil using shortened formatting
            y_offset, text_img = write_description(0, SIGIL_NAME_SIZE - SIGIL_DESCRIPTION_SIZE - 1,
                                                   size, description_words, color,
                                                   text_img, SIGIL_DESC_SPACE, shortened_format)
        else:
            # Draw sigil normally

            new_height = text_img.size[1] + SIGIL_NAME_SIZE
            new_img = Image.new("RGBA", (SIGIL_DESC_SPACE, new_height), (0, 0, 0, 0))
            new_img.paste(text_img, (0, 0))
            text_img = new_img
            draw = ImageDraw.Draw(text_img)
            heavyweight_font = ImageFont.truetype(FONT, SIGIL_DESCRIPTION_SIZE)
            size = SIGIL_DESCRIPTION_SIZE

            y_offset, text_img = write_description(SIGIL_DESCRIPTION_SIZE, SIGIL_NAME_SIZE,
                                                   size, description_words, color,
                                                   text_img, SIGIL_DESC_SPACE, shortened_format)

        text_height = y_offset + SIGIL_DESCRIPTION_SIZE
        final_img_height = max(text_height, sigil_img.height)
        final_img = Image.new("RGBA", (DEFAULT_CONFIG['sigil_space'], final_img_height), (0, 0, 0, 0))
        final_img.paste(sigil_img,
                        ((SIGIL_IMG_SPACE - sigil_img.width) // 2,
                         min((final_img_height - sigil_img.height) // 2, 10)))
        final_img.paste(text_img.crop((0, 0, text_img.width, text_height)),
                        (SIGIL_IMG_SPACE, (final_img_height - text_height) // 2))
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

