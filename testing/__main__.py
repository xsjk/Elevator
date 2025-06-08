import sys
import asyncio
import argparse
from pathlib import Path

from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt
from rich import box

TEST_PATTERNS = ["test_*.py"]
console = Console()


def find_all_tests():
    base = Path(__file__).parent
    return [str(f) for pattern in TEST_PATTERNS for f in base.glob(pattern)]


class TestRunner:
    def __init__(self, test_paths):
        self.test_paths = test_paths
        self.results = {}
        self.outputs = {}
        self.statuses = {}
        self.live = None

    def set_live_display(self, live):
        self.live = live

    def set_status(self, test_path, status):
        self.statuses[test_path] = status
        if self.live:
            self.live.update(self.generate_table())

    async def run_test(self, test_path):
        # Set status to running
        self.set_status(test_path, "运行中")

        output = []

        # Start process asynchronously
        cmd = [sys.executable, "-m", "unittest", test_path]
        try:
            process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=Path(test_path).parent)

            # Collect output asynchronously
            async def read_stream(stream, is_error=False):
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    line_str = line.decode("utf-8").rstrip()
                    prefix = "ERROR: " if is_error else ""
                    output.append(prefix + line_str)
                    self.outputs[test_path] = "\n".join(output)

            # Create tasks for stdout and stderr
            stdout_task = asyncio.create_task(read_stream(process.stdout))
            stderr_task = asyncio.create_task(read_stream(process.stderr, True))

            # Monitor process
            await process.wait()

            # Process finished, make sure we got all output
            await stdout_task
            await stderr_task

            # Set final status
            success = "OK" in output[-1]
            self.set_status(test_path, "通过" if success else "失败")
            self.results[test_path] = success

            return test_path, success, self.outputs.get(test_path, "")

        except Exception as e:
            self.set_status(test_path, "错误")
            self.results[test_path] = False
            self.outputs[test_path] = f"{self.outputs.get(test_path, '')}\n异常: {str(e)}"
            return test_path, False, str(e)

    def generate_table(self):
        table = Table(box=box.ROUNDED)
        table.add_column("测试文件", style="cyan")
        table.add_column("状态", justify="center")
        table.add_column("结果", justify="center")

        status_styles = {
            "等待中": "yellow",
            "运行中": "blue",
            "通过": "green",
            "失败": "red",
            "错误": "red bold",
            "中止": "yellow italic",
        }

        for test_path in self.test_paths:
            test_name = Path(test_path).name
            status = self.statuses.get(test_path, "等待中")
            status_style = status_styles.get(status, "white")

            result = "✓" if self.results.get(test_path) is True else "✗" if self.results.get(test_path) is False else ""
            result_style = "green" if result == "✓" else "red" if result == "✗" else ""

            status_text = f"[{status_style}]{status}[/{status_style}]" if status_style else status
            result_text = f"[{result_style}]{result}[/{result_style}]" if result_style and result else result

            table.add_row(test_name, status_text, result_text)

        return table


def select_tests(tests):
    console.print("[bold blue]可用的测试脚本:[/bold blue]")
    for i, test in enumerate(tests, 1):
        console.print(f"  {i}. [cyan]{Path(test).name}[/cyan]")

    console.print("\n[bold]选择测试方式:[/bold]")
    console.print("  - 输入测试编号 (例如: 1 3 5)")
    console.print("  - 输入 'all' 运行所有测试")
    console.print("  - 输入 'exit' 退出\n")

    selection = Prompt.ask("请选择要运行的测试", default="all")

    if selection.lower() == "exit":
        console.print("[yellow]已退出[/yellow]")
        raise asyncio.CancelledError()  # Use exception instead of sys.exit()
    if selection.lower() == "all":
        return tests

    try:
        indices = [int(i.strip()) for i in selection.split() if i.strip()]
        selected = [tests[i - 1] for i in indices if 1 <= i <= len(tests)]

        if not selected:
            console.print("[yellow]没有有效的选择，将运行所有测试[/yellow]")
            return tests

        return selected
    except (ValueError, IndexError):
        console.print("[yellow]无效的选择，将运行所有测试[/yellow]")
        return tests


