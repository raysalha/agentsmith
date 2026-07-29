import argparse
import asyncio
import json
import os
from helper.misc import GREEN, RESET
from dotenv import load_dotenv
from helper.orchestrator import Orchestrator
from helper.data_models import MBPPTaskInput, SandboxConfig

load_dotenv()


async def real_main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task-file", default="task.json",
                    help="input file containing MBPP task")
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
            task = MBPPTaskInput.model_validate(data)
        except Exception:
            print("ERROR: Invalid task JSON")
            return

    api_key = os.getenv("OPENROUTER_API")
    if not api_key:
        print("Invalid or no API key")
        return

    try:
        client = Orchestrator(
            args.model_name,
            args.provider_url,
            args.target,
            sandbox_conf,
            None
        )
        await client.sandbox.init_mcp_client(task.test_imports, task.test_list)
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
