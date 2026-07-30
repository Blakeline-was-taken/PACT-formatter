# Getting Started & Migration Guide

## How to Install

Most of the tools this program needs are already built directly into Python. However, you will need to install two external library packages to handle the images and show progress bars (that one will most likely be removed soon so you might not actually need to do this later).

### 1. Install Python

If you haven't already, download and install **Python 3** from the official website (python.org). Make sure to check the box that says **"Add Python to PATH"** during the installation process.

### 2. Install the Required Packages

Open your computer's **Terminal** (Mac/Linux) or **Command Prompt** (Windows), type the following command, and press **Enter**:

```bash
pip install Pillow tqdm
```

* **Pillow** is the engine that handles all the heavy lifting for drawing, layering, and color-swapping image assets. This formatter quite literally cannot work without it.
* **tqdm** creates the visual progress bars in the console so you can see exactly how fast the cards are rendering. But it's clunky and doesn't even work so it's probably gonna go soon.

---

## Upgrading from the Old Formatter

If you have a collection of cards created in the older version of the formatter, follow these steps to migrate your assets and data sheets to the new system.

1. **Move Assets:** Take your old `card_art` and `sigils` folders and place them inside the new `assets/general_assets/` directory.
2. **Place the Old Data Sheets (say that again?):** Grab your old `cards.csv`, `sigils.csv`, and `traits.csv` files and place them directly in the main root folder (where the python scripts live).
3. **Run the Converter:** Open the terminal or command prompt in that folder and run the conversion script by typing:
```bash
python convert_old_formatter_data.py
```

4. **Clean Up and Rename:** The script will create three new files in the main directory. Move these files into the `data/` folder and rename them to remove the `updated_` prefix so the application can read them:
* Rename `updated_cards.csv` to **`cards.csv`**
* Rename `updated_sigils.csv` to **`sigils.csv`**
* Rename `updated_traits.csv` to **`traits.csv`**

*(Alternative: You can leave the names as `updated_cards.csv` etc., but you will need to open your `general.json` configuration file and change the file paths to match those exact names. If you really want to do that for some reason).*

---

## What Changed?

The migration script does a lot of automatic restructuring to prevent a lot of tedious manual editing. Here is a summary of what changed under the hood and why these new data sheets look a little different:

### Changes to Cards (`cards.csv`)

* **Art File section:** The new system no longer uses the card's name to fetch its art, meaning there can now be multiple cards with the same name. The script creates a new **`Art File`** column, which it fills by following the old formatter's naming convention. (for example, a card named "Wild Wolf!" will have "WildWolf.png" in its Art File column).
* **Unified Background Tags:** This new formatter now has a Tags system for cards, sigils and traits. This is useful for a variety of things, and you are encouraged to check out the CSV Data Models section to see what tags exist natively and what they can do. But all the conversion script does is adding the **`bloodless_bg`** tag to cards that had a Bloodless sigil or trait, as that is how it used to work. **Do note that you no longer need a card to have a Bloodless sigil/trait in order for it to have the bloodless background, and vice versa**.

### Changes to Sigils & Traits (`sigils.csv` & `traits.csv`)

* **Bracket Change:** The new text layout engine uses curly brackets instead of square ones to display inline graphics, as square brackets could actually be used by the heavyweight font while curly brackets cannot. The script automatically converts old text codes like `[sigil:TouchOfDeath]` into `{sigil:TouchOfDeath}`.
* **Tags:** Instead of cluttered, individual columns tracking specific behaviors, everything has been streamlined into a single, multi-purpose `Tags` column. The script cleans this up by converting old data toggles:
  * If a sigil shouldn't be color-swapped, it gets tagged with **`has_color`**.
  * If the sigil/trait needs to replace the power value entirely, it gets tagged with `power_sigil`. Note that you can now also do this for health using the `health_sigil` tag.
  * If a sigil has "Conduit" in the name, it gains the **`conduit_sigil`** asset tracker to still use a conduit sigil indicator. Note that those can be turned off by setting the `show_conduit_sigil_indicators` config option to **false**.
  * The script interprets the sigil's description text to know if it acts as a Mox provider, in which case it applies the correct gem overlay tag (**`mox_green`**, **`mox_orange`**, **`mox_blue`**, or **`mox_prism`**). This is used for cards with the mox indicator.

# How to Use

Generating custom cards, sigils, and traits is a three-step process: prepare the data, place the raw image assets, and run the generator script.

