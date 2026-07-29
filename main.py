import os
import threading
import traceback

from csv import DictReader
from tqdm import tqdm
from PIL import Image
from model import cards, sigils, costs, DEFAULT_CONFIG, ASSETS_DIR, logging

CARDS_FILE_PATH = DEFAULT_CONFIG["cards_file_path"]
SIGILS_FILE_PATH = DEFAULT_CONFIG["sigils_file_path"]
TRAITS_FILE_PATH = DEFAULT_CONFIG["traits_file_path"]

# ANSI color codes
RESET = "\033[0m"
BOLD = "\033[1m"
BLUE = "\033[34m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"

successful_export = True


def save_image(img, file_path):
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        img.save(file_path)
    except Exception as e:
        logging.error(f"Failed to save image to {file_path}: {e}\n{traceback.format_exc()}")
        print(f"{RED}Error: Failed to save image to {file_path}.{RESET}")


def run_in_thread_pool(export_function, *args, **kwargs):
    def target_func():
        try:
            export_function(*args, **kwargs)
        except Exception as e:
            logging.error(f"Error in thread while executing export function: {e}\n{traceback.format_exc()}")
            print(f"{RED}Error: {e}{RESET}")

    thread = threading.Thread(target=target_func)
    thread.start()
    return thread


def export_data(csv_file, arrays, export_function):
    global data_list
    in_array = False
    open_arrays = []

    with tqdm(total=len(csv_file), desc=f"{BLUE}Exporting{RESET}", leave=True, bar_format="{l_bar}{bar}|",
              colour="blue") as pbar:
        for row in csv_file:
            try:
                item_name = row.get('Card Name', row.get('Name', '')).upper()
                if item_name in arrays.values():
                    found = False
                    for open_array in open_arrays:
                        found = arrays[open_array] == item_name
                        if found:
                            open_arrays.remove(open_array)
                            arrays.pop(open_array)
                            if len(open_arrays) == 0:
                                in_array = False
                            break
                    if not found:
                        for key in arrays:
                            if arrays[key] == item_name:
                                arrays.pop(key)
                                break
                    run_in_thread_pool(export_function, row)
                elif in_array or type(data_list) is set or item_name in data_list:
                    if item_name in data_list:
                        data_list.remove(item_name)
                    run_in_thread_pool(export_function, row)
                elif item_name in arrays:
                    open_arrays.append(item_name)
                    in_array = True
                    run_in_thread_pool(export_function, row)
            except Exception as e:
                logging.error(f"Error exporting data for row {row}: {e}\n{traceback.format_exc()}")
                print(f"{RED}Error exporting data for row {row}: {e}{RESET}")

            pbar.update(1)


def get_data_list(example_1, example_2):
    global data
    while True:
        try:
            print(f"{YELLOW}Which {data} do you want to export?{RESET}")
            print(
                f"{YELLOW}You may specify {data} with their name (spaces included).{RESET}\n"
                f"{YELLOW}You can also specify arrays of {data}. (e.g., '{example_1}')\n"
                f"{YELLOW}Individual {data} and arrays of {data} are separated by commas. (e.g., '{example_2}')\n{RESET}"
            )

            user_input = input(
                f"{YELLOW}\nPlease list the {data} you wish to export (entering nothing will export all of them): {RESET}"
            ).strip()

            if user_input == '':
                return set()
            return [obj.strip().upper() for obj in user_input.split(",")]

        except ValueError:
            print(f"{RED}Invalid input. Please try again.{RESET}")


def extract_arrays():
    global data_list
    arrays = {}
    for data_id in range(len(data_list) - 1, -1, -1):
        if ":" in data_list[data_id]:
            array = data_list.pop(data_id).split(':')
            arrays[array[0]] = array[1]
    return arrays


def get_csv_data(file_path):
    try:
        with open(file_path, 'r', newline='', encoding='UTF-8') as f:
            return list(DictReader(f, delimiter=','))
    except Exception as e:
        logging.error(f"Failed to read CSV file at {file_path}: {e}\n{traceback.format_exc()}")
        print(f"{RED}Error: Failed to read CSV file at {file_path}.{RESET}")
        return []


