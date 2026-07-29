from os import path
from model import get_color_mapping, apply_temple_colors, load_config, costs, sigils, Image, ImageDraw, ImageFont, logging, FONT, DEFAULT_CONFIG


def get_card_asset(asset_name, default_folder, temple, tier=None, bg_modifier=None):
    prefixes = []
    if tier and bg_modifier:
        prefixes.append(f"{tier}_{bg_modifier}_")
    if tier:
        prefixes.append(f"{tier}_")
    if bg_modifier:
        prefixes.append(f"{bg_modifier}_")
    prefixes.append("")

    directories = [f"assets/{temple.lower()}", f"assets/general_assets/{default_folder}"]
    for prefix in prefixes:
        for directory in directories:
            try:
                return apply_temple_colors(Image.open(f"{directory}/{prefix}{asset_name}.png"), temple, tier, bg_modifier)
            except (FileNotFoundError, PermissionError):
                continue
    
    return get_card_asset(asset_name, default_folder, temple, DEFAULT_CONFIG["default_tier"], bg_modifier)

def get_cardback(temple, tier, bg_modifier=None):
    return get_card_asset("bg", "cardbacks", temple, tier, bg_modifier)

def get_empty_cardback_bottom(temple, tier, bg_modifier=None):
    return get_card_asset("bg_emptybottom", "cardbacks", temple, tier, bg_modifier)

def get_vanilla_gemification(temple, tier, bg_modifier=None):
    return get_card_asset("vanilla_gemify", "extras/gemification", temple, tier, bg_modifier)

def get_conduit_indicator(temple, tier, bg_modifier=None):
    return get_card_asset("conduit", "extras/indicators", temple, tier, bg_modifier)

def get_mox_indicator(temple, tier, bg_modifier=None):
    return get_card_asset("mox", "extras/indicators", temple, tier, bg_modifier)

def get_conduit_mox_indicator(temple, tier, bg_modifier=None):
    return get_card_asset("conduit_mox", "extras/indicators", temple, tier, bg_modifier)

def get_traitline_image(temple, tier, bg_modifier):
    traitline = get_card_asset("traitline", "cardbacks", temple, tier, bg_modifier)
    return traitline.resize((traitline.width * 10, traitline.height * 10), Image.NEAREST)


def get_card_art(art_filename, temple, bg_modifier):
    try:
        art = Image.open(f"assets/general_assets/card_art/{art_filename}")
        return apply_temple_colors(art, temple, bg_modifier)
    except (FileNotFoundError, PermissionError):
        return Image.open(f"assets/general_assets/card_art/_placeholder_.png")


def get_sigil_data(config, csv_dict):
    str_sigils = csv_dict['Sigils'].split(', ') if csv_dict['Sigils'] not in ['None', ''] else []
    str_tokens = csv_dict['Token'].split(', ') if csv_dict['Token'] not in ['None', ''] else []
    str_traits = csv_dict['Traits'].split(', ') if csv_dict['Traits'] not in ['None', ''] else []
    power_sigil = False
    health_sigil = False
    conduit_sigil = False
    mox_provided = []
    token_id = 0

    def handle_sigil_or_trait(att_list, att_dict, tokens):
        nonlocal token_id, power_sigil, health_sigil, conduit_sigil
        result = None
        conditionals = SigilConditional.get_all_subclasses()
        while len(conditionals) > 0 and not result:
            result = conditionals.pop().handle_sigil_entry(config, sigil)
        if result:
            att_list.append(result)
            if result.sigil:
                for _ in range(result.sigil.token_needed):
                    result.sigil.addToken(tokens[token_id % len(tokens)])
                    token_id += 1
                for tag in result.sigil.tags.split(','):
                    if "power_sigil" in tag:
                        power_sigil = result.sigil.sigilImage()
                    if "health_sigil" in tag:
                        health_sigil = result.sigil.sigilImage()
                    if "conduit_sigil" in tag:
                        conduit_sigil = result.sigil.name.replace(" ", "")
                    if "mox_" in tag:
                        mox_provided.append(tag)
        elif sigil in att_dict:
            elt = att_dict[sigil].copy()
            att_list.append(elt)
            for _ in range(elt.token_needed):
                elt.addToken(tokens[token_id % len(tokens)])
                token_id += 1
            for tag in elt.tags.split(','):
                if "power_sigil" in tag:
                    power_sigil = elt.sigilImage()
                if "health_sigil" in tag:
                    health_sigil = elt.sigilImage()
                if "conduit_sigil" in tag:
                    conduit_sigil = elt.name.replace(" ", "")
                if "mox_" in tag:
                    mox_provided.append(tag)

    sigil_list = []
    trait_list = []
    try:
        for sigil in str_sigils:
            handle_sigil_or_trait(sigil_list, sigils.SIGILS, str_tokens)
        for sigil in str_traits:
            handle_sigil_or_trait(trait_list, sigils.TRAITS, str_tokens)
        return sigil_list, trait_list, power_sigil, health_sigil, conduit_sigil, mox_provided
    except KeyError as e:
        print(f"Error: {e}")
        logging.error(f"Error: {e}")


