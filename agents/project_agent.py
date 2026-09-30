import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import TypedDict

from langchain_ollama import ChatOllama
from langgraph.graph import END, START, StateGraph


OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gpt-oss:latest")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
MAX_ITERATIONS_LIMIT = 8
MAX_PROJECT_FILES = 100
MAX_FILE_BYTES = 512_000
MAX_TOTAL_BYTES = 2_000_000
QA_TIMEOUT_SECONDS = 60


class ProjectAgentState(TypedDict):
	request: str
	analysis: str
	acceptance_criteria: list[str]
	language: str
	design: str
	output_dir: str
	files: dict[str, str]
	changed_files: dict[str, str]
	file_hashes: dict[str, str]
	iteration: int
	max_iterations: int
	qa_report: str
	qa_passed: bool
	retryable: bool
	generation_error: str
	status: str


def text_content(response) -> str:
	content = response.content
	return content if isinstance(content, str) else str(content)


def build_model() -> ChatOllama:
	return ChatOllama(
		model=OLLAMA_MODEL,
		base_url=OLLAMA_BASE_URL,
		temperature=0,
	)


def ask_model(instructions: str, context: str) -> str:
	response = build_model().invoke(
		[("system", instructions), ("user", context)]
	)
	return text_content(response)


def parse_json_payload(text: str) -> dict:
	"""Read a JSON object, tolerating a surrounding Markdown code fence."""
	cleaned = text.strip()
	if cleaned.startswith("```"):
		cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.I)
	decoder = json.JSONDecoder()
	for position, character in enumerate(cleaned):
		if character != "{":
			continue
		try:
			value, _ = decoder.raw_decode(cleaned[position:])
		except json.JSONDecodeError:
			continue
		if isinstance(value, dict):
			return value
	raise ValueError("模型没有返回有效的 JSON 对象")


def validate_relative_path(value: str) -> str:
	if not isinstance(value, str) or not value.strip():
		raise ValueError("文件路径必须是非空字符串")
	if "\\" in value or "\x00" in value:
		raise ValueError(f"路径只允许使用正斜杠：{value!r}")
	posix_path = PurePosixPath(value)
	windows_path = PureWindowsPath(value)
	parts = value.split("/")
	if (
		posix_path.is_absolute()
		or windows_path.is_absolute()
		or windows_path.drive
		or any(part in {"", ".", ".."} for part in parts)
	):
		raise ValueError(f"不允许绝对路径或路径穿越：{value!r}")
	return posix_path.as_posix()


def parse_file_manifest(text: str) -> dict[str, str]:
	"""Parse JSON or Markdown file blocks and bound the generated manifest."""
	try:
		payload = parse_json_payload(text)
	except ValueError:
		raw_files = None
	else:
		raw_files = payload.get("files")
	if not isinstance(raw_files, (dict, list)):
		raw_files = parse_markdown_file_blocks(text)
	if isinstance(raw_files, dict):
		entries = [{"path": path, "content": content} for path, content in raw_files.items()]
	elif isinstance(raw_files, list):
		entries = raw_files
	else:
		raise ValueError("文件清单必须包含 files 数组或对象")
	if not entries or len(entries) > MAX_PROJECT_FILES:
		raise ValueError(f"项目文件数量必须在 1 到 {MAX_PROJECT_FILES} 之间")

	files: dict[str, str] = {}
	total_bytes = 0
	for entry in entries:
		if not isinstance(entry, dict):
			raise ValueError("每个文件条目都必须是对象")
		path = validate_relative_path(entry.get("path"))
		content = entry.get("content")
		if not isinstance(content, str):
			raise ValueError(f"文件内容必须是字符串：{path}")
		if path in files:
			raise ValueError(f"文件清单中存在重复路径：{path}")
		content_bytes = len(content.encode("utf-8"))
		if content_bytes > MAX_FILE_BYTES:
			raise ValueError(f"单个文件超过 {MAX_FILE_BYTES} 字节：{path}")
		total_bytes += content_bytes
		if total_bytes > MAX_TOTAL_BYTES:
			raise ValueError(f"项目文件总大小超过 {MAX_TOTAL_BYTES} 字节")
		files[path] = content
	return files