try:
    export = None
    while export not in [1, 2, 3]:
        try:
            export = int(
                input(f"{YELLOW}\nWhat do you want to export?{RESET}\n1. Cards\n2. Sigils\n3. Traits\nAnswer: "))
        except ValueError:
            pass

    sigils_csv_data = get_csv_data(SIGILS_FILE_PATH)
    traits_csv_data = get_csv_data(TRAITS_FILE_PATH)

    # Load all sigils and traits
    for sigil in list(DictReader(open(SIGILS_FILE_PATH, 'r', newline='', encoding='UTF-8'), delimiter=',')):
        sigils.add_sigil(sigil)
    for trait in list(DictReader(open(TRAITS_FILE_PATH, 'r', newline='', encoding='UTF-8'), delimiter=',')):
        sigils.add_trait(trait)

    data = None
    data_list = []

    if export == 1:
        data = "cards"
        example = "Adder,Bee:Squirrel,Bullfrog,Axolotl:Flying Ant,Wolf:Grizzly,Cat"
        data_list = get_data_list("Bullfrog:Cat", example)
        total = len(data_list)
        data_arrays = extract_arrays()


        def export_card(row):
            image = cards.create_card(row)
            if DEFAULT_CONFIG["export_sorted_by_folder"]:
                file_name = row['Art File'] if row['Art File'] else row['Card Name']
                save_image(image, f"exports/cards/{row['Temple']}/{row['Tier']}/{file_name}")
            else:
                file_name = row['Art File'] if row['Art File'] else row['Card Name']
                save_image(image, f"exports/cards/{file_name}")


        export_data(get_csv_data(CARDS_FILE_PATH), data_arrays, export_card)
    elif export == 2:
        data = "sigils"
        example = "Touch of Death,Armored:Scavenger,Green Gem,Bell Ringer:Strong Hand,Fecundity:Leader,Deathtrap"
        data_list = get_data_list("Green Gem:Prism Gem", example)
        total = len(data_list)
        data_arrays = extract_arrays()

        color = "black" if DEFAULT_CONFIG["export_color"] == (0, 0, 0) else DEFAULT_CONFIG["export_color"]
        if DEFAULT_CONFIG["export_sigil_patches"]:
            patch = Image.open(f"{ASSETS_DIR}/general_assets/patch.png")


        def export_sigil(row):
            sigil = sigils.SIGILS[row['Name']]

            if DEFAULT_CONFIG["export_normal_formatting"]:
                img = sigil.getImage(color=color)
                save_image(img, "exports/sigils/" + sigil.name + ".png")

            if DEFAULT_CONFIG["export_shorter_formatting"]:
                save_image(sigil.getImage(shortened_format=True, color=color),
                           "exports/short sigils/" + sigil.name + ".png")

            if DEFAULT_CONFIG["export_base_game_formatting"]:
                save_image(sigil.getImage(base_game=True, color=color),
                           "exports/base game sigils/" + sigil.name + ".png")

            if DEFAULT_CONFIG["export_sigil_patches"]:
                sigil_img = sigil.sigilImage(color=color)
                sigil_patch = patch.copy()
                sigil_box = tuple((sigil_patch.size[i] - sigil_img.size[i]) // 2 for i in range(2))
                sigil_patch = cards.paste_sigil(sigil_patch, sigil_img, sigil_box)
                save_image(sigil_patch, "exports/sigil patches/" + sigil.name + "_patch.png")

            if DEFAULT_CONFIG["export_sigil_description_icon"]:
                icon = sigils.get_resized_image(sigil.sigilImage(color=color), DEFAULT_CONFIG['sigil_description_icon_size'])
                save_image(icon, "exports/sigil icons/" + sigil.name + "_icon.png")

            if DEFAULT_CONFIG["export_trait_description_icon"]:
                icon = sigils.get_resized_image(sigil.sigilImage(color=color), DEFAULT_CONFIG['trait_description_icon_size'])
                save_image(icon, "exports/sigil icons/" + sigil.name + "_trait-icon.png")


        export_data(sigils_csv_data, data_arrays, export_sigil)
    else:
        data = "traits"
        example = "Noble Stag Trait,Nine Lives:Bone Power,The Bloated Trait,Dice Power:traeH Power,Skeleton Army Trait:Pipe Bomb Trait,WERE THE RATS"
        data_list = get_data_list("Nine Lives:Bone Power", example)
        total = len(data_list)
        data_arrays = extract_arrays()

        traitline = None
        if DEFAULT_CONFIG["exported_traitline"] != "None":
            temple = DEFAULT_CONFIG["exported_traitline"]
            if temple in cards.TEMPLES:
                traitlines = Image.open(f"{ASSETS_DIR}/cardbacks/Traitlines.png").convert("RGBA")
                traitline = costs.get_temple_variant(traitlines, temple)
                traitline = traitline.resize((traitline.width * 10, traitline.height * 10), Image.NEAREST)
            color = cards.TEXT_COLORS[temple]
        else:
            color = "black" if DEFAULT_CONFIG["export_color"] == (0, 0, 0) else DEFAULT_CONFIG["export_color"]


        def export_trait(row):
            trait_img = sigils.TRAITS[row["Name"]].getImage(color=color)
            if traitline:
                box = (max(trait_img.width, traitline.width), traitline.height + 6 + trait_img.height)
                final_img = Image.new("RGBA", box, (0, 0, 0, 0))
                traitline_x = (final_img.width - traitline.width) // 2
                final_img.paste(traitline, (traitline_x - traitline_x % 10, 0))
                final_img.paste(trait_img, (0, traitline.height + 6))
                save_image(final_img, "exports/traits/" + row["Name"] + ".png")
            else:
                save_image(trait_img, "exports/traits/" + row["Name"] + ".png")


        export_data(traits_csv_data, data_arrays, export_trait)

    if successful_export and total != total - len(data_arrays) - len(data_list):
        print(f"{YELLOW}\nWarning: Some {data} were not able to export.{RESET}")
    else:
        print(f"{GREEN}\nAll {data} were exported.{RESET}")

except Exception as error:
    logging.error('An error occurred: %s', error)
    print(f"{RED}Something went wrong. Check your error.log file for more information.{RESET}")
