from model import *

class Cost:

    def __init__(self):
        self.asterisk = False

    @classmethod
    def get_all_subclasses(cls):
        """Recursively finds all subclasses down the inheritance tree."""
        subclasses = set(cls.__subclasses__())
        return subclasses.union([s for c in subclasses for s in c.get_all_subclasses()])

    @classmethod
    def handle_segment(cls, segment: str, current_costs: list) -> bool:
        """
        Each subclass overrides this. 
        Checks if the segment matches its signal, updates current_costs, 
        and returns True if handled.
        """
        return False

    def addAsterisk(self, image: Image.Image) -> Image:
        if self.asterisk:
            asterisk_img = Image.open("assets/general_assets/costs/asterisk.png")
            final_image = Image.new('RGBA', (image.width + asterisk_img.width - 1, max(image.height, asterisk_img.height)))
            final_image.paste(image, (0, final_image.height - image.height))
            final_image.paste(asterisk_img, (image.width - 1, 0), mask=asterisk_img)
            image = final_image
        return image


class Blood(Cost):

    def __init__(self, amount: int):
        self.amount = amount
        super().__init__()

    def __add__(self, other):
        if type(other) is not Blood:
            raise TypeError("Add operation can only be performed on two resources of the same type")
        return Blood(self.amount + other.amount)

    def __sub__(self, other):
        if type(other) is not Blood:
            raise TypeError("Sub operation can only be performed on two resources of the same type")
        return Blood(self.amount - other.amount)

    def getCostImage(self) -> Image:
        cost_img = Image.open(f"assets/general_assets/costs/blood/blood.png").convert("RGBA")

        total_width = cost_img.width * self.amount
        final_img = Image.new('RGBA', (total_width, cost_img.height))
        for i in range(self.amount):
            x_offset = i * cost_img.width
            final_img.paste(cost_img, (x_offset, 0))

        return self.addAsterisk(final_img)

    @classmethod
    def handle_segment(cls, segment: str, current_costs: list) -> bool:
        if "blood" in segment:
            amount = int(segment.split(" ")[0])
            current_costs.append(cls(amount))
            return True
        return False


class Bones(Cost):

    def __init__(self, amount: int):
        self.amount = amount
        super().__init__()

    def __add__(self, other):
        if type(other) is not Bones:
            raise TypeError("Add operation can only be performed on two resources of the same type")
        return Bones(self.amount + other.amount)

    def __sub__(self, other):
        if type(other) is not Bones:
            raise TypeError("Sub operation can only be performed on two resources of the same type")
        return Bones(self.amount - other.amount)

    def getCostImage(self) -> Image:
        bone_img = Image.open("assets/general_assets/costs/bones/bone.png").convert("RGBA")
        if self.amount <= 4: # No need for numbers
            duplicate_bone = bone_img.copy()
            final_width = bone_img.width + (duplicate_bone.width - 1) * (self.amount - 1)
            final_image = Image.new('RGBA', (final_width, bone_img.height))
            final_image.paste(bone_img, (0, 0))

            for i in range(self.amount - 1):
                paste_position = (bone_img.width + (duplicate_bone.width - 1) * i - 1, 0)
                final_image.paste(duplicate_bone, paste_position, duplicate_bone)

        else: # Need numbers
            digits = list(str(self.amount))
            number_img = Image.open(f"assets/general_assets/costs/bones/{digits[0]}.png").convert("RGBA")
            for digit in digits[1:]:
                digit_img = Image.open(f"assets/general_assets/costs/bones/{digit}.png").convert("RGBA")
                if digit_img.height != 11:
                    new_digit_img = Image.new('RGBA', (digit_img.width, 11))
                    new_digit_img.paste(digit_img, (0, 1), digit_img)
                    digit_img = new_digit_img
                        
                new_img = Image.new('RGBA', (number_img.width + digit_img.width - 2, 11))
                new_img.paste(number_img, (0,0), number_img)

                for x in range(2):
                    for y in range(11):
                        left_pixel = new_img.getpixel((number_img.width - 2 + x, y))
                        right_pixel = digit_img.getpixel((x, y))
                        if left_pixel[3] != 0 and right_pixel == (123, 51, 132, 255):
                            digit_img.putpixel((x, y), (0, 0, 0, 255))

                new_img.paste(digit_img, (number_img.width - 2, 0), digit_img)
                number_img = new_img
            
            final_image = Image.new('RGBA', (number_img.width + 16, number_img.height))
            x_img = Image.open(f"assets/general_assets/costs/bones/x.png").convert("RGBA")
            final_image.paste(number_img, (0, 0), number_img)
            final_image.paste(x_img, (number_img.width, number_img.height-8), x_img)
            final_image.paste(bone_img, (number_img.width+7, number_img.height-8), bone_img)

        return self.addAsterisk(final_image)

    @classmethod
    def handle_segment(cls, segment: str, current_costs: list) -> bool:
        if "bone" in segment:
            amount = int(segment.split(" ")[0])
            current_costs.append(cls(amount))
            return True
        return False


