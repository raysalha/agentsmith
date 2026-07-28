import argparse
import asyncio
import json
import os
import subprocess
from typing import Any
from helper.misc import GREEN, RESET
from dotenv import load_dotenv
from helper.orchestrator import Orchestrator
from helper.data_models import SWEBenchTaskInput, SandboxConfig

load_dotenv()


def setup_docker(task: SWEBenchTaskInput) -> tuple[Any, Any]:
    image = task.docker_image
    volume_dir = "/tmp/agent"
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
    ap.add_argument("--model-name", default="openai/gpt-oss-120b",
                    help="LLM name")
    ap.add_argument("--provider-url", default="https://api.groq.com/openai/v1",
                    help="LLM provider")
    ap.add_argument("--target", default="agent_mbpp/mcp_tools_mbpp.py",
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

    api_key = os.getenv("OPENROUTER_API")
    if not api_key:
        print("Invalid or no API key")
        return

    try:
        container_name, volume_dir = setup_docker(task)
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
        os.environ["AGENT_DOCKER_CONTAINER"] = container_name
        result = await client.process_query(task, args)
        print(f"{GREEN}FINAL ANSWER:\n{result.solution}{RESET}\n")
        solution = result.model_dump_json(indent=4)
        print(f"task_id: {result.task_id}")
        print(f"benchmark: {result.benchmark}")
        print(f"success: {result.success}")
        print(f"iterations: {result.iterations}")
        print(f"total_requests: {result.total_requests}")
        print(f"total_input_tokens: {result.total_input_tokens}")
        print(f"total_output_tokens: {result.total_output_tokens}")
        print(f"total_time_seconds: {result.total_time_seconds}")
        print(f"timestamp: {result.timestamp}")
        with open(args.output, "w") as f:
            f.write(solution)
    finally:
        await client.cleanup()


def main() -> None:
    asyncio.run(real_main())


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(e)
