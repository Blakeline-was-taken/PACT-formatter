import csv

# Define the input and output filenames
input_file_cards = 'data/cards.csv'
output_file_cards = 'data/updated_cards.csv'
input_file_sigils = 'data/sigils.csv'
output_file_sigils = 'data/updated_sigils.csv'
input_file_traits = 'data/traits.csv'
output_file_traits = 'data/updated_traits.csv'

def generate_filename(name):
    # Removes spaces, single quotes, commas, hyphens, exclamation marks, and question marks
    return name.translate(str.maketrans("", "", " ',-!?")) + ".png"

with open(input_file_cards, mode='r', encoding='utf-8') as infile:
    reader = csv.DictReader(infile)
    # Get original fieldnames and insert 'Art File' at index 1
    fieldnames = reader.fieldnames
    new_fieldnames = fieldnames[:1] + ['Art File'] + fieldnames[1:] + ['Tags']
    with open(output_file_cards, mode='w', encoding='utf-8', newline='') as outfile:
        writer = csv.DictWriter(outfile, fieldnames=new_fieldnames)
        writer.writeheader()
        for row in reader:
            # Generate the new column value
            row['Art File'] = generate_filename(row['Card Name'])
            tags = []
            if "Bloodless" in row["Sigils"] + row["Traits"]:
                tags.append("bloodless_bg")
            row["Tags"] = ', '.join(tags)
            writer.writerow(row)


with open(input_file_sigils, mode='r', encoding='utf-8') as infile:
    reader = csv.DictReader(infile)
    # Define new headers: Keep Name and Description, replace last 2 with 'Tags'
    fieldnames = ['Name', 'Description', 'Tags']
    with open(output_file_sigils, mode='w', encoding='utf-8', newline='') as outfile:
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in reader:
            tags = []
            # Update the icons
            row["Description"] = row["Description"].replace("["; "{").replace("]", "}")
            # Check Can_be_colored (if empty, add has_color)
            if row['Can_be_colored'] and not row['Can_be_colored'].strip():
                tags.append('has_color')
            # Check Is_attack_sigil (if filled, add power_sigil)
            if row['Is_attack_sigil'] and row['Is_attack_sigil'].strip():
                tags.append('power_sigil')
            # Check if the sigil is a conduit (has "Conduit" in its name)
            if row["Name"] and "Conduit" in row["Name"]:
                tags.append('conduit_sigil')
            # Check if the sigil provides a gem (has " Gem" in its name)
            if row["Name"] and " Gem" in row["Name"]:
                for gem in ["Green", "Orange", "Blue"]:
                    if gem in row["Description"]:
                        tags.append('mox_' + gem.lower())
                if "every color" in row["Description"]:
                    tags.append('mox_prism')
            # Prepare new row
            new_row = {
                'Name': row['Name'],
                'Description': row['Description'],
                'Tags': ', '.join(tags)
            }
            writer.writerow(new_row)


with open(input_file_traits, mode='r', encoding='utf-8') as infile:
    reader = csv.DictReader(infile)
    # Define new headers: Keep Name and Description, replace last one with 'Tags'
    fieldnames = ['Name', 'Description', 'Tags']
    with open(output_file_traits, mode='w', encoding='utf-8', newline='') as outfile:
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in reader:
            tags = []
            # Update the icons
            row["Description"] = row["Description"].replace("["; "{").replace("]", "}")
            # Check Is_attack_sigil (if filled, add power_sigil)
            if row['Is_attack_sigil'] and row['Is_attack_sigil'].strip():
                tags.append('power_sigil')
            # Prepare new row
            new_row = {
                'Name': row['Name'],
                'Description': row['Description'],
                'Tags': ', '.join(tags)
            }
            writer.writerow(new_row)


print(f"Processed cards file saved as '{output_file_cards}'.")
print(f"Processed sigils file saved as '{output_file_sigils}'.")
print(f"Processed traits file saved as '{output_file_traits}'.")