def parse_markdown_file_blocks(text: str) -> list[dict[str, str]]:
	"""Parse sections shaped like `### FILE: src/main.py` followed by a fence."""
	lines = text.splitlines()
	files: list[dict[str, str]] = []
	index = 0
	while index < len(lines):
		line = lines[index]
		heading = re.match(
			r"^\s*(?:#{1,6}\s+)?(?:FILE\s*:\s*)?`?([^`]+?)`?\s*$",
			line,
			re.IGNORECASE,
		)
		is_file_heading = bool(
			heading
			and (re.match(r"^\s*#{1,6}\s+", line) or re.match(r"^\s*FILE\s*:", line, re.I))
		)
		if not is_file_heading:
			index += 1
			continue
		candidate = heading.group(1).strip()
		try:
			path = validate_relative_path(candidate)
		except ValueError:
			index += 1
			continue
		if not PurePosixPath(path).suffix:
			index += 1
			continue

		index += 1
		while index < len(lines) and not lines[index].strip():
			index += 1
		if index >= len(lines):
			break
		fence = re.match(r"^\s*(`{3,}|~{3,})(?:[^`~]*)$", lines[index])
		if not fence:
			index += 1
			continue
		marker = fence.group(1)
		fence_char = marker[0]
		closing_pattern = re.compile(r"^\s*" + re.escape(fence_char) + "{" + str(len(marker)) + r",}\s*$")
		index += 1
		content_lines = []
		while index < len(lines) and not closing_pattern.match(lines[index]):
			content_lines.append(lines[index])
			index += 1
		if index >= len(lines):
			raise ValueError(f"文件块代码围栏未闭合：{path}")
		if any(item["path"] == path for item in files):
			raise ValueError(f"文件清单中存在重复路径：{path}")
		files.append({"path": path, "content": "\n".join(content_lines) + "\n"})
		index += 1
	if not files:
		raise ValueError("回复中既没有有效 JSON 文件清单，也没有 Markdown 文件块")
	return files


def response_preview(text: str) -> str:
	preview = text.strip()[:1500]
	return f"\n模型回复片段：\n{preview}" if preview else ""


def parse_or_reformat_file_manifest(text: str, language: str) -> dict[str, str]:
	"""Make one format-only recovery attempt before failing a generation round."""
	try:
		return parse_file_manifest(text)
	except ValueError as initial_error:
		conversion_input = text[:12_000]
		if len(text) > len(conversion_input):
			conversion_input += "\n[回复过长，后续内容已省略]"
		formatted = ask_model(
			"你是代码文件清单格式转换器。把输入中的代码文件原样提取并输出为文件块，"
			"不得解释、总结、修改或省略代码。格式必须是："
			"### FILE: 相对路径\n```语言\n完整文件内容\n```。"
			"如果输入内容不足以识别文件路径，不要猜路径，只输出无法识别。",
			f"目标语言：{language}\n\n待转换的原始模型回复：\n{conversion_input}",
		)
		try:
			return parse_file_manifest(formatted)
		except ValueError as recovery_error:
			raise ValueError(
				f"原始回复无法解析（{initial_error}）；格式恢复也失败（{recovery_error}）"
				f"{response_preview(text)}{response_preview(formatted)}"
			) from recovery_error


def allocate_project_dir(output_root: Path) -> Path:
	root = output_root.expanduser().resolve()
	root.mkdir(parents=True, exist_ok=True)
	stamp = datetime.now().strftime("project-%Y%m%d-%H%M%S")
	for suffix in range(1000):
		name = stamp if suffix == 0 else f"{stamp}-{suffix}"
		candidate = root / name
		try:
			candidate.mkdir()
			return candidate
		except FileExistsError:
			continue
	raise RuntimeError("无法在输出目录中分配唯一项目目录")


