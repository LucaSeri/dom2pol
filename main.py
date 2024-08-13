from dotenv import load_dotenv
import click
import os
from result import Result, Ok, Err
import yaml
import configparser

from polygon_api_calls import *
from domjudge_api_calls import export_contest

def is_domjudge_problem(path):
    # path should be a directory
    if not os.path.isdir(path):
        return False
    
    # there should be a domjudge-problem.ini and a problem.yaml file
    if not os.path.exists(os.path.join(path, "domjudge-problem.ini")):
        return False
    
    if not os.path.exists(os.path.join(path, "problem.yaml")):
        return False
    
    return True

def get_problem_id(api_key, api_secret, problem_name):
    # Get all problems
    problems = get_problems(api_key, api_secret)
    if problems.is_err():
        return problems

    # Find the problem with the given name
    for problem in problems.unwrap():
        if problem["name"] == problem_name:
            return Ok(problem["id"])
    
    return Err("Problem not found")

def add_problem_from_dir(api_key, api_secret, path, name_prefix):
    print("Adding problem from " + path)
    # Check if the directory is a Domjudge problem
    if not is_domjudge_problem(path):
        return Err("Directory is not a Domjudge problem")
    
    # Read the problem.yaml file
    problem_yaml_path = os.path.join(path, "problem.yaml")
    with open(problem_yaml_path, "r") as f:
        problem_yaml = yaml.load(f, Loader=yaml.FullLoader)

    domjudge_ini_path = os.path.join(path, "domjudge-problem.ini")
    config = configparser.ConfigParser()
    with open(domjudge_ini_path) as stream:
        config.read_string("[problem]\n" + stream.read())

    # Get the problem name
    problem_name = problem_yaml["name"]
    # Replace all spaces with dashes
    problem_name = problem_name.replace(" ", "-")
    # Turn it to lowercase
    problem_name = problem_name.lower()
    if name_prefix is not None:
        problem_name = name_prefix + problem_name
    
    ret = create_problem(api_key, api_secret, problem_name)
    if ret.is_err() and not "already have" in ret.unwrap_err():
        return ret

    # Get the problem ID
    problem_id = get_problem_id(api_key, api_secret, problem_name)
    if problem_id.is_err():
        return problem_id
    
    # Get the time limit. It is a float in seconds, wrapped in ''
    time_limit = float(config["problem"]["timelimit"][1:-1])
    # Convert it to milliseconds
    time_limit = int(time_limit * 1000)

    memory_limit = 2048 # 2 GB default

    # The yaml might optionnaly have a limits field with a memory limit
    if "limits" in problem_yaml:
        memory_limit = problem_yaml["limits"]["memory"]

    memory_limit = min(memory_limit, 1024)

    ret = set_limits(api_key, api_secret, problem_id.unwrap(), time_limit, memory_limit)
    if ret.is_err():
        return ret

    ret = add_statement_resource(api_key, api_secret, problem_id.unwrap(), os.path.join(path, "problem.pdf"))
    if ret.is_err():
        return ret

    ret = add_statement(api_key, api_secret, problem_id.unwrap(), problem_yaml["name"], path)
    if ret.is_err():
        return ret

    checker = "wcmp"

    if "validator_flags" in problem_yaml:
        flag = problem_yaml["validator_flags"].lower()
        if "1e-6" in flag:
            checker = "rcmp6"
        if "1e-9" in flag:
            checker = "rcmp9"

    ret = set_checker(api_key, api_secret, problem_id.unwrap(), "std::" + checker + ".cpp")
    if ret.is_err():
        return ret
    

    ret = add_file(api_key, api_secret, problem_id.unwrap(), "./empty_validator.cpp", "source")
    if ret.is_err():
        return ret
    print("added validator")
    
    ret = set_validator(api_key, api_secret, problem_id.unwrap(), "empty_validator.cpp")
    if ret.is_err():
        return ret
    
    ret = add_main_sol(api_key, api_secret, problem_id.unwrap(), os.path.join(path, "main.cpp"))
    if ret.is_err():
        return ret
    
    # Add all the tests
    samples_dir = os.path.join(path, "data", "sample")
    tests_dir = os.path.join(path, "data", "secret")

    cnt = 0
    if os.path.exists(samples_dir):
        for i, test in enumerate(os.listdir(samples_dir)):
            # Ignore files that dont end with .in
            if not test.endswith(".in"):
                continue

            cnt += 1
            ret = add_test(api_key, api_secret, problem_id.unwrap(), os.path.join(samples_dir, test), True, cnt)
            if ret.is_err():
                return ret

    if os.path.exists(tests_dir):
        for i, test in enumerate(os.listdir(tests_dir)):
            # Ignore files that dont end with .in
            if not test.endswith(".in"):
                continue

            cnt += 1
            ret = add_test(api_key, api_secret, problem_id.unwrap(), os.path.join(tests_dir, test), False, cnt)
            if ret.is_err():
                return ret
    
    ret = commit_changes(api_key, api_secret, problem_id.unwrap())
    if ret.is_err():
        return ret
    
    ret = build_package(api_key, api_secret, problem_id.unwrap())
    if ret.is_err():
        return ret
    
    return Ok("Problem added")
    
def add_contest_from_dir(api_key, api_secret, path, name_prefix):
    # Get all problems in the directory
    problems = [f for f in os.listdir(path) if os.path.isdir(os.path.join(path, f))]
    
    # For each problem, add it to Polygon
    for problem in problems:
        add_problem_from_dir(api_key, api_secret, os.path.join(path, problem), name_prefix)

    return Ok("Contest added")

@click.command()
@click.argument("path")
@click.option("--name_prefix", default=None, help="Prefix to add to all problem names")
def to_polygon(path, name_prefix):
    api_key = os.getenv("POLYGON_API_KEY")
    if api_key is None:
        click.echo("No API key provided")
        return
    api_secret = os.getenv("POLYGON_API_SECRET")
    if api_secret is None:
        click.echo("No API secret provided")
        return

    # The command should receive exactly one argument, a path
    # Throw an error if it doesn't
    if not os.path.exists(path):
        click.echo("Path does not exist")
        return

    if is_domjudge_problem(path):
        ret = add_problem_from_dir(api_key, api_secret, path, name_prefix)
        if ret.is_err():
            click.echo(ret.unwrap_err())
    else:
        ret = add_contest_from_dir(api_key, api_secret, path, name_prefix)
        if ret.is_err():
            click.echo(ret.unwrap_err())

@click.command()
@click.option("--contest_id", default=None, prompt=True, help="ID of the contest to import")
def import_domjudge_contest(contest_id):
    username = os.getenv("DOMJUDGE_USERNAME")
    if username is None:
        click.echo("No username provided")
        return
    
    password = os.getenv("DOMJUDGE_PASSWORD")
    if password is None:
        click.echo("No password provided")
        return
    
    export_contest(contest_id, username, password)

@click.group()
def cli():
    pass

if __name__ == "__main__":
    load_dotenv()
    cli.add_command(to_polygon)
    cli.add_command(import_domjudge_contest)
    cli()