## 1. Preparing Data and Assets

Before running the program, ensure data files and visual assets are in the correct directories so the formatter can find them.

### Data CSVs (`/data`)

Raw text data is managed across three files in the `data/` folder:

* **`cards.csv`**: Contains card info.
* **`sigils.csv`**: Contains sigil definitions.
* **`traits.csv`**: Contains trait definitions.

Each of these data sheets have their structure detailed later down in this document in the CSV Data Models section. Make sure they are following that structure before launching the formatter.

### Image Assets (`/assets`)

* **Card Portraits**: Place the image files specified in `cards.csv` (e.g. `Bee.png`) directly into `assets/general_assets/card_art/`.
* **Sigil & Trait Icons**: Drop any custom sigil or trait icons into their respective folders inside `assets/general_assets/sigils/` or `assets/general_assets/icons/`.

---

## 2. Running the Generator

The formatter features an command-line interface that lets you render your entire library or pinpoint specific items.

1. **Launch the Main Script:** Open a terminal in the root directory of the project and run the main entry point:

```bash
python main.py

```

2. **Select Asset Type:** The CLI will prompt you to select what you want to render. Enter the corresponding number:

* `1` for Cards
* `2` for Sigils
* `3` for Traits


3. **Filter What to Export:** You will be asked which specific items you want to export. You have three options:

* **Export All**: Press `Enter` without typing anything.
* **Specific Items**: Type the exact names separated by commas (e.g., `Bullfrog, Axolotl, Squirrel`).
* **Ranges/Arrays**: Use a colon syntax to define bounds (e.g., `Bee:Squirrel` or `Bullfrog:Cat`).

---

## 3. Finding Exports

Once the progress bar completes, all rendered images are compiled inside an `exports/` directory. Depending on the configurations in `config/general.json`, they will look like this:

### Cards (`exports/cards/`)

Cards can either be exported flat into one folder or perfectly sorted based on the configuration rules:

* **Sorted (Default)**: `exports/cards/[Temple]/[Tier]/[Card_Name].png` (e.g., `exports/cards/Beast/Common/Bullfrog.png`)
* **Flat**: `exports/cards/[Card_Name].png`

### Sigils (`exports/sigils/`)

Depending on the export toggles, the formatter can output multiple formatting styles simultaneously:

* `exports/sigils/`: Standard formatted sigil cards.
* `exports/short sigils/`: Compact layout formats.
* `exports/base game sigils/`: Base-game style.
* `exports/sigil patches/`: The raw icon stamped onto a patch background.
* `exports/sigil icons/`: Resized inline icons ready for description text layout.

### Traits (`exports/traits/`)

* `exports/traits/[Trait_Name].png`: Automatically attaches the configured temple traitline graphics (if active) directly above the text block image.

---

# Features

## CSV Data Models

This formatter drives generation using three core CSV data sheets. Below is the precise map of what each data field accepts, how it behaves, and the hidden mechanics it triggers behind the scenes.

### 1. `cards.csv`

This sheet acts as the blueprint for every individual card generated by the formatter.

* **`Card Name`**: The text rendered at the top of the card. The formatter calculates text width dynamically using `name_font_size`. If the name exceeds `name_max_width`, it will automatically shrink the font pixel-by-pixel to prevent asset clipping.
* **`Temple`**: Controls asset routing and the primary palette swap injection. The value maps directly to a matching asset directory (e.g., `assets/beast/` or `assets/undead/`) and pulls its corresponding color palette sheet (`colors.png`).
* **`Tier`**: Defines card rarity (e.g., `common`, `uncommon`, `rare`). It is used to load rarity-specific cardback modifiers (like `uncommon_bg.png`) and hooks into the JSON configuration override hierarchy.
* **`Cost`**: Lists the resources to be printed on the card. Can concatenate multiple different types of resources using a `+` splitting delimiter. Can be gemified similarly to `Power` & `Health` (see below). Supported resource syntaxes include:
  * *Blood*: Formatted as `X blood` (renders a row of X consecutive blood drop icons).
  * *Bones*: Formatted as `X bone`. Renders distinct bones for amounts up to 4, amounts 5 and above stitch together numeric digits and crossbones.
  * *Energy*: Accepts `X energy` (current cells) and/or `Y max` (max cells). Renders a sequential battery bar up to 6 total slots, shifts to numeric rendering beyond 6.
  * *Gems*: Accepts individual or multiple gem types (e.g., `1 emerald`, `2 sapphired + 1 prism`, `3 rubies`).