def write_project_files(
	project_dir: Path,
	updates: dict[str, str],
	known_hashes: dict[str, str],
) -> dict[str, str]:
	"""Write only beneath the fresh project directory and detect user edits."""
	root = project_dir.resolve()
	new_hashes = dict(known_hashes)
	for relative_path, content in updates.items():
		path = validate_relative_path(relative_path)
		target = root.joinpath(*PurePosixPath(path).parts)
		resolved_target = target.resolve()
		if not resolved_target.is_relative_to(root):
			raise ValueError(f"文件路径越出项目目录：{path}")
		if target.is_symlink():
			raise ValueError(f"拒绝覆盖符号链接：{path}")
		if target.exists():
			previous_hash = known_hashes.get(path)
			current_hash = hashlib.sha256(target.read_bytes()).hexdigest()
			if previous_hash is None or current_hash != previous_hash:
				raise RuntimeError(f"检测到项目文件被外部修改，已停止覆盖：{path}")
		target.parent.mkdir(parents=True, exist_ok=True)
		target.write_text(content, encoding="utf-8", newline="")
		new_hashes[path] = hashlib.sha256(content.encode("utf-8")).hexdigest()
	return new_hashes


def requirements_analysis(state: ProjectAgentState) -> dict:
	response = ask_model(
		"你是资深产品分析师。分析用户需求并只返回 JSON 对象，字段为："
		"analysis（中文功能分析，含用户、目标、功能边界和主要流程），"
		"acceptance_criteria（可验证的验收条件字符串数组），"
		"language（只能是 python、javascript 或 unsupported）。"
		"只选择 Python 或 JavaScript；用户明确要求其他语言时设为 unsupported。"
		"用户没有指定语言时，根据需求在 Python 和 JavaScript 中选择一个。",
		state["request"],
	)
	result = parse_json_payload(response)
	analysis = result.get("analysis")
	criteria = result.get("acceptance_criteria")
	language = str(result.get("language", "unsupported")).strip().lower()
	if not isinstance(analysis, str) or not analysis.strip():
		raise ValueError("需求分析结果缺少 analysis")
	if not isinstance(criteria, list) or not all(isinstance(item, str) for item in criteria):
		raise ValueError("需求分析结果中的 acceptance_criteria 格式无效")
	if language not in {"python", "javascript", "unsupported"}:
		language = "unsupported"
	print(f"[Analysis] target language: {language}")
	return {
		"analysis": analysis,
		"acceptance_criteria": criteria,
		"language": language,
	}


def preflight(state: ProjectAgentState) -> dict:
	language = state["language"]
	if language == "unsupported":
		return {"status": "blocked", "qa_report": "当前版本只支持 Python 和 JavaScript 项目。"}
	if language == "javascript" and shutil.which("node") is None:
		return {
			"status": "blocked",
			"qa_report": "需求分析选择了 JavaScript，但当前环境找不到 Node.js。请安装 Node.js 后重试。",
		}
	output_dir = allocate_project_dir(Path(state["output_dir"]))
	return {"output_dir": str(output_dir), "status": "running"}


def route_after_preflight(state: ProjectAgentState) -> str:
	return "design" if state["status"] == "running" else "blocked"


def design_system(state: ProjectAgentState) -> dict:
	design = ask_model(
		"你是软件架构师。根据需求分析和验收标准编写精简但具体的系统设计，"
		"包括模块职责、数据流、关键接口、错误处理、测试策略和目录结构。"
		"必须使用指定语言，依赖限制为该语言标准库或运行时内置模块。",
		f"原始需求：\n{state['request']}\n\n"
		f"功能分析：\n{state['analysis']}\n\n"
		f"验收标准：\n{json.dumps(state['acceptance_criteria'], ensure_ascii=False)}\n"
		f"指定语言：{state['language']}",
	)
	print("[Design] complete")
	return {"design": design}


def prepare_documents(state: ProjectAgentState) -> dict:
	criteria = "\n".join(f"- {item}" for item in state["acceptance_criteria"])
	updates = {
		"docs/requirements-analysis.md": (
			"# 功能分析\n\n"
			f"## 原始需求\n\n{state['request']}\n\n"
			f"## 分析\n\n{state['analysis']}\n\n"
			f"## 验收标准\n\n{criteria}\n"
		),
		"docs/system-design.md": f"# 系统设计\n\n{state['design']}\n",
	}
	return {"changed_files": updates}