class Energy(Cost):

    def __init__(self, current_energy: int = 0, max_energy: int = 0):
        self.current_energy = current_energy
        self.max_energy = max_energy
        super().__init__()

    def __add__(self, other):
        if type(other) is not Energy:
            raise TypeError("Add operation can only be performed on two resources of the same type")
        return Energy(self.current_energy + other.current_energy, self.max_energy + other.max_energy)

    def __sub__(self, other):
        if type(other) is not Energy:
            raise TypeError("Sub operation can only be performed on two resources of the same type")
        return Energy(self.current_energy - other.current_energy, self.max_energy - other.max_energy)

    def getCostImage(self) -> Image:
        cost_image = None
        first_cell = Image.open("assets/general_assets/costs/energy/cell_first.png").convert("RGBA")
        cell = Image.open(f"assets/general_assets/costs/energy/cell.png").convert("RGBA")
        energy = Image.open("assets/general_assets/costs/energy/energy.png").convert("RGBA")
        max_energy = Image.open("assets/general_assets/costs/energy/overcharge.png").convert("RGBA")
        
        if (self.current_energy + self.max_energy) <= 6: # Use the energy bar
            cost_image = Image.new("RGBA", (26, 9))
            cost_image.paste(first_cell, (0, 0))
            for i in range(6, 23, 4):
                cost_image.paste(cell, (i, 0))

            for i in range(2 + 4 * (6 - self.max_energy), 23, 4):
                cost_image.paste(max_energy, (i, 2))

            for i in range(2 + 4 * (6 - self.max_energy - self.current_energy), 23 - 4 * self.max_energy, 4):
                cost_image.paste(energy, (i, 2))
        
        else: # Use energy numbers
            cost_image = None

            if self.current_energy > 0:
                if self.current_energy > 6:
                    digits = list(str(self.current_energy))
                    digits.reverse() # We reverse here so that the cells print properly
                    energy_img = Image.new("RGBA", (10 + 4 * len(digits), 9))
                    for i, digit in enumerate(digits):
                        cell_x = 4 * (len(digits)-1-i)
                        energy_img.paste(first_cell, (cell_x, 0))
                        digit_img = Image.open(f"assets/general_assets/costs/energy/{digit}.png").convert("RGBA")
                        energy_img.paste(digit_img, (cell_x + 2, 2), digit_img)
                    
                    x_img = Image.open(f"assets/general_assets/costs/energy/x.png").convert("RGBA")
                    energy_img.paste(cell, (energy_img.width - 8, 0), cell)
                    energy_img.paste(x_img, (energy_img.width - 8, 2), x_img)
                    energy_img.paste(cell, (energy_img.width - 4, 0), cell)
                    energy_img.paste(energy, (energy_img.width - 4, 2), energy)
                else:
                    energy_img = Image.new("RGBA", (2 + 4 * self.current_energy, 9))
                    energy_img.paste(first_cell, (0, 0))
                    energy_img.paste(energy, (2, 2))
                    for i in range(6, 4 * self.current_energy, 4):
                        energy_img.paste(cell, (i, 0))
                        energy_img.paste(energy, (i, 2))

                cost_image = energy_img

            if self.max_energy > 0:
                if self.max_energy > 6:
                    digits = list(str(self.max_energy))
                    digits.reverse() # We reverse here so that the cells print properly
                    overcharge_img = Image.new("RGBA", (10 + 4 * len(digits), 9))
                    for i, digit in enumerate(digits):
                        cell_x = 4 * (len(digits)-1-i)
                        overcharge_img.paste(first_cell, (cell_x, 0))
                        digit_img = Image.open(f"assets/general_assets/costs/energy/{digit}.png").convert("RGBA")
                        overcharge_img.paste(digit_img, (cell_x + 2, 2), digit_img)
                    
                    x_img = Image.open(f"assets/general_assets/costs/energy/x.png").convert("RGBA")
                    overcharge_img.paste(cell, (energy_img.width - 8, 0), cell)
                    overcharge_img.paste(x_img, (energy_img.width - 8, 2), x_img)
                    overcharge_img.paste(cell, (energy_img.width - 4, 0), cell)
                    overcharge_img.paste(max_energy, (energy_img.width - 4, 2), max_energy)

                    energy_to_overcharge = {
                        (117, 255, 220, 255): (255, 255, 3, 255),
                        (33, 130, 147, 255): (255, 202, 3, 255)
                    }
                    for x in range(2, overcharge_img.width):
                        for y in range(2, overcharge_img.height-1):
                            if overcharge_img.getpixel((x, y)) in energy_to_overcharge:
                                overcharge_img.putpixel((x, y), energy_to_overcharge[overcharge_img.getpixel((x, y))])
                else:
                    overcharge_img = Image.new("RGBA", (2 + 4 * self.max_energy, 9))
                    overcharge_img.paste(first_cell, (0, 0))
                    overcharge_img.paste(max_energy, (2, 2))
                    for i in range(6, 4 * self.max_energy, 4):
                        overcharge_img.paste(cell, (i, 0))
                        overcharge_img.paste(max_energy, (i, 2))

                if cost_image:
                    new_cost_img = Image.new("RGBA", (cost_image.width + overcharge_img.width, 9))
                    new_cost_img.paste(cost_image, (0, 0))
                    new_cost_img.paste(overcharge_img, (cost_image.width, 0))
                    cost_image = new_cost_img
                else:
                    cost_image = overcharge_img
        
        return self.addAsterisk(cost_image)

    @classmethod
    def handle_segment(cls, segment: str, current_costs: list) -> bool:
        if "energy" in segment or "max" in segment:
            # Look for an already existing Energy instance in the list
            energy_inst = next((c for c in current_costs if isinstance(c, cls)), None)
            amount = int(segment.split(" ")[0])
            
            if "energy" in segment:
                if energy_inst:
                    energy_inst.current_energy = amount
                else:
                    current_costs.append(cls(current_energy=amount))
            elif "max" in segment:
                if energy_inst:
                    energy_inst.max_energy = amount
                else:
                    current_costs.append(cls(max_energy=amount))
            return True
        return False