* **`Power` & `Health`**: Dual-purpose fields handling standard values or **Stat Gemification**. Passing a standard number writes raw statistics using `power_coord` and `health_coord`.
  * *Gemification Syntax*: Formatted as `[gem1]_[gem2]_[value]_[stat]` (can be any number of gems, even 1). For example, `green_5_health` tells the formatter to paste a custom gemmed health background panel, align the physical green and orange mini-gem graphics inside it, and center the text value `5` over the asset using separate gemification coordinates.
* **`Sigils`**: A comma-separated list of sigils to pull from `sigils.csv`. This field features structural wrappers that add conditionals, which completely alter card formatting:
  * *`cell_[SigilName]`*: Embeds the sigil inside a cell structural frame.
  * *`latch_[SigilName]`*: Encapsulates the sigil inside a latch bracket with flanking left/right mechanical heads.
  * *`[gem1]_[gem2]_[SigilName]`*: (e.g., `prism_BombSpewer`) Gemifies the sigil slot, works similarly to `Power` & `Health`.
  * *`rainbow` / `tribal`*: Spawns structural divider zones featuring custom descriptive text defined in the configuration.
* **`Traits`**: A comma-separated list of traits pulled from `traits.csv`. Renders a separator graphic (`traitline.png`).
* **`Token`**: A comma-separated list of string values used to inject dynamic data variables into sigil/trait descriptions. Every time the formatter encounters the exact uppercase keyword `TOKEN` inside a description string, it pops the next value from this list and drops it into the layout.
* **`Tags`**: Internal control flags that direct specific changes:
  * *`[name]_bg`*: Injects an asset override mask. For example, `bloodless_bg` signals the system to look for background sheets matching `bloodless_bg.png` and checks for matching overrides in the config file.
  * *`gemified_vanila`*: Pastes a more vanilla-faithful gemification render onto standard cardbacks before any artwork is drawn.
  * *`conduit_indicator` / `mox_indicator`*: Toggles overlay maps on the upper frame of the card. Renders conduit traces or aligned gems (`mox_green`, `mox_orange`, `mox_blue`, `mox_prism`).
  * *`[integer]_extra_cell`*: (e.g., `3_extra_cells`) Stacks as many energy cells vertically down the left border of the card frame as indicated in the tag.
  * *`conduit_sigil_indicator`*: Places a standard `NullConduit` sigil indicator if no specific conduit sigil is assigned.
* **`Flavor Text`**: Narrative text strings. The layout engine strips line breaks, handles soft truncation via automated ellipsis placement if the text extends past `flavor_text_max_width`, and adds vertical displacement padding if indicator flags are set.
* **`Tribes`**: Space-separated list of structural tribes. Written in the metadata at the top of the card, alongside the `Tier` and `Temple`.
* **`Credit`**: Author or artist attribution text strings, written at the bottom of the card.
* **`Art File`**: The target graphic filename inside the `assets/general_assets/card_art` directory. If the file is missing or blocked, the system uses a `_placeholder_.png` asset as a fallback.

### 2. `sigils.csv` & `traits.csv`

These two sheets define the sub-components of the cards. Both utilize identical structures:

* **`Name`**: Serves as both the name of the sigil and the name of the asset to look for in `assets/general_assets/sigils/`.
* **`Description`**: The informational paragraph. This formatter includes a robust structural text compiler that decodes formatting tokens:
  * *`\n`*: Forces a clean row jump.
  * *`{sigil:SigilName}`*: Compiles and patches a miniature sigil icon directly inside the flowing text field.
  * *`{icon:IconName}`*: Inserts decorative indicators or icon graphics directly inside the flowing text field.
* **`Tags`**: Diagnostic metadata values.
    * *`has_color`*: Prevents the sigil from being colored normally, and instead looks for an outlined version of the sigil (named `[sigil_outline]`) without the color so it may change the black color of that one.
    * *`power_sigil` / `health_sigil`*: Replaces the number on the power or health or both and substitutes the entire value zone with its sigil icon using `power_sigil_center` and `health_sigil_center` to dictate where it goes.
    * *`mox_[color]`* (e.g., `mox_green`, `mox_orange`, `mox_blue`, `mox_prism`) : adds a gem to the mox indicator if the card the sigil is printed onto has one.

---

