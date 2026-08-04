import traceback
import argparse
import asyncio
import json
import os
import re
import subprocess
from typing import Any
from helper.misc import GREEN, RESET
from dotenv import load_dotenv
from helper.orchestrator import Orchestrator
from helper.data_models import SWEBenchTaskInput, SandboxConfig
from helper.models import model_pool_help

load_dotenv()


def determine_python_version(image: str) -> str:
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            image,
            "bash",
            "-lc",
            "source /opt/miniconda3/bin/activate testbed && python --version",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    output = (result.stdout + result.stderr).strip()
    m = re.search(r"Python (\d+\.\d+)", output)
    if not m:
        raise RuntimeError(f"Couldn't determine Python version: {output}")

    return m.group(1)


def setup_docker(task: SWEBenchTaskInput) -> tuple[Any, Any]:
    image = task.docker_image
    volume_dir = "/testbed"
    os.makedirs(volume_dir, exist_ok=True)

    print("Downloading image...")
    subprocess.run(
        ["docker", "pull", image],
        text=True,
        timeout=1200,
    )

    temp_name = f"{task.instance_id.lower()}-temp-{os.getpid()}"
    container_name = f"{task.instance_id.lower()}-{os.getpid()}"

    print("Creating temp container...")
    subprocess.run(
        ["docker", "rm", "-f", temp_name],
        capture_output=True,
        text=True,
        check=False,
    )
    create_result = subprocess.run(
        ["docker", "create", "--name", temp_name, image],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if create_result.returncode != 0:
        raise RuntimeError(
            f"Failed to create temporary docker container for '{image}':\n"
            f"stdout: {create_result.stdout}\n"
            f"stderr: {create_result.stderr}"
        )

    print("Copying content to testbed...")
    copy_result = subprocess.run(
        ["docker", "cp", f"{temp_name}:/testbed/.", volume_dir],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if copy_result.returncode != 0:
        raise RuntimeError(
            f"Failed to copy /testbed from container "
            f"'{temp_name}' to '{volume_dir}':\n"
            f"stdout: {copy_result.stdout}\n"
            f"stderr: {copy_result.stderr}"
        )

    subprocess.run(
        ["docker", "rm", "-f", temp_name],
        capture_output=True,
        text=True,
        check=False,
    )
    subprocess.run(
        ["docker", "rm", "-f", container_name],
        capture_output=True,
        text=True,
        check=False,
    )

    print("Creating container with testbed...")
    run_result = subprocess.run(
        [
            "docker", "run", "-d", "--name", container_name,
            "-v", f"{volume_dir}:/testbed", "-w", "/testbed",
            image, "sleep", "infinity",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if run_result.returncode != 0:
        raise RuntimeError(
            f"Failed to create docker container "
            f"'{container_name}' from '{image}':\n"
            f"stdout: {run_result.stdout}\n"
            f"stderr: {run_result.stderr}"
        )

    print("Docker setup completed")
    return container_name, volume_dir


async def real_main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task-file", default="task.json",
                    help="input file containing SWE-bench task")
    ap.add_argument("--output", default="solution.json",
                    help="output file path")
    ap.add_argument("--model-name", default="agentsmith",
                    help=("LLM name override. If omitted, one is picked from: "
                          f"{model_pool_help()}"))
    ap.add_argument("--provider-url", default="https://openrouter.ai/api/v1",
                    help="LLM provider")
    ap.add_argument("--target", default="mcp_tools_swebench.py",
                    help="MCP tools server URL or file path")
    ap.add_argument("--sandbox-conf", default=None,
                    help="sandbox JSON config")
    args = ap.parse_args()

    sandbox_conf = SandboxConfig()
    if (args.sandbox_conf):
        with open(args.sandbox_conf, 'r') as f:
            try:
                conf_file = json.load(f)
                sandbox_conf = SandboxConfig.model_validate(conf_file)
            except Exception as e:
                print("JSON format error:", e)

    if args.task_file:
        try:
            with open(args.task_file, "r") as f:
                data = json.load(f)
            task = SWEBenchTaskInput.model_validate(data)
        except Exception:
            print("ERROR: Invalid task JSON")
            return

    client = None

    try:
        container_name, volume_dir = setup_docker(task)
        python_version = determine_python_version(task.docker_image)
        print(f"Detected Python {python_version}")
        print("Installing dependencies...")
        subprocess.run(
            [
                "bash",
                "-lc",
                """
                source /opt/miniconda3/bin/activate testbed
                cd /testbed
                python -m pip install --upgrade pip setuptools wheel
                python -m pip install pytest numpy scipy
                python -m pip install cython joblib threadpoolctl
                """,
            ],
            check=True,
        )
        os.environ["AGENT_DOCKER_CONTAINER"] = container_name
        sandbox_conf.allowed_directories = [volume_dir]
        client = Orchestrator(
            args.model_name,
            args.provider_url,
            args.target,
            sandbox_conf,
            "/tmp/eval.sh"
        )
        with open("/tmp/eval.sh", "w") as f:
            f.write(task.eval_script)
        await client.sandbox.init_mcp_client()
        result = await client.process_query(task, args)
        solution = result.model_dump_json(indent=4)
        with open(args.output, "w") as f:
            f.write(solution)
        if result.solution != "":
            print(f"{GREEN}FINAL ANSWER:\n{result.solution}{RESET}\n")
        print("task_id:", result.task_id)
        print("benchmark:", result.benchmark)
        print("success:", result.success)
        print("iterations:", result.iterations)
        print("total_requests:", result.total_requests)
        print("total_input_tokens:", result.total_input_tokens)
        print("total_output_tokens:", result.total_output_tokens)
        print("total_time_seconds:", result.total_time_seconds)
        print("timestamp:", result.timestamp)
    finally:
        if client:
            await client.cleanup()


def main() -> None:
    asyncio.run(real_main())


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        container_name = os.getenv("AGENT_DOCKER_CONTAINER")
        if container_name:
            subprocess.run(
                ["docker", "rm", "-f", container_name],
                capture_output=True,
                text=True,
                check=False,
            )
    except Exception as e:
        print(e)
        traceback.print_exc()
