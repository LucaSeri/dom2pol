import random
import string
import time
import hashlib
import requests
import os
from result import Ok, Err, Result

from PyPDF2 import PdfReader, PdfWriter
from io import BytesIO

def serialize_file(path):
    with open(path, "r") as f:
        return f.read()
    
def generate_apisig(methodName, api_secret, params):
    first = "".join(random.choices(string.ascii_letters + string.digits, k=6))

    encoded_params = []
    for key, value in params.items():
        if isinstance(value, bytes):
            encoded_params.append((key.encode(), value))
        else:
            encoded_params.append((key.encode(), str(value).encode()))

    sorted_params = sorted(encoded_params)

    # print the key of the sorted params
    tohash = (f"{first}/{methodName}?").encode()
    for key, value in sorted_params:
        tohash += key + b"=" + value + b"&"

    tohash = tohash[:-1]
    tohash += (f"#{api_secret}").encode()

    return first + hashlib.sha512(tohash).hexdigest()

def convert_to_bytes(x):
    if isinstance(x, bytes):
        return x
    return bytes(str(x), 'utf8')

def send_request(methodName, api_key, api_secret, params):
        print("sending " + methodName)
        params["apiKey"] = api_key
        params["time"] = int(time.time())
        
        signature_random = ''.join([chr(random.SystemRandom().randint(0, 25) + ord('a')) for _ in range(6)])
        signature_random = convert_to_bytes(signature_random)
        for i in params:
            params[i] = convert_to_bytes(params[i])
        param_list = [(convert_to_bytes(key), params[key]) for key in params]
        param_list.sort()
        signature_string = signature_random + b'/' + convert_to_bytes(methodName)
        signature_string += b'?' + b'&'.join([i[0] + b'=' + i[1] for i in param_list])
        signature_string += b'#' + convert_to_bytes(api_secret)
        params["apiSig"] = signature_random + convert_to_bytes(hashlib.sha512(signature_string).hexdigest())
        url =  'https://polygon.codeforces.com/api/' + methodName
        result = requests.post(url, files=params)

        print ("done with " + methodName)
        if result.status_code == 200:
            return Ok(result.json())
        else:
            return Err(result.text)

def create_problem(api_key, api_secret, name):
    params = {
        "name": name,
    }

    return send_request("problem.create", api_key, api_secret, params)

# time_limit is in milliseconds
# memory_limit is in megabytes
def set_limits(api_key, api_secret, problem_id, time_limit, memory_limit):
    params = {
        "memoryLimit": memory_limit,
        "problemId": problem_id,
        "timeLimit": time_limit,
    }

    return send_request("problem.updateInfo", api_key, api_secret, params)

def set_validator(api_key, api_secret, problem_id, validator_name):
    params = {
        "problemId": problem_id,
        "validator": validator_name,
    }

    return send_request("problem.setValidator", api_key, api_secret, params)

def set_checker(api_key, api_secret, problem_id, checker_name):
    params = {
        "checker": checker_name,
        "problemId": problem_id,
    }

    return send_request("problem.setChecker", api_key, api_secret, params)

def add_main_sol(api_key, api_secret, problem_id, sol_path):
    params = {
        "file": serialize_file(sol_path),
        "name": "main.cpp",
        "problemId": problem_id,
        "tag": "MA",
    }

    return send_request("problem.saveSolution", api_key, api_secret, params)

def add_test(api_key, api_secret, problem_id, test_path, sample, test_idx):
    params = {
        "problemId": problem_id,
        "testIndex": test_idx,
        "testInput": serialize_file(test_path),
        "testset": 'tests',
        "testUseInStatements": ('true' if sample else 'false'),
    }

    return send_request("problem.saveTest", api_key, api_secret, params)

def add_file(api_key, api_secret, problem_id, file_path, typ):
    params = {
        "file": serialize_file(file_path),
        "name": file_path.split("/")[-1],
        "problemId": problem_id,
        "type": typ,
    }

    return send_request("problem.saveFile", api_key, api_secret, params)

def add_statement_resource(api_key, api_secret, problem_id, statement_path):
    # Embed the pdf as a sequence of bytes
    # Read the pdf
    reader = PdfReader(statement_path)

    # Split it into one page pdfs -> problem1.pdf, problem2.pdf, ...
    for i, page in enumerate(reader.pages):
        writer = PdfWriter()
        writer.add_page(page)

        # Write the page at statemetn_path + i
        # Take the statement_path and remove the .pdf extension
        writer.write(open(statement_path[:-4] + str(i) + ".pdf", "wb"))

    # Upload each pdf as a resource
    for i in range(len(reader.pages)):
        pdf_path = statement_path[:-4] + str(i) + ".pdf"

        file_content = open(pdf_path, "rb").read()

        params = {
            "name": "problem" + str(i) + ".pdf",
            "problemId": problem_id,
            "file": file_content,
        }
        
        ret = send_request("problem.saveStatementResource", api_key, api_secret, params)
        # print the sent request for debugging
        if ret.is_err():
            return ret
        
    return Ok(None)

def add_statement(api_key, api_secret, problem_id, problem_name, problem_path):
    # Find number of "problemx.pdf" files
    pdfs = [f for f in os.listdir(problem_path) if f.endswith(".pdf")]
    # Remove the problem.pdf file
    pdfs.remove("problem.pdf")

    # Add each pdf as a resource
    resources = ""
    for i in range(len(pdfs)):
        resources += f"\\includegraphics{{problem{i}.pdf}}\n"

    legend = "\\begin{center}\n" + resources + "\\end{center}\n"

    params = {
        "lang": "english",
        "name": problem_name,
        "legend": legend,
        "problemId": problem_id,
    }

    return send_request("problem.saveStatement", api_key, api_secret, params)

def get_problems(api_key, api_secret):
    params = {}
    
    result = send_request("problems.list", api_key, api_secret, params)

    if result.is_err():
        return result
    
    return Ok(result.unwrap()["result"])

def commit_changes(api_key, api_secret, problem_id):
    params = {
        "problemId": problem_id,
        "minorChanges": "true",
    }

    return send_request("problem.commitChanges", api_key, api_secret, params)

def build_package(api_key, api_secret, problem_id):
    params = {
        "problemId": problem_id,
        "full": "true",
        "verify": "true",
    }

    return send_request("problem.buildPackage", api_key, api_secret, params)