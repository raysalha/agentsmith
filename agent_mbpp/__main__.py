import argparse
import asyncio
import json
from helper.misc import GREEN, RESET
from dotenv import load_dotenv
from helper.orchestrator import Orchestrator
from helper.data_models import MBPPTaskInput, SandboxConfig
from helper.models import model_pool_help, pick_model

load_dotenv()


async def real_main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task-file", default="task.json",
                    help="input file containing MBPP task")
    ap.add_argument("--output", default="solution.json",
                    help="output file path")
    ap.add_argument("--model-name", default=None,
                    help=("LLM name override. If omitted, one is picked from: "
                          f"{model_pool_help()}"))
    ap.add_argument("--provider-url", default="https://openrouter.ai/api/v1",
                    help="LLM provider")
    ap.add_argument("--target", default="mcp_tools_mbpp.py",
                    help="MCP tools server URL or file path")
    ap.add_argument("--sandbox-conf", default=None,
                    help="sandbox JSON config")
    args = ap.parse_args()
    args.model_name = pick_model(args.model_name)
    print("Using model:", args.model_name)

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
        print("task_id:", result.task_id)
        print("benchmark:", result.benchmark)
        print("success:", result.success)
        print("iterations:", result.iterations)
        print("total_requests:", result.total_requests)
        print("total_input_tokens:", result.total_input_tokens)
        print("total_output_tokens:", result.total_output_tokens)
        print("total_time_seconds:", result.total_time_seconds)
        print("timestamp:", result.timestamp)
        with open(args.output, "w") as f:
            f.write(solution)
    finally:
        if client:
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
