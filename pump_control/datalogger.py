import os
import csv

def log_data(directory:str,filename:str,data:list[float],column_headers:list[str] = [""]):
    total_path = f"{directory}/{filename}.csv"
    if os.path.isfile(total_path):
        with open(total_path,mode="a") as f:
            writer = csv.writer(f,delimiter=",")
            
            writer.writerow(data)
    else:
        if not os.path.isdir(directory):
            os.makedirs(directory)
        with open(total_path,mode="a+") as f:
            writer = csv.writer(f,delimiter = ",")
            writer.writerow(column_headers)
            writer.writerow(data)