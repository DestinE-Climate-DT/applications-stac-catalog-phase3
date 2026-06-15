import os
from calendar import monthrange

BASE_DIR = "/gpfs/scratch/ehpc01/bsc032056/a314/output/energy_indicators/20150101/member01"

model="ifs-nemo"
experiment="ssp3-7.0"
generation="2"
realization="1"
activity="projections"
resolution="high"

print("hi")

# 🔹 Toggle this to False to actually execute changes
DRY_RUN = True

for year in os.listdir(BASE_DIR):
    year_path = os.path.join(BASE_DIR, year)

    if not os.path.isdir(year_path) or not year.isdigit():
        continue

    for month in os.listdir(year_path):
        month_path = os.path.join(year_path, month)

        if not os.path.isdir(month_path) or not month.isdigit():
            continue

        yyyy = year
        mm = month.zfill(2)

        # First and last day of the month
        start_day = "01"
        last_day = str(monthrange(int(yyyy), int(mm))[1]).zfill(2)

        start_date = f"{yyyy}{mm}{start_day}T000000"
        end_date = f"{yyyy}{mm}{last_day}T230000"

        new_folder_name = (
            f"EO.BSC.DAT.ENERGY_INDICATORS_"
            f"{start_date}_{end_date}__{model}__{experiment}__{generation}__{realization}__{activity}__{resolution}"
        )

        new_folder_path = os.path.join(year_path, month, new_folder_name)

        # If the folder already exists, skip
        if os.path.exists(new_folder_path):
            print(f"Skipping (already exists): {new_folder_path}")
            continue

        print(f"{'[DRY RUN] ' if DRY_RUN else ''}Creating: {new_folder_path}")

        if not DRY_RUN:
            os.makedirs(new_folder_path)

        # Move all contents into the new folder
        for item in os.listdir(month_path):
            item_path = os.path.join(month_path, item)

            # Skip the newly created folder itself
            if item_path == new_folder_path:
                continue

            dest_path = os.path.join(new_folder_path, item)

            print(f"{'[DRY RUN] ' if DRY_RUN else ''}Moving: {item_path} -> {dest_path}")

            if not DRY_RUN:
                os.rename(item_path, dest_path)

