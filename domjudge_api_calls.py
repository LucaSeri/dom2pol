import random
import string
import requests
import os
from dotenv import load_dotenv
from result import Ok, Err, Result
import base64

import shutil
import zipfile

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import time
import os

domjudge_url = "https://judge.agm-contest.com"
prepare_contest = 2
export_contests_dir = "./exported_contests"

def export_problem(contest_id, problem_id, username, password, headless=True):
    # Set up Chromium options
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless")
    
    # Set up the download directory
    download_dir = os.path.join(os.getcwd(), 'downloads')
    os.makedirs(download_dir, exist_ok=True)
    for f in os.listdir(download_dir):
        os.remove(os.path.join(download_dir, f))

    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    }

    chrome_options.add_experimental_option("prefs", prefs)

    # Initialize the Service object for ChromiumDriver
    service = Service("/usr/lib/chromium-browser/chromedriver")

    # Initialize the WebDriver with Chromium
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    try:
        # Open the problem export page
        url = f"https://judge.agm-contest.com/login"
        driver.get(url)

        # Handle login if prompted
        if "login" in driver.current_url.lower():
            username_field = driver.find_element(By.ID, "username")
            password_field = driver.find_element(By.ID, "inputPassword")

            username_field.send_keys(username)
            password_field.send_keys(password)
            password_field.send_keys(Keys.RETURN)

        # Wait for a short period to ensure we are logged in
        time.sleep(5)  # Adjust this time if necessary

        # Open the problem export page
        url = f"https://judge.agm-contest.com/jury/problems/{problem_id}/export"
        driver.get(url)

        # Wait for the download to complete by monitoring the download directory
        download_complete = False
        timeout = 120  # Set a maximum wait time in seconds
        start_time = time.time()

        while not download_complete:
            # Check the download directory for any files without a .crdownload extension
            downloaded_files = [f for f in os.listdir(download_dir) if not f.endswith('.crdownload')]
            if downloaded_files:
                download_complete = True
                break
            
            # Check if the timeout has been reached
            if time.time() - start_time > timeout:
                return Err("Download timed out")

            time.sleep(1)  # Wait for 1 second before checking again

        return Ok(os.path.join(download_dir, downloaded_files[0]))

    except Exception as e:
        return str(e)
    
    finally:
        # Close the WebDriver
        driver.quit()


def get_contest_problems(contest_id, username, password):
    response = requests.get(f"{domjudge_url}/api/v4/contests/{contest_id}/problems", auth=(username, password))

    if response.status_code == 200:
        return Ok(response.json())
    else:
        return Err(response.text)
    
def get_correct_submission_for_problem(contest_id, problem_id, username, password):
    response = requests.get(f"{domjudge_url}/api/v4/contests/{contest_id}/submissions", auth=(username, password))

    if response.status_code != 200:
        return Err(response.text)
    
    submissions = response.json()

    # We also need all judgements
    response = requests.get(f"{domjudge_url}/api/v4/contests/{contest_id}/judgements", auth=(username, password))
    if response.status_code != 200:
        return Err(response.text)
    
    judgements = response.json()

    # Keep all judgements whose judgement_type_id is "AC" in a dictionary
    ac_judgements = {}
    for judgement in judgements:
        if judgement["judgement_type_id"] == "AC":
            ac_judgements[judgement["submission_id"]] = judgement

    # Keep the lowest id submission that has an AC judgement
    correct_submission = None
    for submission in submissions:
        if submission["problem_id"] == problem_id and submission["language_id"] == "cpp":
            if submission["id"] in ac_judgements:
                if correct_submission is None or submission["id"] > correct_submission["id"]:
                    correct_submission = submission

    if correct_submission is not None:
        return Ok(correct_submission)
    
    return Err("No correct submission found")

def export_correct_submission_for_problem(contest_id, problem_id, username, password):
    correct_submission = get_correct_submission_for_problem(contest_id, problem_id, username, password)
    if correct_submission.is_err():
        return correct_submission

    id = correct_submission.unwrap()["id"]
    response = requests.get(f"{domjudge_url}/api/v4/contests/{contest_id}/submissions/{id}/source-code", auth=(username, password))

    # Save the source code to a file in downloads
    if response.status_code == 200:
        filename = "downloads/main.cpp"
        with open(filename, "w") as f:
            # Take the "source" field from the response and decode it from base64
            f.write(base64.b64decode(response.json()[0]["source"]).decode())

        
        return Ok(filename)
    
    return Err(response.text)

def export_problem_with_submission(contest_id, problem_id, username, password):
    # Export the problem
    problem_file = export_problem(contest_id, problem_id, username, password)
    print(problem_file)
    if problem_file.is_err():
        return problem_file

    # Export the correct submission
    submission_file = export_correct_submission_for_problem(prepare_contest, problem_id, username, password)
    print(submission_file)
    if submission_file.is_err():
        return submission_file

    exported_problem_path = os.path.join(export_contests_dir, str(contest_id), str(problem_id))
    os.makedirs(exported_problem_path, exist_ok=True)

    # Unzip the problem file in the directory
    with zipfile.ZipFile(problem_file.unwrap(), "r") as zip_ref:
        zip_ref.extractall(exported_problem_path)

    # Copy the submission file
    shutil.copy(submission_file.unwrap(), os.path.join(exported_problem_path, "main.cpp"))

    return Ok(exported_problem_path)

def export_contest(contest_id, username, password):
    # Get the list of problem IDs
    problems = get_contest_problems(contest_id, username, password)

    # For each problem, first export it
    for problem in problems.unwrap():
        export_problem_with_submission(contest_id, problem["id"], username, password)