async def main():
    # Parse arguments
    parser = argparse.ArgumentParser(description="运行电梯系统测试")
    parser.add_argument("--all", action="store_true", help="运行所有测试，不进行交互选择")
    parser.add_argument("--tests", nargs="+", help="指定要运行的测试文件名 (例如: test_controller.py)")
    parser.add_argument("--max-workers", type=int, default=16, help="Maximum concurrent tests")
    args = parser.parse_args()

    # Find tests
    all_tests = find_all_tests()
    console.print(f"[bold blue]发现 {len(all_tests)} 个测试脚本[/bold blue]")

    # Select tests to run
    if args.tests:
        tests_to_run = []
        for pattern in args.tests:
            matching = [t for t in all_tests if Path(t).name == pattern or Path(t).name.startswith(pattern)]
            tests_to_run.extend(matching)

        if not tests_to_run:
            console.print("[bold red]未找到指定的测试文件[/bold red]")
            return 1  # Return exit code instead of sys.exit()

        console.print(f"[bold green]将运行 {len(tests_to_run)} 个指定的测试脚本[/bold green]")
    elif not args.all:
        try:
            tests_to_run = select_tests(all_tests)
        except EOFError:
            console.print("\n[bold yellow]已取消选择[/bold yellow]")
            return 0  # Return exit code instead of sys.exit()
        except SystemExit as e:
            return e.code  # Propagate exit code from SystemExit

        console.print(f"[bold green]将运行 {len(tests_to_run)} 个测试脚本[/bold green]")
    else:
        tests_to_run = all_tests

    # Remove duplicates
    tests_to_run = list(dict.fromkeys(tests_to_run))

    # Create runner
    runner = TestRunner(tests_to_run)

    # Setup semaphore for concurrency control
    max_concurrency = min(args.max_workers, len(tests_to_run))
    semaphore = asyncio.Semaphore(max_concurrency)

    async def run_test(test):
        async with semaphore:
            return await runner.run_test(test)

    with Live(runner.generate_table(), refresh_per_second=10, auto_refresh=True) as live:
        # Store reference and connect to runner
        runner.set_live_display(live)

        # Initialize all tests as "等待中" (waiting)
        for test_path in tests_to_run:
            runner.set_status(test_path, "等待中")

        # Create tasks but don't start them all immediately
        tasks = [asyncio.create_task(run_test(test)) for test in tests_to_run]

        # Wait for results or termination
        try:
            # Use wait with timeout to allow checking for termination
            pending = tasks.copy()
            while pending:
                # Wait with short timeout to allow checking for termination
                done, pending = await asyncio.wait(pending, timeout=0.1, return_when=asyncio.FIRST_COMPLETED)

                # Process completed tasks
                for task in done:
                    try:
                        await task
                    except Exception as e:
                        console.print(f"[bold red]执行错误: {str(e)}[/bold red]")

        except asyncio.CancelledError:
            # Handle cancellation - mark all pending tasks as aborted
            for test_path in tests_to_run:
                if test_path in runner.statuses and runner.statuses[test_path] in ["等待中", "运行中"]:
                    runner.set_status(test_path, "中止")

    # Show results
    passed = sum(1 for success in runner.results.values() if success)

    console.print("\n[bold]测试详细结果:[/bold]")
    for test_path in tests_to_run:
        test_name = Path(test_path).name
        status = runner.statuses.get(test_path, "")

        # Skip showing output for aborted tests
        if status == "中止":
            continue

        success = runner.results.get(test_path, False)
        output = runner.outputs.get(test_path, "无输出")

        result_text = "通过" if success else "失败"
        result_color = "green" if success else "red"

        console.print(
            Panel(
                output,
                title=f"[bold]{test_name}[/bold]",
                subtitle=f"结果: [{result_color}]{result_text}[/{result_color}]",
                border_style="green" if success else "red",
                padding=(1, 2),
            )
        )

    result_color = "green" if passed == len(tests_to_run) else "red"
    console.print(f"\n[bold]总结:[/bold] [{result_color}]{passed}/{len(tests_to_run)} 测试通过[/{result_color}]")
    return 0 if passed == len(tests_to_run) else 1


try:
    asyncio.Runner().run(main())
except KeyboardInterrupt:
    pass