def generation_prompt(state: ProjectAgentState, repair: bool) -> tuple[str, str]:
	language_rules = (
		"使用 Python 3 和标准库，测试使用 unittest，测试文件放在 tests/test_*.py。"
		if state["language"] == "python"
		else "使用 Node.js JavaScript 和内置模块，测试使用 node:test，测试文件放在 tests/*.test.js。"
	)
	common = (
		f"用户需求：\n{state['request']}\n\n功能分析：\n{state['analysis']}\n\n"
		f"验收标准：\n{json.dumps(state['acceptance_criteria'], ensure_ascii=False)}\n\n"
		f"系统设计：\n{state['design']}\n\n"
		f"技术约束：{language_rules} 只使用标准库/內置模块，不要要求安装依赖。"
		"必须提供 README 和能够验证核心行为的自动化测试。"
	)
	if repair:
		common += (
			f"\n\n当前项目文件：\n{json.dumps(state['files'], ensure_ascii=False)}\n\n"
			f"最近一次 QA 结果：\n{state['qa_report']}\n"
			f"生成错误：\n{state['generation_error'] or '无'}\n\n"
			"仅返回需要新增或修改的文件；不要重复未变更文件。"
		)
	else:
		common += "\n请生成完整项目文件。"
	return (
		"你是负责交付可运行项目的高级工程师。根据需求与设计生成代码。"
		"优先使用以下 Markdown 文件块格式，逐个返回所有文件：\n"
		"### FILE: 相对路径\n```语言\n完整文件内容\n```\n"
		"Markdown 文件内容若包含三反引号代码块，外层改用四反引号。"
		"也兼容 JSON 文件清单格式 {\"files\":[{\"path\":\"相对路径\",\"content\":\"完整文件内容\"}]}。"
		"不要输出文件之外的说明；不得返回绝对路径、.. 路径、密钥或 shell 命令。",
		common,
	)


def generate_project(state: ProjectAgentState) -> dict:
	response = ""
	try:
		system, context = generation_prompt(state, repair=False)
		response = ask_model(system, context)
		files = parse_or_reformat_file_manifest(response, state["language"])
		return {
			"changed_files": files,
			"iteration": 1,
			"generation_error": "",
		}
	except Exception as exc:
		return {
			"changed_files": {},
			"iteration": 1,
			"generation_error": (
				f"代码生成失败：{type(exc).__name__}: {exc}"
				f"{response_preview(response)}"
			),
		}


def apply_file_changes(state: ProjectAgentState) -> dict:
	updates = state["changed_files"]
	if not updates:
		return {"files": state["files"]}
	try:
		hashes = write_project_files(
			Path(state["output_dir"]), updates, state["file_hashes"]
		)
	except Exception as exc:
		return {
			"generation_error": f"写入项目文件失败：{type(exc).__name__}: {exc}",
			"files": state["files"],
		}
	files = dict(state["files"])
	files.update(updates)
	return {"files": files, "file_hashes": hashes, "generation_error": ""}


def route_after_apply(state: ProjectAgentState) -> str:
	return "generate" if state["iteration"] == 0 else "qa"


def bounded_output(result: subprocess.CompletedProcess) -> str:
	output = (result.stdout or "") + (result.stderr or "")
	return output[-12_000:].strip() or f"退出码：{result.returncode}"


def run_fixed_command(command: list[str], project_dir: Path) -> tuple[bool, str]:
	env_names = ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP")
	env = {name: os.environ[name] for name in env_names if name in os.environ}
	env["PYTHONIOENCODING"] = "utf-8"
	try:
		result = subprocess.run(
			command,
			cwd=project_dir,
			env=env,
			capture_output=True,
			text=True,
			encoding="utf-8",
			errors="replace",
			timeout=QA_TIMEOUT_SECONDS,
			check=False,
			shell=False,
		)
		details = bounded_output(result)
		return result.returncode == 0, details
	except subprocess.TimeoutExpired as exc:
		output = (exc.stdout or b"") + (exc.stderr or b"")
		if isinstance(output, bytes):
			output = output.decode("utf-8", errors="replace")
		return False, f"命令超过 {QA_TIMEOUT_SECONDS} 秒，已终止。\n{output[-12_000:]}"
	except OSError as exc:
		return False, f"无法启动固定 QA 命令：{exc}"