## The Configuration Blueprint (`general.json`)

The configuration files set the global variables, spatial coordinates, fallback mechanics, export values, rules, and basically everything that is hard-coded. Each temple config file just serves to override some of the values listed in the `general.json` in that specific temple (and often of a specific tier in that temple).

### Architectural Core & Global Toggles

* **`assets_dir`**: The root directory containing the asset packages.
* **`cards_file_path` / `sigils_file_path` / `traits_file_path`**: Defines what files the formatter reads the data from.
* **`write_art_credit` / `write_card_metadata`**: Toggles whether credit tags and metadata elements are written on the cards.
* **`show_power_sigil` / `show_health_sigil`**: Toggles the display mode for custom stat replacements. If a card features a stat-modifying sigil, setting these to true replaces standard numbers with full sigil graphics.
* **`show_conduit_sigil_indicators`**: Controls whether to show the conduit sigil indicators (the large sigil bar on top) or not.
* **`center_card_name`**: Switches between centering card titles or anchoring them to the left side using `name_left_border`.
* **`traits_at_bottom`**: Switches between pinning traits to the bottom of the layout frame (`sigil_bottom_border`), or to stack them directly underneath the sigils.

### Printing Formats

The formatter contains three separate rendering formats to ensure content fits cleanly onto the card face. It checks them sequentially based on these configuration flags:

1. **`allow_default_formatting`**: The primary mode. Large, clear sigils, wide descriptions, and full-scale graphics.
2. **`allow_shortened_formatting`**: The first fallback. If default formatting overflows the card boundaries, this flag permits a compact rendering mode that shrinks sigils and condenses line spacing.
3. **`allow_base_game_display`**: The final fallback. If the sigil list still overflows, this flag triggers an *Inscryption*-style layout: it drops the descriptions entirely and grids out standalone raw sigil assets horizontally across the card face.

### Export Settings

* **`export_sorted_by_folder`**: Automates output organization, sorting generated cards into subdirectories named after their respective temples.
* **`export_color`**: An RGB list (e.g., `[0, 0, 0]`) setting the sigils to a certain color.
* **`export_normal_formatting` / `export_shorter_formatting` / `export_base_game_formatting`**: Standard output filters directing which sigil variants are to be printed.
* **`export_sigil_patches` / `export_sigil_description_icon` / `export_trait_description_icon` / `exported_traitline`**: Exports variants of the sigil icons.

### Typography, Color Routing & Scale

* **`font`**: Points to the target `.TTF` font package inside the `data/fonts` directory.
* **`default_tier`**: The baseline tier fallback used whenever a card's tier value is missing or invalid.
* **`[element]_font_size` / `[element]_max_width`**: Global controls handling font dimensions and text wrapping boundaries for names, flavor text, metadata, stats, and sigils.
* **`[element]_color_index`**: Maps structural text elements directly to index slots in the color arrays (`colors.png`). The values match the formatter's internal offset calculations (`index - 1`).

### Spacing & Grid Boundaries

* **`sigil_img_scale`**: Scale percentage multiplier (e.g., `100` for 1:1 scale) for the size of the sigil art.
* **`allow_colored_sigils`**: Toggles whether sigils retain native colors or are swapped out for monochromatic outline variants.
* **`sigil_img_space` / `sigil_space`**: Defines the canvas boundaries for drawing sigils.
* **`sigil_vertical_spacing` / `traitline_vertical_spacing` / `trait_vertical_spacing`**: Spacing to give the text some air.

### Coordinate Mapping

* **`cost_right_border` / `cost_left_border` / `cost_bottom_border`**: A bounding box that dictates exactly where the card cost renders.
* **`cost_right_border_gemification_displacement`**: Adjusts the right-hand layout margin when costs feature gemification.
* **`name_top_border` / `name_left_border` / `flavor_text_top_border` / `flavor_text_left_border` / `metadata_top_border` / `art_credit_top_border`**: Fixed positions for text labels.
* **`indicator_displacement`**: An offset value that shifts flavor text and sigils downwards if an indicator (like conduit or mox) is present.
* **`sigil_top_border` / `sigil_left_border` / `sigil_bottom_border`**: Establishes the layout space for rendering sigils and traits.
* **`power_sigil_center` / `health_sigil_center`**: Precise midpoint for centering replacement sigil icons.
* **`power_coord` / `health_coord`**: Fixed points for drawing the stats.

### Gemification, Patch & Conditional Bounds

