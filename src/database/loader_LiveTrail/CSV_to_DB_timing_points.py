import os
import csv
import sqlite3
import argparse
from database.database import Event
from database.create_db import Database
from database.loader_LiveTrail import db_LiveTrail_loader


# Function to connect to SQLite database
def connect_to_db(db_file):
    conn = sqlite3.connect(db_file, timeout=3600)
    return conn


# Function to fetch race_id and event_id from races table
def fetch_race_event_ids(cursor, filepath):
    cursor.execute("SELECT race_id, event_id FROM races WHERE results_filepath=?", (filepath,))
    row = cursor.fetchone()
    if row:
        return row
    else:
        return None


# Function to fetch race_id and event_id from races table
def fetch_all_event_ids(cursor):
    cursor.execute("SELECT DISTINCT(event_id) FROM races WHERE results_filepath IS NOT NULL AND results_filepath NOT LIKE ''")
    event_ids = []
    for row in cursor.fetchall():
        event_ids.append(row[0])
    return event_ids


# Function to fetch information from control_points table
def fetch_control_points(cursor, race_id, event_id):
    cursor.execute('''
        SELECT code, name, distance, elevation_pos, elevation_neg, control_point_id
        FROM control_points WHERE race_id = ? AND event_id = ?
        ORDER BY distance
    ''', (race_id, event_id,))
    rows = cursor.fetchall()
    control_points = {}
    control_points_names = {}
    control_points_ids = {}
    for row in rows:
        control_points[row[0]] = (row[2], row[3], row[4])
        control_points_names[row[0]] = row[1]
        control_points_ids[row[0]] = row[-1]
    return control_points, control_points_names, control_points_ids


# Function to insert data into results table
def insert_into_timing_points(cursor, race_id, event_id, data):
    for row in data:
        bib = row[0]
        times = row[1]
        cps, cps_names, cps_ids = fetch_control_points(cursor, race_id, event_id)

        if len(cps_ids) == len(times) + 1:  # This means there is no time for the starting control point
            cps_ids.popitem()
        elif len(cps_ids) != len(times):
            print(f"cps_ids: {len(cps_ids)}, times: {len(times)}")
            with open('timing_points.log', 'a') as file:
                # Write the new line to the file
                file.write(f"{event_id} {race_id}. cps_ids: {len(cps_ids)}, times: {len(times)}\n")
            raise ValueError("Lengths of control points and times do not match")

        for control_point_id, time in zip(cps_ids.values(), times):
            cursor.execute("""
                INSERT INTO timing_points (control_point_id, race_id, event_id, bib, time)
                VALUES (?, ?, ?, ?, ?)
            """, (control_point_id, race_id, event_id, bib, time))


# Function to read CSV file
def read_csv(file_path):
    with open(file_path, newline='', encoding='utf-8') as csvfile:
        reader = csv.reader(csvfile)
        next(reader)  # Skip header
        # CSV file header is
        # n, doss, nom, prenom, cat, {numbers for each control point of variable length}
        return [[row[1], row[5:]] for row in reader]


def clean_table(cursor):
    cursor.execute('''
        DELETE
        FROM timing_points
    ''')


def main(path: str = '../data/parsed_data.db', data_folder: str = '../../data/', clean: bool = False, update: str = None):
    '''
    Args:
        path (str): Path to SQLite3 DB.
        data_folder (dict): Path to the directory containing folders of CSV files.
        clean (bool): If True, the tables will be emtied before execution.
        update (str): If specified, path for the file containing the list of files in the DB before
                        executing the main script (db_LiveTrail_loader)
    '''
    # Path to the directory containing folders of CSV files
    data_folder = '../../data/'

    db: Database = Database.create_database(path=path)

    if clean:
        db_connection = connect_to_db(db.path)
        with db_connection:
            cursor = db_connection.cursor()
            clean_table(cursor)
            print('timing_points table emptied')
    folders = os.listdir(data_folder)
    if update:
        _, db_years = Event.get_events_years(db)
        parsed_data = db_LiveTrail_loader.parse_events_years_txt_file(update)
        _, years = db_LiveTrail_loader.get_years_only_in_v1(db_years, db_years, parsed_data)
        folders = list(years.keys())
        db_LiveTrail_loader.save_years_to_txt('updated_events_years.txt', years)
    print("INFO: Inserting data into Timing Points table.")
    # Iterate through folders
    for folder in folders:
        folder_path = os.path.join(data_folder, folder)
        if os.path.isdir(folder_path):
            # Iterate through CSV files in the folder
            for file in os.listdir(folder_path):
                if file.endswith('.csv'):
                    if update and not any(file.endswith(f'{year}.csv') for year in years):
                        continue
                    file_path = os.path.join(folder_path, file)
                    # Fetch race_id and event_id from races table

                    db_connection = connect_to_db(db.path)
                    with db_connection:
                        cursor = db_connection.cursor()
                        race_event_ids = fetch_race_event_ids(cursor, f'data/{folder}/{file}')
                        if race_event_ids:
                            race_id, event_id = race_event_ids
                            print(f'Inserting data into {event_id}. {folder}, {race_id}')
                            # Read CSV file
                            csv_data = read_csv(file_path)
                            # Insert data into timing_points table
                            try:
                                insert_into_timing_points(cursor, race_id, event_id, csv_data)
                            except sqlite3.IntegrityError:
                                pass
                            except ValueError:
                                pass
                        db_connection.commit()
                    db_connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Data loader from CSV files into results table.')
    parser.add_argument('-p', '--path', default='../data/parsed_data.db', help='DB path.')
    parser.add_argument('-c', '--clean', action='store_true', help='Remove all data from table before execution.')
    parser.add_argument('-u', '--update', default='update.txt', help='Filepath to list of events and years to update.')

    args = parser.parse_args()
    path = args.path
    clean = args.clean
    update = args.update

    main(path=path, clean=clean, update=update)