class Gems(Cost):

    def __init__(self, *gems: str):
        self.gems = list(gems)
        super().__init__()

    def __add__(self, other):
        if type(other) not in [Gems, str]:
            raise TypeError('Add operation between gems may only be done with objects of type Gems or str.')
        return Gems(*list(self.gems + (other.gems if type(other) is Gems else [other])))

    def __sub__(self, other):
        if type(other) not in [Gems, str]:
            raise TypeError('Sub operation between gems may only be done with objects of type Gems or str.')
        if type(other) is str:
            other = [other]
        gems = self.gems[:]
        for gem in other.gems:
            if gem in gems:
                gems.remove(gem)
        return Gems(*gems)

    def copy(self):
        return Gems(*self.gems[:])

    @staticmethod
    def getGemImage(gem) -> Image:
        shatter = "_shatter" if "shattered" in gem else ""
        gem = gem.split(" ")[-1].lower()
        color = dict(emeralds="emerald", sapphires="sapphire", rubies="ruby", prisms="prism").get(gem, gem)
        img = Image.open(f"assets/general_assets/costs/gems/{color.lower()}{shatter}.png").convert("RGBA")
        return img

    def getCostImage(self) -> Image:
        gem_images = []
        for gem in self.gems:
            image = self.getGemImage(gem)
            for _ in range(int(gem.split(" ")[0])):
                gem_images.append(image)

        total_width = sum(img.width for img in gem_images) - (len(gem_images) - 1)
        max_height = max(img.height for img in gem_images)

        cost_image = Image.new("RGBA", (total_width, max_height), (255, 255, 255, 0))

        offset = 0
        for img in gem_images:
            if img.height == 90 and img.height != max_height:
                paste_position = (offset, 1)
            else:
                paste_position = (offset, 0)

            cost_image.paste(img, paste_position, mask=img)
            offset += img.width - 1
        return self.addAsterisk(cost_image)

    @classmethod
    def handle_segment(cls, segment: str, current_costs: list) -> bool:
        gem_keywords = ["emerald", "sapphire", "ruby", "rubies", "prism"]
        if any(gem in segment for gem in gem_keywords):
            # If a Gems instance already exists, add this segment to it
            for idx, c in enumerate(current_costs):
                if isinstance(c, cls):
                    current_costs[idx] = c + segment
                    return True
            # Otherwise, create a new one
            current_costs.append(cls(segment))
            return True
        return False


def get_cost(strcost):
    cost = []
    if strcost is None:
        return cost
    try:
        for c in strcost.split(" + "):
            handled = False
            # Dynamically check every subclass of Cost
            for subclass in Cost.get_all_subclasses():
                if subclass.handle_segment(c, cost):
                    handled = True
                    break  # Stop checking other classes for this segment
            if not handled:
                raise KeyError(f"Unknown cost type: {c}")
        return cost
    except KeyError as e:
        print(f"Error: {e}")
        logging.error(f"Error: {e}")