* **`gemification_[stat]_*`**: Bounding dimensions and text layout anchors used when stats are gemified.
* **`gemification_sigil_*` / `cell_sigil_*` / `latch_sigil_*`**: Sets custom vertical adjustments and dictates when the formatter swaps out small, medium, or large background patches based on the size of the sigil.
* **`left_latch_head_border` / `right_latch_head_border`**: Sets precise positionings for the heads of the latchers.
* **`arcane_sigil_*` / `tribal_sigil_*`**: Sets the vertical adjustement and custom text for arcane and tribal sigils.

### The Overrides Cascading Inheritance Tree

The `overrides` block specifies custom properties that automatically trigger based on a card's theme or rarity.

```json
"overrides": {
    "default": {
        "uncommon": {
            "sigil_bottom_border": 1440
        }
    },
    "bloodless": {
        "default": {
            "sigil_bottom_border": 1440,
            "power_sigil_center": [215, 930],
            "power_coord": [193, 885]
        },
        "uncommon": {
            "sigil_bottom_border": 1450
        }
    }
}

```

When generating a card, the system resolves its configuration by applying settings in a strict order of priority:

1. It starts by loading all baseline settings from the global configuration file.
2. If a specific background modifier tag is detected (e.g., `bloodless_bg`), the formatter jumps into that theme's override block and applies its baseline values (found under `"default"`).
3. Finally, it checks the card's `Tier` value. If a matching rarity block exists within that theme's section, those settings are applied last, overriding any previous values.

This structure allows the fine-tuning layouts. For example, if a specific background theme uses a thicker bottom border (like the Rare Beast one), we can adjust the layout boundaries for that entire subset of cards without breaking the global layout rules.

Here is the clear, user-friendly breakdown of how the asset and color systems function under the hood, written for non-programmers who want to customize their card templates.

---

## Assets & Colors

### Temple Assets vs. General Assets

The `assets/` directory is split into two distinct zones:

* **Temple Folders (e.g., `assets/beast`, `assets/undead`)**: These contain assets unique to a specific card theme. If a card belongs to the Beast temple, the formatter checks the `beast` folder first for its artwork, backgrounds, etc.
* **General Assets (`assets/general_assets`)**: This is the universal folder. If the formatter can't find a specific asset inside a given temple folder, it grabs the standard version from here.

### Image Search Hierarchy (How Files Are Found)

Whenever the formatter draws a card component (like a cardback or a frame modifier), it hunts for the file by combining the card’s **Tier** and **Background Modifier** (defined in the card's `Tags`). It checks directories from the most specific to the most general.

For example, if we are generating a **Rare** card with a **bloodless_bg** tag in the **Beast** temple, the formatter will search for the card background image in this exact order:

1. `assets/beast/rare_bloodless_bg.png` *(Temple + Tier + Modifier)*
2. `assets/beast/rare_bg.png` *(Temple + Tier)*
3. `assets/beast/bloodless_bg.png` *(Temple + Modifier)*
4. `assets/beast/bg.png` *(Temple)*
5. `assets/general_assets/cardbacks/rare_bloodless_bg.png` *(Tier + Modifier)*
6. `assets/general_assets/cardbacks/rare_bg.png` *(Tier)*
7. `assets/general_assets/cardbacks/bloodless_bg.png` *(Modifier)*
8. `assets/general_assets/cardbacks/bg.png` *(usually doesn't exist)*

If it goes through this entire list and finds nothing, it changes the Tier to the default tier (set in `general.json`) and runs the search one more time before giving up.

### Dynamic Palette System (`colors.png`)

There is no need to manually change text or border colors for different card themes. The formatter handles this dynamically using color mapping files named `colors.png`.

Inside `assets/general_assets/`, there is a master `colors.png` sheet. The formatter looks at the pixels in this master file and swaps them out with the corresponding pixels found in the temple's local `colors.png` file. This single file controls the text color for the flavor text, card metadata, artist credits, trait descriptions, and sigil conditionals like tribal or arcane.

Just like image assets, these color sheets can be specialized. The system searches for color maps in the temple folder using the same naming order:

1. `assets/beast/rare_bloodless_colors.png` *(Temple + Tier + Modifier)*
2. `assets/beast/rare_colors.png` *(Temple + Tier)*
3. `assets/beast/bloodless_colors.png` *(Temple + Modifier)*
4. `assets/beast/colors.png` *(Temple)*