def print_indicators(config, image, csv_dict, bg_modifier=None, mox_provided=[]):
    need_displacement = False
    if "conduit_indicator" in csv_dict["Tags"]:
        conduit_image = get_conduit_indicator(csv_dict["Temple"], csv_dict["Tier"], bg_modifier)
        image.paste(conduit_image, (0, 0), conduit_image)
        need_displacement = True
    if "mox_indicator" in csv_dict["Tags"]:
        # Here, if need_displacement is true, it means we also already have a conduit indicator in place.
        conduit = "conduit_" if need_displacement else ""
        if conduit:
            mox_image = get_conduit_mox_indicator(csv_dict["Temple"], csv_dict["Tier"], bg_modifier)
        else:
            mox_image = get_mox_indicator(csv_dict["Temple"], csv_dict["Tier"], bg_modifier)
        image.paste(mox_image, (0, 0), mox_image)

        possible_moxes = ["mox_green", "mox_orange", "mox_blue", "mox_prism"]
        for mox in possible_moxes:
            if mox in csv_dict["Tags"] or mox in mox_provided:
                mox_img = Image.open(f"assets/general_assets/extras/indicators/{conduit}{mox}.png")
                image.paste(mox_img, (0, 0), mox_img)
                
        need_displacement = True
    return need_displacement