def run_python_qa(project_dir: Path, files: dict[str, str]) -> tuple[bool, str, bool]:
	python_files = [path for path in files if PurePosixPath(path).suffix == ".py"]
	tests = [
		path for path in python_files
		if PurePosixPath(path).parts[0] == "tests"
		and PurePosixPath(path).name.startswith("test_")
	]
	if not tests:
		return False, "Python 项目必须包含 tests/test_*.py 自动化测试。", True
	for relative_path in python_files:
		try:
			compile((project_dir / Path(*PurePosixPath(relative_path).parts)).read_text(encoding="utf-8"), relative_path, "exec")
		except (SyntaxError, UnicodeError) as exc:
			return False, f"Python 语法错误：{relative_path}: {exc}", True
	for cache_dir in project_dir.rglob("__pycache__"):
		if cache_dir.is_dir() and not cache_dir.is_symlink():
			shutil.rmtree(cache_dir)
	passed, output = run_fixed_command(
		[sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-v"],
		project_dir,
	)
	return passed, f"Python unittest {'通过' if passed else '失败'}：\n{output}", True


def run_javascript_qa(project_dir: Path, files: dict[str, str]) -> tuple[bool, str, bool]:
	node = shutil.which("node")
	if node is None:
		return False, "当前环境没有 Node.js，无法执行 JavaScript QA。", False
	javascript_files = [
		path for path in files
		if PurePosixPath(path).suffix in {".js", ".mjs", ".cjs"}
	]
	tests = [
		path for path in javascript_files
		if PurePosixPath(path).parts[0] == "tests"
		and PurePosixPath(path).name.endswith(".test.js")
	]
	if not tests:
		return False, "JavaScript 项目必须包含 tests/*.test.js 自动化测试。", True
	for relative_path in javascript_files:
		passed, output = run_fixed_command(
			[node, "--check", relative_path], project_dir
		)
		if not passed:
			return False, f"JavaScript 语法检查失败：{relative_path}\n{output}", True
	passed, output = run_fixed_command(
		[node, "--test", *tests], project_dir
	)
	return passed, f"Node.js tests {'通过' if passed else '失败'}：\n{output}", True


def run_quality_checks(state: ProjectAgentState) -> dict:
	project_dir = Path(state["output_dir"])
	files = state["files"]
	if state["generation_error"]:
		return {
			"qa_passed": False,
			"retryable": True,
			"qa_report": state["generation_error"],
			"status": "qa_failed",
		}
	if not files:
		return {
			"qa_passed": False,
			"retryable": True,
			"qa_report": "项目没有生成任何文件。",
			"status": "qa_failed",
		}

	suffixes = {PurePosixPath(path).suffix.lower() for path in files}
	if suffixes & {".ts", ".tsx", ".jsx"}:
		return {
			"qa_passed": False,
			"retryable": False,
			"qa_report": "当前版本支持 Python 和原生 JavaScript，不支持 TypeScript/JSX。",
			"status": "blocked",
		}
	checks: list[tuple[bool, str]] = []
	if ".py" in suffixes:
		passed, report, retryable = run_python_qa(project_dir, files)
		checks.append((passed, report))
		if not retryable:
			return {"qa_passed": False, "retryable": False, "qa_report": report, "status": "blocked"}
	if suffixes & {".js", ".mjs", ".cjs"} or "package.json" in files:
		passed, report, retryable = run_javascript_qa(project_dir, files)
		checks.append((passed, report))
		if not retryable:
			return {"qa_passed": False, "retryable": False, "qa_report": report, "status": "blocked"}
	if not checks:
		return {
			"qa_passed": False,
			"retryable": False,
			"qa_report": "没有发现可执行 QA 的 Python 或 JavaScript 源文件。",
			"status": "blocked",
		}
	passed = all(item[0] for item in checks)
	report = "\n\n".join(item[1] for item in checks)
	print(f"[QA iteration {state['iteration']}] {'passed' if passed else 'failed'}")
	return {
		"qa_passed": passed,
		"retryable": True,
		"qa_report": report,
		"status": "success" if passed else "qa_failed",
	}


def route_after_qa(state: ProjectAgentState) -> str:
	if state["qa_passed"]:
		return "done"
	if not state["retryable"]:
		return "blocked"
	if state["iteration"] >= state["max_iterations"]:
		return "exhausted"
	return "repair"


def repair_project(state: ProjectAgentState) -> dict:
	response = ""
	try:
		system, context = generation_prompt(state, repair=True)
		response = ask_model(system, context)
		files = parse_or_reformat_file_manifest(response, state["language"])
		return {
			"changed_files": files,
			"iteration": state["iteration"] + 1,
			"generation_error": "",
		}
	except Exception as exc:
		return {
			"changed_files": {},
			"iteration": state["iteration"] + 1,
			"generation_error": (
				f"修复生成失败：{type(exc).__name__}: {exc}"
				f"{response_preview(response)}"
			),
		}


def finish_blocked(state: ProjectAgentState) -> dict:
	return {"status": "blocked"}


def finish_exhausted(state: ProjectAgentState) -> dict:
	return {"status": "max_iterations"}


def build_project_agent():
	graph = StateGraph(ProjectAgentState)
	graph.add_node("analyze", requirements_analysis)
	graph.add_node("preflight", preflight)
	graph.add_node("design", design_system)
	graph.add_node("prepare_docs", prepare_documents)
	graph.add_node("generate", generate_project)
	graph.add_node("apply", apply_file_changes)
	graph.add_node("qa", run_quality_checks)
	graph.add_node("repair", repair_project)
	graph.add_node("blocked", finish_blocked)
	graph.add_node("exhausted", finish_exhausted)
	graph.add_edge(START, "analyze")
	graph.add_edge("analyze", "preflight")
	graph.add_conditional_edges(
		"preflight", route_after_preflight,
		{"design": "design", "blocked": "blocked"},
	)
	graph.add_edge("design", "prepare_docs")
	graph.add_edge("prepare_docs", "apply")
	graph.add_conditional_edges(
		"apply", route_after_apply,
		{"generate": "generate", "qa": "qa"},
	)
	graph.add_edge("generate", "apply")
	graph.add_conditional_edges(
		"qa", route_after_qa,
		{"done": END, "repair": "repair", "blocked": "blocked", "exhausted": "exhausted"},
	)
	graph.add_edge("repair", "apply")
	graph.add_edge("blocked", END)
	graph.add_edge("exhausted", END)
	return graph.compile()


def run_project_agent(request: str, output_root: Path, max_iterations: int) -> ProjectAgentState:
	if not request.strip():
		raise ValueError("项目需求不能为空")
	if not 1 <= max_iterations <= MAX_ITERATIONS_LIMIT:
		raise ValueError(f"max_iterations 必须在 1 到 {MAX_ITERATIONS_LIMIT} 之间")
	app = build_project_agent()
	return app.invoke(
		{
			"request": request,
			"analysis": "",
			"acceptance_criteria": [],
			"language": "",
			"design": "",
			"output_dir": str(output_root),
			"files": {},
			"changed_files": {},
			"file_hashes": {},
			"iteration": 0,
			"max_iterations": max_iterations,
			"qa_report": "",
			"qa_passed": False,
			"retryable": True,
			"generation_error": "",
			"status": "starting",
		}
	)


def main() -> int:
	parser = argparse.ArgumentParser(
		description="分析需求、设计并生成 Python/JavaScript 项目，通过 QA 失败反馈迭代修复。"
	)
	parser.add_argument("request", help="用自然语言描述要构建的项目")
	parser.add_argument(
		"--output-root", type=Path, default=Path.cwd() / "generated_projects",
		help="新项目的父目录；Agent 只会创建新的子目录",
	)
	parser.add_argument(
		"--max-iterations", type=int, default=3,
		help=f"最多 QA 轮数（1-{MAX_ITERATIONS_LIMIT}，默认 3）",
	)
	args = parser.parse_args()
	print(f"模型：{OLLAMA_MODEL}")
	print(f"输出根目录：{args.output_root.resolve()}")
	try:
		state = run_project_agent(args.request, args.output_root, args.max_iterations)
	except Exception as exc:
		print(f"\nAgent 执行失败：{type(exc).__name__}: {exc}")
		return 1
	print(f"\n状态：{state['status']}")
	if state["output_dir"] and state["status"] != "blocked":
		print(f"项目目录：{state['output_dir']}")
	if state["qa_report"]:
		print(f"\nQA 报告：\n{state['qa_report']}")
	if state["status"] == "success":
		print(f"\n项目通过 QA，共执行 {state['iteration']} 轮。")
		return 0
	if state["status"] == "max_iterations":
		print(f"\n达到 {state['max_iterations']} 轮上限，项目保留供人工检查或继续迭代。")
	return 1


if __name__ == "__main__":
	raise SystemExit(main())