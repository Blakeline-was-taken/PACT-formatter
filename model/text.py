import re
from model import GENERAL_ASSETS_DIR, Image, ImageDraw


MARKUP_PATTERN = re.compile(r"\{([^{}]*)\}")
WORD_PATTERN = re.compile(r"(\\n|\s+|\S+)")


def resolve_text_color(name, config, color_map):
    text_colors = config.get("text_colors", {})
    if not isinstance(text_colors, dict):
        raise ValueError("The config.json 'text_colors' setting must be an object.")
    if name in text_colors:
        value = text_colors[name]
    else:
        matches = [configured_value for configured_name, configured_value in text_colors.items() if configured_name.casefold() == name.casefold()]
        if not matches:
            raise ValueError(f"Text color '{name}' is not defined in config.json.")
        if len(matches) > 1:
            raise ValueError(f"Text color '{name}' is ambiguous in config.json.")
        value = matches[0]

    def indexed_color(entry):
        if not isinstance(entry, dict) or set(entry) != {"index"}:
            raise ValueError(f"Text color '{name}' must use an RGB list or an object with an 'index' value.")
        index = entry["index"]
        palette = color_map.get("palette_colors", [])
        if not isinstance(index, int) or isinstance(index, bool) or not 1 <= index <= len(palette):
            raise ValueError(f"Text color '{name}' has an invalid palette index: {index!r}.")
        return tuple(palette[index - 1][:3])

    def rgb_color(entry):
        if (not isinstance(entry, list) or len(entry) != 3 or any(not isinstance(channel, int) or isinstance(channel, bool) or not 0 <= channel <= 255 for channel in entry)):
            raise ValueError(f"Text color '{name}' must contain three RGB values from 0 to 255.")
        return tuple(entry)

    if isinstance(value, dict) and set(value) == {"index"}:
        return indexed_color(value)
    if isinstance(value, list) and value and isinstance(value[0], (list, dict)):
        palette = []
        for entry in value:
            palette.append(indexed_color(entry) if isinstance(entry, dict) else rgb_color(entry))
        return tuple(palette)
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f"Text color '{name}' must be an RGB list or an object with an 'index' value.")

    return rgb_color(value)


def add_color(image, color):
    color = tuple(color[:3])
    pixels = image.load()
    for y in range(image.height):
        for x in range(image.width):
            pixels[x, y] = (*color, pixels[x, y][3])


def get_inline_icon_size(text, font):
    plain_text = re.sub(r"\\n", "", MARKUP_PATTERN.sub("", text))
    glyph_heights = [bottom - top for character in plain_text if not character.isspace() for left, top, right, bottom in [font.getbbox(character)]]
    if not glyph_heights:
        glyph_heights = [bottom - top for left, top, right, bottom in [font.getbbox("Ag")]]
    return max(1, max(glyph_heights, default=font.size))


def strip_rich_text_tags(text):
    return MARKUP_PATTERN.sub("", text)


def load_icon(markup, color, icon_height):
    icon_type, separator, icon_name = markup.partition(":")
    if not separator:
        return None

    directory = "sigils" if icon_type == "sigil" else "icons"
    icon_path = GENERAL_ASSETS_DIR / directory / f"{icon_name}.png"
    if color != "black":
        directory_path = icon_path.parent
        outline_path = directory_path / f"{icon_path.stem}_outline{icon_path.suffix}"
        if outline_path.exists():
            icon_path = outline_path

    try:
        icon = Image.open(icon_path).convert("RGBA")
    except FileNotFoundError:
        fallback_path = GENERAL_ASSETS_DIR / "sigils" / "X_outline.png"
        if not fallback_path.exists():
            fallback_path = GENERAL_ASSETS_DIR / "sigils" / "X.png"
        icon = Image.open(fallback_path).convert("RGBA")

    icon_width = max(1, round(icon.width * icon_height / icon.height))
    icon = icon.resize((icon_width, icon_height))
    if color != "black":
        add_color(icon, color)
    return icon