def print_stat_gemification_indicators(config, image, csv_dict, bg_modifier=None):
    for stat in ["Health", "Power", "Cost"]:
        if "_" not in csv_dict[stat]:
            continue

        gemified_asset = get_card_asset(stat.lower(), "extras/gemification", csv_dict["Temple"], csv_dict["Tier"], bg_modifier)
        image.paste(gemified_asset, (0, 0), gemified_asset)
        
        gems_list = csv_dict[stat].lower().split("_")[:-2]
        if "prism" in gems_list:
            gem_file = "prism"
        else:
            gem_file = "_".join([g for g in ["green", "orange", "blue"] if g in gems_list])
        gem_image = get_card_asset(gem_file, "extras/gemification", csv_dict["Temple"], csv_dict["Tier"], bg_modifier)
        
        gem_x = config[f'gemification_{stat.lower()}_horizontal_center'] - (gem_image.width // 2)
        if stat == "Health":
            gem_y = config[f'gemification_{stat.lower()}_top_border']
        else:
            gem_y = config[f'gemification_{stat.lower()}_bottom_border'] - gem_image.height
            
        image.paste(gem_image, (gem_x, gem_y), gem_image)


def print_extra_cell_indicators(config, image, csv_dict, bg_modifier=None):
    for tag in csv_dict["Tags"].split(","):
        if "extra_cell" in tag.strip():
            cells = int(tag.strip().split("_")[0])
            cell_y = 26
            cell_image = get_card_asset("extra_cell", "extras/indicators", csv_dict["Temple"], csv_dict["Tier"], bg_modifier)
            for _ in range(cells):
                image.paste(cell_image, (3, cell_y), cell_image)
                cell_y += cell_image.height - 1
            return


def print_card_cost(config, image, csv_dict):
    if csv_dict['Cost'].upper() in ['NONE', '', 'FREE', None]:
        return

    cost = csv_dict['Cost']
    cost_x = config['cost_right_border']
    if "_" in cost:
        cost = cost.lower().split("_").pop()
        cost_x -= config["cost_right_border_gemification_displacement"]
        
    cost_images = []
    for cost in costs.get_cost(cost):
        cost_images.append(apply_temple_colors(cost.getCostImage(), csv_dict['Temple'], csv_dict['Tier']))

    cost_y = config['cost_bottom_border'] - cost_images[0].height
    for cost_img in cost_images:
        if cost_x - cost_img.width < config['cost_left_border']:
            cost_x = config['cost_right_border']
            cost_y -= cost_img.height + 1
        image.paste(cost_img, (cost_x - cost_img.width, cost_y), cost_img)
        cost_x -= cost_img.width + 1


def paste_sigil(image, sigil_img, box):
    sigil_img_trans = Image.new("RGBA", image.size)
    sigil_img_trans.paste(sigil_img, box, mask=sigil_img)
    new_img = Image.alpha_composite(image, sigil_img_trans)
    return new_img


def paste_empty_cardback_bottom(config, image, temple, tier, bg_modifier=None):
    if not config["allow_card_bottom_removal"]:
        # If bottom removal is not allowed, return None to indicate failure
        return None
    bottom_image = get_empty_cardback_bottom(temple, tier, bg_modifier)
    bottom_image = bottom_image.resize((bottom_image.width * 10, bottom_image.height * 10), Image.NEAREST)
    image.paste(bottom_image, (0, image.height - bottom_image.height), bottom_image)
    return image


def print_card_sigils_and_traits(config, color_map, bg_modifier, image, sigil_y, csv_dict, sigil_list, trait_list, use_shortened_format):
    # -----------------------
    # Print the sigils
    # -----------------------
    sigil_x = config['sigil_left_border']
    for sigil in sigil_list:
        if isinstance(sigil, SigilConditional):
            sigil_y -= sigil.top_displacement
            sigil_y -= sigil_y % 10
            sigil_img = sigil.getImage(config, color_map, csv_dict['Temple'], csv_dict['Tier'], bg_modifier, use_shortened_format)
            image = paste_sigil(image, sigil_img, (0, sigil_y))
            sigil_y -= sigil.bottom_displacement
        else:
            sigil_img = sigil.getImage(shortened_format=use_shortened_format)
            if sigil_y + sigil_img.height > image.height:
                # If the sigil would go off the bottom of the card, return None to indicate failure
                return None
            if sigil_y + sigil_img.height > config['sigil_bottom_border']:
                image = paste_empty_cardback_bottom(config, image, csv_dict['Temple'], csv_dict['Tier'], bg_modifier)
                if image is None:
                    # If the sigils would overlap with the bottom border of the card and bottom removal is not allowed, return None to indicate failure
                    return None
            image = paste_sigil(image, sigil_img, (sigil_x, sigil_y))
        sigil_y += sigil_img.height + config['sigil_vertical_spacing']

    # -----------------------
    # Print the traits
    # -----------------------
    if len(trait_list) > 0:
        traitline_img = get_traitline_image(csv_dict['Temple'], csv_dict['Tier'], bg_modifier)
        trait_images = []
        trait_height = traitline_img.height + config['traitline_vertical_spacing']
        for trait in trait_list:
            trait_img = trait.getImage(color=color_map["trait_color"])
            trait_height += trait_img.height + config['trait_vertical_spacing']
            trait_images.append(trait_img)

        if sigil_y + trait_height > image.height:
            # If the traits would go off the bottom of the card, return None to indicate failure
            return None

        if sigil_y + trait_height > config['sigil_bottom_border']:
            image = paste_empty_cardback_bottom(config, image, csv_dict['Temple'], csv_dict['Tier'], bg_modifier)
            if image is None:
                # If the traits would overlap with the bottom border of the card and bottom removal is not allowed, return None to indicate failure
                return None
            trait_y = sigil_y - (sigil_y % 10) + 10
        else:
            if config['traits_at_bottom']:
                trait_y = config['sigil_bottom_border'] - trait_height
                trait_y -= trait_y % 10
            else:
                trait_y = sigil_y - (sigil_y % 10) + 10

        image.paste(traitline_img, ((image.width - traitline_img.width) // 2, trait_y), traitline_img)
        trait_y += traitline_img.height + config['traitline_vertical_spacing']
        for trait_img in trait_images:
            image.paste(trait_img, (sigil_x, trait_y), trait_img)
            trait_y += trait_img.height + config['trait_vertical_spacing']
    return image


def print_base_game_card(config, color_map, bg_modifier, image, sigil_y, csv_dict, sigil_list, trait_list):
    trait_height = 0
    if len(trait_list) > 0:
        traitline_img = get_traitline_image(csv_dict['Temple'], csv_dict['Tier'], bg_modifier)
        trait_images = []
        trait_height = traitline_img.height + config['traitline_vertical_spacing']
        for trait in trait_list:
            trait_img = trait.getImage(color=color_map["trait_color"])
            trait_height += trait_img.height + config['trait_vertical_spacing']
            trait_images.append(trait_img)

    sigil_left = config['sigil_left_border']
    size = image.width - sigil_left * 2
    sigil_rows = [[]]
    sigil_heights = [0]
    current_row_width = 0
    for sigil in sigil_list:
        sigil_img = sigil.getImage(base_game=True)
        if current_row_width + sigil_img.width > size:
            sigil_rows.append([])
            sigil_heights.append(0)
            current_row_width = 0
        sigil_rows[-1].append(sigil_img)
        sigil_heights[-1] = max(sigil_heights[-1], sigil_img.height)
        current_row_width += sigil_img.width

    total_sigil_height = sum(sigil_heights) + (len(sigil_heights) - 1) * config['sigil_vertical_spacing']
    if sigil_y + total_sigil_height + trait_height > image.height:
        # If the sigils and traits would go off the bottom of the card, return None to indicate failure
        return None
    if sigil_y + total_sigil_height + trait_height > config['sigil_bottom_border']:
        image = paste_empty_cardback_bottom(config, image, csv_dict['Temple'], csv_dict['Tier'], bg_modifier)
        if image is None:
            # If the sigils and traits would overlap with the bottom border of the card and bottom removal is not allowed, return None to indicate failure
            return None
        trait_y = sigil_y + total_sigil_height - (sigil_y + total_sigil_height % 10) + 10
    else:
        if config['traits_at_bottom']:
            trait_y = config['sigil_bottom_border'] - trait_height
            trait_y -= trait_y % 10
        else:
            trait_y = sigil_y + total_sigil_height - ((sigil_y + total_sigil_height) % 10) + 10

    for row_index, row in enumerate(sigil_rows):
        row_width = sum(sigil.width for sigil in row)
        free_space = size - row_width
        num_sigils = len(row)
        space_between = free_space / (num_sigils + 1) if num_sigils > 0 else 0
        row_x = sigil_left + space_between
        for sigil_img in row:
            image.paste(sigil_img, (int(row_x), sigil_y), sigil_img)
            row_x += sigil_img.width + space_between
        sigil_y += sigil_heights[row_index] + config['sigil_vertical_spacing']

    image.paste(traitline_img, ((image.width - traitline_img.width) // 2, trait_y), traitline_img)
    trait_y += traitline_img.height + config['traitline_vertical_spacing']
    for trait_img in trait_images:
        image.paste(trait_img, (sigil_left, trait_y), trait_img)
        trait_y += trait_img.height + config['trait_vertical_spacing']

    return image


def write_name(config, image, draw, csv_dict):
    name_size = config['name_font_size']
    name_y = config['name_top_border']
    name_font = ImageFont.truetype(FONT, name_size)
    while draw.textlength(csv_dict["Card Name"], font=name_font) > config['name_max_width']:
        name_size -= 1
        name_font = ImageFont.truetype(FONT, name_size)
        name_y += 0.5
    if config["center_card_name"]:
        name_x = (image.width - draw.textlength(csv_dict["Card Name"], font=name_font)) // 2
    else:
        name_x = config["name_left_border"]
    draw.text((name_x, int(name_y)), csv_dict["Card Name"], fill="black", font=name_font)


def write_flavor_text(config, color_map, image, draw, csv_dict, need_displacement):
    flavor_text = csv_dict["Flavor Text"].replace("\r", "").replace("\n", " ")
    flavor_font = ImageFont.truetype(FONT, config['flavor_text_font_size'])
    if flavor_text != "":
        while draw.textlength(flavor_text, font=flavor_font) > config['flavor_text_max_width']:
            limit = flavor_text.rfind(" ") if " " in flavor_text else -6
            flavor_text = flavor_text[:limit] + "..."
            flavor_text += "''" if "''" in flavor_text else ""
        flavor_text_x = config['flavor_text_left_border'] + (config['flavor_text_max_width'] - draw.textlength(flavor_text, font=flavor_font)) // 2
        flavor_text_y = config['flavor_text_top_border'] + (config['indicator_displacement'] if need_displacement else 0)
        draw.text((flavor_text_x, flavor_text_y), flavor_text, fill=color_map["flavor_text_color"], font=flavor_font)


def write_metadata(config, color_map, image, draw, csv_dict):
    metadata_font = ImageFont.truetype(FONT, config['metadata_font_size'])
    description = f"{csv_dict['Tier']} {csv_dict['Temple']}"
    tribes = csv_dict['Tribes'].split(' ') if csv_dict['Tribes'] not in ['None', ''] else []
    if len(tribes) > 0:
        description += " - "
        for tribe in tribes:
            description += tribe + " "
        description = description[:-1]
    desc_y = config['metadata_top_border']
    desc_x = (image.width - draw.textlength(description, font=metadata_font)) // 2
    draw.text((desc_x, desc_y), description, fill=color_map["metadata_color"], font=metadata_font)


def write_art_credit(config, color_map, image, draw, csv_dict):
    art_credit_font = ImageFont.truetype(FONT, config['art_credit_font_size'])
    artist_text = f"Art by {csv_dict['Credit']}"
    desc_y = config['art_credit_top_border']
    desc_x = (image.width - draw.textlength(artist_text, font=art_credit_font)) // 2
    draw.text((desc_x, desc_y), artist_text, color_map["art_credit_color"], font=art_credit_font)


def write_stats(config, image, csv_dict, power_sigil, health_sigil, bg_modifier):
    stats_font = ImageFont.truetype(FONT, config['stats_font_size'])
    
    if power_sigil and config['show_power_sigil']:
        power_center = config['power_sigil_center']
        image = paste_sigil(image, power_sigil, (power_center[0] - power_sigil.width // 2, power_center[1] - power_sigil.height // 2))
    else:
        power = csv_dict["Power"]
        if "_" in power:
            power = power.lower().split("_").pop()
        draw = ImageDraw.Draw(image)
        draw.text(config['power_coord'], power, fill="black", font=stats_font)

    if health_sigil and config['show_health_sigil']:
        health_center = config['health_sigil_center']
        image = paste_sigil(image, health_sigil, (health_center[0] - health_sigil.width // 2, health_center[1] - health_sigil.height // 2))
    else:
        health = csv_dict["Health"]
        if "_" in health:
            health = health.lower().split("_").pop()
        draw = ImageDraw.Draw(image)
        draw.text(config['health_coord'], health, fill="black", font=stats_font)

    return image


def write_stat_gemification_text(config, image, draw, csv_dict):
    gemification_font = ImageFont.truetype(FONT, config['gemification_font_size'])
    for stat in ["Health", "Power", "Cost"]:
        if "_" in csv_dict[stat]:
            text = csv_dict[stat].split("_")[-2]
            text_x = config[f'gemification_{stat.lower()}_text_horizontal_center'] - (draw.textlength(text, font=gemification_font) // 2)
            draw.text((text_x, config[f'gemification_{stat.lower()}_text_top_border']), text, fill="black", font=gemification_font)


class SigilConditional():

    def __init__(self, sigil=None, top_displacement=0, bottom_displacement=0):
        self.sigil = sigil
        self.top_displacement = top_displacement
        self.bottom_displacement = bottom_displacement
    
    @classmethod
    def get_all_subclasses(cls):
        """Recursively finds all subclasses down the inheritance tree."""
        subclasses = set(cls.__subclasses__())
        return subclasses.union([s for c in subclasses for s in c.get_all_subclasses()])

    @classmethod
    def handle_sigil_entry(cls, config, sigil_entry: str):
        """
        Each subclass overrides this. 
        Checks if the sigil entry corresponds to its signal, 
        and returns an instance of itself if it does.
        """
        return None


class CellConditional(SigilConditional):

    def __init__(self, config, sigil):
        super().__init__(
            sigil,
            top_displacement = config["cell_sigil_top_displacement"],
            bottom_displacement = config["cell_sigil_bottom_displacement"]
        )

    def getImage(self, config, color_map, temple, tier, bg_modifier, use_shortened_format=False):
        sigil_img = self.sigil.getImage(shortened_format=use_shortened_format)
        if sigil_img.height < config["cell_sigil_small_max_height"]:
            patch_image = get_card_asset("cell", "extras/conditionals", temple, tier, bg_modifier)
        elif sigil_img.height < config["cell_sigil_medium_max_height"]:
            patch_image = get_card_asset("cell3", "extras/conditionals", temple, tier, bg_modifier)
        else:
            patch_image = get_card_asset("cell4", "extras/conditionals", temple, tier, bg_modifier)
        return paste_sigil(patch_image, sigil_img, (config["sigil_left_border"], (patch_image.height - sigil_img.height) // 2 + 3))

    @classmethod
    def handle_sigil_entry(cls, config, sigil_entry: str):
        if "_" not in sigil_entry:
            return None
        sigil = sigil_entry.split("_")
        if sigil[0].lower() == "cell":
            if sigil[1] in sigils.SIGILS:
                return CellConditional(config, sigils.SIGILS[sigil[1]].copy())
        return None


class LatcherConditional(SigilConditional):

    def __init__(self, config, sigil):
        super().__init__(
            sigil,
            top_displacement = config["latch_sigil_top_displacement"],
            bottom_displacement = config["latch_sigil_bottom_displacement"]
        )

    def getImage(self, config, color_map, temple, tier, bg_modifier, use_shortened_format=False):
        sigil_img = self.sigil.getImage(shortened_format=use_shortened_format)
        if sigil_img.height < config["latch_sigil_small_max_height"]:
            patch_image = get_card_asset("latch", "extras/conditionals", temple, tier, bg_modifier)
        elif sigil_img.height < config["latch_sigil_medium_max_height"]:
            patch_image = get_card_asset("latch3", "extras/conditionals", temple, tier, bg_modifier)
        else:
            patch_image = get_card_asset("latch4", "extras/conditionals", temple, tier, bg_modifier)
        latch_head = get_card_asset("latch_head", "extras/conditionals", temple, tier, bg_modifier)
        patch_image.paste(latch_head, (config["left_latch_head_border"] - latch_head.width, (patch_image.height - latch_head.height) // 2), latch_head)
        latch_head = latch_head.transpose(Image.FLIP_LEFT_RIGHT)
        patch_image.paste(latch_head, (config["right_latch_head_border"], (patch_image.height - latch_head.height) // 2), latch_head)
        return paste_sigil(patch_image, sigil_img, (config["sigil_left_border"], (patch_image.height - sigil_img.height) // 2 + 2))

    @classmethod
    def handle_sigil_entry(cls, config, sigil_entry: str):
        if "_" not in sigil_entry:
            return None
        sigil = sigil_entry.split("_")
        if sigil[0].lower() == "latch":
            if sigil[1] in sigils.SIGILS:
                return LatcherConditional(config, sigils.SIGILS[sigil[1]].copy())
        return None


class GemifyConditional(SigilConditional):

    def __init__(self, config, sigil, gems=[]):
        self.gems = gems
        super().__init__(
            sigil,
            top_displacement = config["gemification_sigil_top_displacement"],
            bottom_displacement = config["gemification_sigil_bottom_displacement"]
        )

    def getImage(self, config, color_map, temple, tier, bg_modifier, use_shortened_format=False):
        sigil_img = self.sigil.getImage(shortened_format=use_shortened_format)
        if sigil_img.height < config["gemification_sigil_small_max_height"]:
            patch_image = get_card_asset("sigil", "extras/gemification", temple, tier, bg_modifier)
        elif sigil_img.height < config["gemification_sigil_medium_max_height"]:
            patch_image = get_card_asset("sigil3", "extras/gemification", temple, tier, bg_modifier)
        else:
            patch_image = get_card_asset("sigil4", "extras/gemification", temple, tier, bg_modifier)
        
        if "prism" in self.gems:
            gem_file = "prism"
        else:
            gem_file = "_".join([g for g in ["green", "orange", "blue"] if g in self.gems])
        if "_" in gem_file:
            gem_file = "sigil_" + gem_file
        gem_image = get_card_asset(gem_file, "extras/gemification", temple, tier, bg_modifier)
        
        gem_x = config['gemification_sigil_gems_right_border'] - gem_image.width
        gem_y = (patch_image.height - gem_image.height) // 2
        patch_image.paste(gem_image, (gem_x, gem_y), gem_image)
        
        patch_image = patch_image.resize((patch_image.width * 10, patch_image.height * 10), Image.NEAREST)
        return paste_sigil(patch_image, sigil_img, (config["sigil_left_border"], (patch_image.height - sigil_img.height) // 2 + 2))

    @classmethod
    def handle_sigil_entry(cls, config, sigil_entry: str):
        if "_" not in sigil_entry:
            return None
        gems = sigil_entry.split("_")
        sigil = gems.pop()
        if set(g.lower() for g in gems) & {"green", "orange", "blue", "prism"}:
            if sigil in sigils.SIGILS:
                return GemifyConditional(config, sigils.SIGILS[sigil].copy(), [g.lower() for g in gems])
        return None


class ArcaneConditional(SigilConditional):

    def __init__(self, config):
        super().__init__(
            top_displacement = config["arcane_sigil_top_displacement"],
            bottom_displacement = config["arcane_sigil_bottom_displacement"]
        )

    def getImage(self, config, color_map, temple, tier, bg_modifier, use_shortened_format=False):
        patch_image = get_card_asset("arcane", "extras/conditionals", temple, tier, bg_modifier)
        draw = ImageDraw.Draw(patch_image)
        font = ImageFont.truetype(FONT, config["arcane_font_size"])
        text = config["arcane_text"]
        text_x = (patch_image.width - draw.textlength(text, font=font)) // 2
        draw.text((text_x-1, config["arcane_text_y"] + 3), text, fill=color_map["arcane_light_color"], font=font)
        draw.text((text_x+1, config["arcane_text_y"]), text, fill=color_map["arcane_dark_color"], font=font)
        return patch_image

    @classmethod
    def handle_sigil_entry(cls, config, sigil_entry: str):
        if sigil_entry.lower() == "rainbow":
            return ArcaneConditional(config)
        return None


class TribalConditional(SigilConditional):

    def __init__(self, config):
        super().__init__(
            top_displacement = config["tribal_sigil_top_displacement"],
            bottom_displacement = config["tribal_sigil_bottom_displacement"]
        )

    def getImage(self, config, color_map, temple, tier, bg_modifier, use_shortened_format=False):
        patch_image = get_card_asset("tribal", "extras/conditionals", temple, tier, bg_modifier)
        draw = ImageDraw.Draw(patch_image)
        font = ImageFont.truetype(FONT, config["tribal_font_size"])
        text = config["tribal_text"]
        text_x = (patch_image.width - draw.textlength(text, font=font)) // 2
        draw.text((text_x-1, config["tribal_text_y"] + 3), text, fill=color_map["tribal_light_color"], font=font)
        draw.text((text_x+1, config["tribal_text_y"]), text, fill=color_map["tribal_dark_color"], font=font)
        return patch_image

    @classmethod
    def handle_sigil_entry(cls, config, sigil_entry: str):
        if sigil_entry.lower() == "tribal":
            return TribalConditional(config)
        return None


def create_card(csv_dict):
    global TEMPLES, FONT

    # Parse the tags
    raw_tags = csv_dict.get('Tags', '')
    tags = [t.strip().lower() for t in raw_tags.split(',')] if raw_tags not in ['None', ''] else []

    # Extract background modifier
    bg_modifier = ""
    for tag in tags:
        if tag.endswith("_bg"):
            bg_modifier = tag.replace("_bg", "")
            break

    # Pass the modifier to config, color map, and image loaders
    config = load_config(csv_dict['Temple'], csv_dict['Tier'], bg_modifier)
    color_map = get_color_mapping(csv_dict['Temple'], csv_dict['Tier'], bg_modifier)
    
    # Get sigil and trait list
    sigil_list, trait_list, power_sigil, health_sigil, conduit_sigil, mox_provided = get_sigil_data(config, csv_dict)

    # Get cardback
    image = get_cardback(csv_dict['Temple'], csv_dict['Tier'], bg_modifier)

    # Add gemification indicator if needed
    if "gemified_vanila" in csv_dict['Tags']:
        vanilla_gemification = get_vanilla_gemification(csv_dict['Temple'], csv_dict['Tier'], bg_modifier)
        image.paste(vanilla_gemification, (0, 0), vanilla_gemification)

    # Add the art
    card_art = get_card_art(csv_dict['Art File'], csv_dict['Temple'], bg_modifier)
    image.paste(card_art, mask=card_art)

    # Add indicators for conduit and mox
    need_displacement = print_indicators(config, image, csv_dict, bg_modifier, mox_provided)

    # Generate and add the cost
    print_card_cost(config, image, csv_dict)

    # Add stat gemification indicators
    print_stat_gemification_indicators(config, image, csv_dict, bg_modifier)

    # Add extra cell indicators
    print_extra_cell_indicators(config, image, csv_dict, bg_modifier)

    # ----------------------------------------------------
    # Resize the card
    # ----------------------------------------------------
    image = image.resize((image.width * 10, image.height * 10), Image.NEAREST)

    # TODO: Temple/rarity-based values
    draw = ImageDraw.Draw(image)
    # Write the name
    write_name(config, image, draw, csv_dict)
    # Write the flavor text
    write_flavor_text(config, color_map, image, draw, csv_dict, need_displacement)
    # Write the metadata
    if config['write_card_metadata']:
        write_metadata(config, color_map, image, draw, csv_dict)
    # Write art credit
    if config['write_art_credit']:
        write_art_credit(config, color_map, image, draw, csv_dict)

    # If a tag calls for it, add a null conduit sigil indicator
    if not conduit_sigil and "conduit_sigil_indicator" in csv_dict["Tags"]:
        conduit_sigil = "NullConduit"

    success = False
    sigil_y = config['sigil_top_border'] + (config['indicator_displacement'] if need_displacement else 0)

    # Print the sigil conduit indicator
    if config['show_conduit_sigil_indicators'] and conduit_sigil:
        try:
            conduit_img = Image.open(f"assets/general_assets/conduit_sigil_indicators/{conduit_sigil}.png")
            conduit_x = (image.width - conduit_img.width) // 2
            image = paste_sigil(image, conduit_img, (conduit_x, sigil_y - config['sigil_vertical_spacing']))
            sigil_y += conduit_img.height
        except (FileNotFoundError, PermissionError):
            logging.warning(f'Warning: Conduit sigil indicator "assets/general_assets/conduit_sigil_indicators/{conduit_sigil}.png" not found.')

    # Try default formatting
    if config['allow_default_formatting']:
        image_default = print_card_sigils_and_traits(config, color_map, bg_modifier, image, sigil_y, csv_dict, sigil_list, trait_list, use_shortened_format=False)
        if image_default is not None:
            image = image_default
            success = True
    # Try shortened formatting
    if not success and config['allow_shortened_formatting']:
        image_shortened = print_card_sigils_and_traits(config, color_map, bg_modifier, image, sigil_y, csv_dict, sigil_list, trait_list, use_shortened_format=True)
        if image_shortened is not None:
            image = image_shortened
            success = True
    # Try base game formatting
    if not success and config['allow_base_game_display']:
        image_base_game = print_base_game_card(config, color_map, bg_modifier, image, sigil_y, csv_dict, sigil_list, trait_list)
        if image_base_game is not None:
            image = image_base_game
            success = True
    # If no formatting method worked, raise an error
    if not success:
        raise Exception(f"Could not fit sigils and traits on card {csv_dict['Card Name']} with any formatting option.")

    # Write the stats
    image = write_stats(config, image, csv_dict, power_sigil, health_sigil, bg_modifier)

    # Write stat gemification text if needed
    draw = ImageDraw.Draw(image)
    write_stat_gemification_text(config, image, draw, csv_dict)

    return image