def parse_rich_text(text, font, color, color_map, config, icon_height):
    tokens = []
    color_stack = []
    current_color = color
    color_index = 0
    previous_character = ""
    cursor = 0
    measure_draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))

    def current_draw_color():
        if current_color and isinstance(current_color[0], tuple):
            return current_color[color_index % len(current_color)]
        return current_color

    def add_words(value):
        nonlocal color_index, previous_character
        for word in WORD_PATTERN.findall(value):
            if not word:
                continue
            if word == r"\n":
                tokens.append(("newline", None, 0, current_color))
                previous_character = ""
            elif word.isspace():
                width = measure_draw.textlength(word, font=font)
                tokens.append(("text", word, width, current_draw_color()))
                previous_character = ""
            else:
                palette = current_color if current_color and isinstance(current_color[0], tuple) else None
                for character in word:
                    if palette:
                        character_color = palette[color_index % len(palette)]
                        color_index += 1
                    else:
                        character_color = current_color
                    previous_width = (measure_draw.textlength(previous_character, font=font) if previous_character else 0)
                    width = measure_draw.textlength(previous_character + character, font=font) - previous_width
                    tokens.append(("text", character, width, character_color))
                    previous_character = character

    for match in MARKUP_PATTERN.finditer(text):
        add_words(text[cursor:match.start()])
        markup = match.group(1)
        if markup.startswith("color:"):
            color_stack.append((current_color, color_index))
            current_color = resolve_text_color(markup[6:], config, color_map)
            color_index = 0
        elif markup == "/color":
            if not color_stack:
                raise ValueError("Found a closing color tag without a matching {color:name} tag.")
            current_color, color_index = color_stack.pop()
        elif ":" in markup:
            icon_color = current_draw_color()
            icon = load_icon(markup, icon_color, icon_height)
            if icon is None:
                add_words(match.group(0))
            else:
                tokens.append(("icon", icon, icon.width, current_color))
                previous_character = ""
        else:
            add_words(match.group(0))
        cursor = match.end()

    add_words(text[cursor:])
    if color_stack:
        raise ValueError("Found an unclosed {color:name} tag.")
    return tokens


def draw_rich_text(image, text, font, position, color, color_map, config,
            max_width=None, align="left", line_height=None, first_line_offset=0, line_offset=0):
    icon_height = get_inline_icon_size(text, font)
    line_height = line_height or max(font.size, icon_height)
    draw = ImageDraw.Draw(image)
    tokens = parse_rich_text(text, font, color, color_map, config, icon_height)

    items = []
    word_parts = []
    word_width = 0

    def finish_word():
        nonlocal word_parts, word_width
        if word_parts:
            items.append(("word", word_parts, word_width))
            word_parts = []
            word_width = 0

    for kind, value, width, token_color in tokens:
        if kind == "text" and not value.isspace():
            word_parts.append((kind, value, width, token_color))
            word_width += width
        else:
            finish_word()
            if kind == "text":
                items.append(("space", [(kind, value, width, token_color)], width))
            else:
                items.append((kind, value, width))
    finish_word()

    lines = [[]]
    line_widths = [0]
    for kind, value, width in items:
        if kind == "newline":
            lines.append([])
            line_widths.append(0)
            continue
        if kind == "space" and not lines[-1]:
            continue
        current_offset = first_line_offset if len(lines) == 1 else line_offset
        if align == "center":
            current_offset = 0
        if (kind == "word" and max_width is not None and lines[-1]
                and line_widths[-1] + width > max_width - current_offset):
            while lines[-1] and lines[-1][-1][0] == "space":
                line_widths[-1] -= lines[-1].pop()[2]
            lines.append([])
            line_widths.append(0)
        lines[-1].append((kind, value, width))
        line_widths[-1] += width

    required_height = max(1, len(lines)) * line_height + int(position[1])
    if required_height > image.height:
        expanded = Image.new("RGBA", (image.width, required_height), (0, 0, 0, 0))
        expanded.paste(image, (0, 0))
        image = expanded
        draw = ImageDraw.Draw(image)

    x, y = position
    for line_index, (line, line_width) in enumerate(zip(lines, line_widths)):
        if align == "center":
            line_x = x + ((max_width if max_width is not None else line_width) - line_width) // 2
        else:
            line_x = x + (first_line_offset if line_index == 0 else line_offset)
        cursor_x = line_x
        for kind, value, width in line:
            if kind in ("word", "space"):
                for token_kind, token_text, token_width, token_color in value:
                    draw.text((int(cursor_x), int(y)), token_text, fill=token_color, font=font)
                    cursor_x += token_width
            elif kind == "icon":
                image.alpha_composite(value, (int(cursor_x), int(y)))
                cursor_x += width
        y += line_height

    return max(line_widths, default=0), len(lines) * line_height, image


def measure_rich_text(text, font, color, color_map, config):
    icon_height = get_inline_icon_size(text, font)
    lines = [0]
    for kind, _, width, _ in parse_rich_text(text, font, color, color_map, config, icon_height):
        if kind == "newline":
            lines.append(0)
        else:
            lines[-1] += width
    return max(lines, default=0)
